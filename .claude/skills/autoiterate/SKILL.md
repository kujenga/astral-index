---
name: autoiterate
description: |
  Autonomous quality iteration loop. Modifies pipeline code, runs experiments,
  keeps improvements, reverts regressions. Loops until interrupted, bounded
  with /loop N, or until a finish condition is met. Supports single-scorer
  targeting or sweep mode across all scorers. Inspired by Karpathy's autoresearch.
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
---

# /autoiterate — Autonomous Quality Iteration

You are an autonomous agent optimizing Astral Index newsletter quality. You modify code, run experiments, keep improvements, revert regressions, and repeat. You do NOT ask for permission or confirmation — you loop until interrupted, your loop count is reached, or your finish condition is met.

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch): the code is your `train.py`, the eval scores are your `val_bpb`, and each iteration is a 5-minute experiment.

## Arguments

`$ARGUMENTS` may contain any combination of:

### Target (what to optimize)
- A scorer name — e.g., `source_diversity`, `category_coverage`, `editorial_quality`
- `--mode sweep` — rotate through all scorers, weakest first (default if no scorer specified)
- `--mode single` — target one scorer only (default if a scorer name is given)

### Scope (what files you may touch)
- `--scope author` — only `packages/author/src/astral_author/` **(default, safest)**
- `--scope prompts` — only system prompt strings in summarize.py and draft.py
- `--scope strategies` — only STRATEGIES dict and stage configs in pipeline.py
- `--scope eval` — only `packages/core/src/astral_core/scoring.py` and `packages/eval/src/astral_eval/scorers/`
- `--scope sources` — only `packages/ingest/src/astral_ingest/sources.yaml`
- `--scope full` — all of the above

### Finish condition (when to stop)
- `--until "CONDITION"` — a natural-language finish condition, evaluated after each iteration. Examples:
  - `--until "all scorers above 0.6"`
  - `--until "average score exceeds 0.75"`
  - `--until "source_diversity above 0.5 and category_coverage above 0.7"`
  - `--until "3 consecutive improvements"`
  - `--until "no scorer below 0.4"`
- If omitted, loops forever (or N times via `/loop N`)

### Other options
- `--dataset NAME` — Braintrust dataset (default: `golden-standard`)
- `--no-llm` — skip LLM judges (faster, cheaper, deterministic — heuristic scorers only)
- `--strategy NAME` — strategy to optimize (default: `baseline`)
- Free-text improvement goal — interpreted as context for ideation

### Examples

```
/autoiterate                                              # sweep all scorers, author scope, loop forever
/autoiterate source_diversity                             # target one scorer
/autoiterate --mode sweep --scope full --until "average score above 0.7"
/autoiterate --mode sweep --until "all scorers above 0.5" # holistic improvement
/autoiterate --scope prompts editorial_quality             # tune prompts for editorial quality
/autoiterate --scope full --until "no scorer below 0.4"   # raise the floor
/loop 10 /autoiterate --mode sweep                        # 10 iterations across all scorers
```

## Setup Phase (Do Once, First Iteration Only)

### 1. Parse arguments and determine configuration

Parse `$ARGUMENTS` for mode, scope, target, finish condition, dataset, and strategy. Apply defaults for anything unspecified.

### 2. Read in-scope files

Based on the scope setting, read the files you may modify:

| Scope | Files to read |
|-------|---------------|
| `author` | `packages/author/src/astral_author/{rank,cluster,summarize,draft,pipeline}.py` |
| `prompts` | `packages/author/src/astral_author/summarize.py`, `draft.py` (prompt strings only) |
| `strategies` | `packages/author/src/astral_author/pipeline.py` |
| `eval` | `packages/core/src/astral_core/scoring.py`, `packages/eval/src/astral_eval/scorers/llm_judges.py` |
| `sources` | `packages/ingest/src/astral_ingest/sources.yaml` |
| `full` | All of the above |

Also read the scorer implementations to understand what "good" means:
- Heuristic scorers: `packages/core/src/astral_core/scoring.py`
- LLM judges: `packages/eval/src/astral_eval/scorers/llm_judges.py`

### 3. Establish baseline

```bash
uv run --package astral-eval astral-eval experiment \
  --dataset {DATASET} --strategy {STRATEGY}
```

If `--no-llm` was passed in `$ARGUMENTS`, add `--no-llm` to the command.

Parse ALL scores. Record as iteration #0. In sweep mode, rank scorers low-to-high — the lowest becomes the first target.

If the experiment fails because the dataset is empty or missing, run `uv run --package astral-eval astral-eval setup-datasets` to create the standard datasets, then retry.

### 4. Check finish condition

If `--until` was specified, evaluate the condition against baseline scores. If already met, print "Finish condition already satisfied" and stop.

