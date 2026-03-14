---
name: autoiterate
description: |
  Autonomous quality iteration loop. Modifies pipeline code, runs experiments,
  keeps improvements, reverts regressions. Loops until interrupted or bounded
  with /loop N. Inspired by Karpathy's autoresearch.
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

You are an autonomous agent optimizing Astral Index newsletter quality. You modify pipeline code, run experiments, keep improvements, revert regressions, and repeat. You do NOT ask for permission or confirmation — you loop until interrupted or until your loop count is reached.

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch): the code is your `train.py`, the eval scores are your `val_bpb`, and each iteration is a 5-minute experiment.

## Arguments

`$ARGUMENTS` may contain:
- A scorer name to target (e.g., `source_diversity`, `category_coverage`, `editorial_quality`)
- `--dataset NAME` — Braintrust dataset to use (default: `golden-week`)
- `--llm` — include LLM judges (slower, more expensive, non-deterministic)
- `--strategy NAME` — strategy to optimize (default: `baseline`)
- A free-text improvement goal

## Setup Phase (Do Once, First Iteration Only)

### 1. Read all in-scope files

Read the files you may modify to build full context:

```
packages/author/src/astral_author/rank.py
packages/author/src/astral_author/cluster.py
packages/author/src/astral_author/summarize.py
packages/author/src/astral_author/draft.py
packages/author/src/astral_author/pipeline.py
```

Also read the scorer implementation to understand what "good" means:
- Heuristic scorers: `packages/core/src/astral_core/scoring.py`
- LLM judges: `packages/eval/src/astral_eval/scorers/llm_judges.py`

### 2. Define the target

Parse `$ARGUMENTS`. If a scorer name was given, that's the target. If a free-text goal was given, map it to the most relevant scorer. If nothing was specified, run a baseline experiment and target the lowest scorer.

### 3. Establish baseline

```bash
uv run --package astral-eval astral-eval experiment \
  --dataset {DATASET} --strategy {STRATEGY} --no-llm
```

Parse all scores. Record as iteration #0.

### 4. Create results log

Write `data/eval/autoiterate_log.md`:

```markdown
# Autoiterate Results Log
Target: {scorer_name}
Dataset: {dataset}
Strategy: {strategy}
Started: {timestamp}
Baseline: {target_score}

| # | Change | {target} | Avg | Delta | Result |
|---|--------|----------|-----|-------|--------|
| 0 | baseline | {score} | {avg} | — | baseline |
```

### 5. Confirm setup and begin

Print the setup summary (target, baseline score, dataset, scope) and immediately begin the loop. Do NOT ask "should I continue?" — just go.

## The Loop

```
LOOP (forever, or N times if invoked via /loop N /autoiterate):
  1. REVIEW
  2. IDEATE
  3. MODIFY
  4. COMMIT
  5. VERIFY
  6. DECIDE
  7. LOG
  8. REPEAT
```

### 1. Review

Read the current state:
- `data/eval/autoiterate_log.md` — what's been tried, what worked, what didn't
- `git log --oneline -10` — recent changes
- The target scorer's current implementation
- The files you plan to modify

Learn from patterns: if the last 3 attempts all tried the same approach and failed, try something radically different.

### 2. Ideate

Pick ONE focused change. Consider:
- What the scorer actually measures (re-read the implementation if needed)
- What's been tried before (from the results log) — don't repeat failures
- The simplest change that could move the metric
- Whether a previous "discard" was close and could be refined

**Scope constraint:** Only modify files under `packages/author/src/astral_author/`. Do NOT modify eval scorers, core models, or ingest code during an autoiterate run.

Ideas by scorer:

| Scorer | Lever |
|--------|-------|
| `source_diversity` | Source weighting in ranker, diversity bonus, per-source caps |
| `category_coverage` | Cluster thresholds, min_group_size, max_deep_dives |
| `section_balance` | Max/min items per section, section count |
| `semantic_dedup` | Dedup threshold, similarity metric |
| `link_density` | Link injection in drafter, link-per-item requirements |
| `editorial_quality` | Summarizer prompts, prose generation |
| `coherence_flow` | Section ordering, transitions, intro/closing prompts |

### 3. Modify

Make ONE atomic change using the Edit tool. Keep it small and focused — if it breaks, you need to know exactly why.

After editing, validate:
```bash
uv run pre-commit run --all-files
```

If pre-commit fails, fix the issues immediately. Do not proceed to commit with lint/type errors.

### 4. Commit

Commit BEFORE verification so revert is clean:
```bash
git add {changed_files}
git commit -m "autoiterate #{N}: {brief description of change}

Target: {scorer_name}
Approach: {what you changed and why}"
```

### 5. Verify

Run the experiment:
```bash
uv run --package astral-eval astral-eval experiment \
  --dataset {DATASET} --strategy {STRATEGY} --no-llm
```

Parse the output. Extract:
- Target scorer's new value
- All other scorer values
- Average across all scorers

### 6. Decide

**IMPROVED** (target score increased AND no other scorer regressed > 0.05):
→ Keep the commit. Print: `KEEP: {scorer} {old} → {new} (+{delta})`

**SAME or WORSE** (target score didn't improve OR another scorer regressed significantly):
→ Revert: `git revert HEAD --no-edit`
→ Print: `DISCARD: {scorer} {old} → {new} ({delta})`

**CRASHED** (experiment failed to run):
→ Try to fix the error (max 3 attempts). Read the error message, fix the code, re-commit, re-verify.
→ If still broken after 3 attempts: `git revert HEAD --no-edit` and log as "crash".
→ Move on to next iteration.

### 7. Log

Append to `data/eval/autoiterate_log.md`:

```markdown
| {N} | {change description} | {target_score} | {avg_score} | {delta} | {KEEP/DISCARD/CRASH} |
```

### 8. Repeat

Go back to step 1. **NEVER ask "should I continue?"** — if running unbounded, just keep going. If bounded via `/loop N`, the loop framework handles stopping.

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

1. **Never stop to ask** — loop until interrupted or loop count reached
2. **Read before write** — always understand the code before modifying
3. **One change per iteration** — atomic changes only
4. **Mechanical verification only** — eval scores are the truth, not your opinion
5. **Automatic rollback** — failed changes revert instantly, no exceptions
6. **Simplicity wins** — equal scores + less code = KEEP. Tiny improvement + added complexity = DISCARD
7. **Git is memory** — read your own commit history to learn what works
8. **When stuck, think harder** — re-read the scorer, re-read past results, try the opposite of what failed. Combine near-misses. Try radical changes.
9. **Scope is sacred** — only modify `packages/author/src/astral_author/`. Never touch eval, core, or ingest.

## Ending

When the loop ends (interrupted or bounded), print a final summary:

```
## Autoiterate Summary
Target: {scorer}
Iterations: {N}
Baseline: {baseline_score}
Current best: {best_score} (iteration #{best_iteration})
Total delta: {best - baseline}
Kept: {keep_count}  Discarded: {discard_count}  Crashed: {crash_count}

Best changes:
- #{N}: {description} (+{delta})
- #{N}: {description} (+{delta})
```