### 5. Create results log

Write `data/eval/autoiterate_log.md`:

```markdown
# Autoiterate Results Log
Mode: {single|sweep}
Scope: {scope}
Dataset: {dataset}
Strategy: {strategy}
Finish condition: {condition or "none — loop until interrupted"}
Started: {timestamp}

## Baseline
| Scorer | Score |
|--------|-------|
| {scorer} | {score} |
| ... | ... |
| **Average** | **{avg}** |

## Iterations
| # | Target | Change | Score | Avg | Delta | Result |
|---|--------|--------|-------|-----|-------|--------|
| 0 | — | baseline | — | {avg} | — | baseline |
```

### 6. Begin

Print the setup summary and immediately begin the loop. Do NOT ask "should I continue?"

## The Loop

```
LOOP:
  1. SELECT TARGET (sweep mode) or use fixed target (single mode)
  2. REVIEW
  3. IDEATE
  4. MODIFY
  5. COMMIT
  6. VERIFY
  7. DECIDE
  8. LOG
  9. CHECK FINISH CONDITION
  10. REPEAT
```

### 1. Select Target (sweep mode only)

In sweep mode, pick the target for this iteration:
- Use the current lowest scorer
- BUT if you've failed 3 consecutive times on the same scorer, mark it "stuck" and skip to the next lowest
- After improving a scorer, re-rank all scorers from the latest experiment results — the new lowest becomes the next target
- Stuck scorers reset when you cycle back to them after improving others

In single mode, the target never changes.

### 2. Review

Read the current state:
- `data/eval/autoiterate_log.md` — what's been tried, what worked, what didn't
- `git log --oneline -10` — recent changes
- The target scorer's implementation (if you haven't read it recently)

Learn from patterns:
- If the last 3 attempts on this scorer all failed, try something radically different
- If a "discard" was close (delta > -0.02), consider refining that approach
- If scope is `full`, consider whether the bottleneck is in code, prompts, strategy config, or source data

### 3. Ideate

Pick ONE focused change. The scope setting determines what you're allowed to touch:

**Scope: `author`** (pipeline parameters and logic)

| Scorer | Levers |
|--------|--------|
| `source_diversity` | Source weighting in ranker, diversity bonus, per-source caps |
| `category_coverage` | Cluster thresholds, min_group_size, max_deep_dives |
| `section_balance` | Max/min items per section, section count |
| `semantic_dedup` | Dedup threshold, similarity metric |
| `link_density` | Link injection in drafter, link-per-item requirements |
| `editorial_quality` | Summarizer prompts, prose generation settings |
| `coherence_flow` | Section ordering, transitions, intro/closing prompts |

**Scope: `prompts`** (LLM prompt strings)

Modify system prompt constants in `summarize.py` and `draft.py`. Focus on:
- Clarity of instructions to the LLM
- Output format requirements
- Tone and voice guidance
- Specific quality criteria in the prompt

**Scope: `strategies`** (named pipeline configurations)

Modify or create strategy configs in `pipeline.py`:
- Adjust weights (w_recency, w_authority, etc.)
- Change stage parameters (max_deep_dives, min_group_size)
- Create new strategy entries in the STRATEGIES dict

**Scope: `eval`** (scorer implementations)

Fix or improve scorers in `scoring.py` or `llm_judges.py`:
- Fix known bugs (e.g., category_coverage not checking item-level categories)
- Adjust scoring curves or thresholds
- Improve LLM judge rubrics
- Add error handling for silent failures

**Scope: `sources`** (source configuration)

Add, remove, or adjust sources in `sources.yaml`:
- Add missing feeds for underrepresented categories
- Remove dead or low-yield sources
- Adjust source metadata

**Scope: `full`** — pick the most impactful lever for the current target, regardless of which file it's in. Think about where the real bottleneck is:
- If `source_diversity` is low and there are only 3 news sources, adding sources matters more than tweaking the ranker
- If `editorial_quality` is low, tuning prompts may matter more than changing pipeline logic
- If a scorer is miscalibrated, fixing the scorer (eval scope) is the right move

### 4. Modify

Make ONE atomic change using the Edit tool. Keep it small and focused.

After editing, validate:
```bash
uv run pre-commit run --all-files
```

If pre-commit fails, fix immediately. Do not proceed with lint/type errors.

### 5. Commit

Commit BEFORE verification so revert is clean:
```bash
git add {changed_files}
git commit -m "autoiterate #{N}: {brief description of change}

Target: {scorer_name}
Scope: {scope}
Approach: {what you changed and why}"
```

### 6. Verify

Run the experiment:
```bash
uv run --package astral-eval astral-eval experiment \
  --dataset {DATASET} --strategy {STRATEGY}
```

If `--no-llm` was passed in `$ARGUMENTS`, add `--no-llm` to the command.

Parse the output. Extract ALL scorer values and the average.

### 7. Decide

**Noise floor:** Heuristic scorers are deterministic — any delta is real. LLM judges have a noise floor of ~0.15 (one grade flip on one dataset row). Treat LLM judge deltas < 0.15 as noise unless corroborated by heuristic changes or consistent across multiple scorers.

**IMPROVED** (target score increased beyond noise floor AND no other scorer regressed > 0.05):
→ Keep the commit. Print: `KEEP: {scorer} {old} → {new} (+{delta})`

**SAME or WORSE** (target score didn't improve beyond noise, OR another scorer regressed significantly):
→ Revert: `git revert HEAD --no-edit`
→ Print: `DISCARD: {scorer} {old} → {new} ({delta})`

**CRASHED** (experiment failed to run):
→ Try to fix the error (max 3 attempts). Read the error, fix the code, re-commit, re-verify.
→ If still broken after 3 attempts: `git revert HEAD --no-edit` and log as "crash".
→ Move on.

### 8. Log

Append to `data/eval/autoiterate_log.md`:

```markdown
| {N} | {target_scorer} | {change description} | {target_score} | {avg_score} | {delta} | {KEEP/DISCARD/CRASH} |
```

### 9. Check Finish Condition

If `--until` was specified, evaluate the condition against the current scores (from the latest experiment, whether kept or baseline).

**How to evaluate conditions:**
- `"all scorers above X"` → check every scorer's current value > X
- `"average score above/exceeds X"` → check mean of all scores > X
- `"{scorer} above X"` → check that specific scorer > X
- `"no scorer below X"` → check every scorer >= X
- `"N consecutive improvements"` → check the last N results in the log are all KEEP
- Compound conditions with "and" → all parts must be true

The "current value" of a scorer is: the most recent KEEP result for that scorer, or the baseline if no KEEP exists.

If the condition is met:
→ Print: `FINISH CONDITION MET: "{condition}"`
→ Print the final summary (see Ending section)
→ Stop looping

If not met, continue to next iteration.

### 10. Repeat

Go back to step 1. **NEVER ask "should I continue?"**

## When Running as a Teammate (Agent Team Context)

If you are a teammate in an agent team (not the lead), your behavior changes:

1. You receive a **specific approach** from the lead (not free-form ideation)
2. You work in a **git worktree** for isolation
3. After verify, you **report your score to the lead** instead of deciding keep/revert
4. The lead decides which teammate's change wins
5. You shut down after reporting

Teammate protocol:
```
1. Receive approach description from lead
2. Create worktree: git worktree add /tmp/autoiterate-{name} -b autoiterate/{name}
3. cd into worktree
4. Implement the change
5. Run pre-commit
6. Commit
7. Run experiment, parse scores
8. Message lead: "Score: {target}={value}, avg={value}. Change: {description}. Branch: autoiterate/{name}"
9. Shut down
```

## Critical Rules

1. **Never stop to ask** — loop until interrupted, loop count reached, or finish condition met
2. **Read before write** — always understand the code before modifying
3. **One change per iteration** — atomic changes only
4. **Mechanical verification only** — eval scores are the truth, not your opinion
5. **Automatic rollback** — failed changes revert instantly, no exceptions
6. **Simplicity wins** — equal scores + less code = KEEP. Tiny improvement + added complexity = DISCARD
7. **Git is memory** — read your own commit history to learn what works
8. **When stuck, think harder** — re-read the scorer, re-read past results, try the opposite of what failed. Combine near-misses. Try radical changes.
9. **Respect scope** — only modify files allowed by the scope setting. In `full` scope, pick the highest-impact lever but stay deliberate.
10. **Sweep, don't fixate** — in sweep mode, move on after 3 consecutive failures on one scorer. Come back to it later.

## Ending

When the loop ends (interrupted, bounded, or finish condition met), print a final summary:

```
## Autoiterate Summary
Mode: {single|sweep}
Scope: {scope}
Finish condition: {condition or "none"}
Iterations: {N}

### Score Progression
| Scorer | Baseline | Current | Delta |
|--------|----------|---------|-------|
| {scorer} | {baseline} | {current} | {delta} |
| ... | ... | ... | ... |
| **Average** | **{baseline_avg}** | **{current_avg}** | **{delta}** |

### Iteration Log
Kept: {keep_count}  Discarded: {discard_count}  Crashed: {crash_count}

Best changes:
- #{N}: {description} → {scorer} +{delta}
- #{N}: {description} → {scorer} +{delta}

{if finish condition met}
Finish condition "{condition}" met at iteration #{N}.
{/if}
```
