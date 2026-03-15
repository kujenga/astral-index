---
name: iterate
description: |
  Quality improvement dev loop. Identifies weak scorers, proposes a change,
  implements it, runs a Braintrust experiment, and compares scores. Use when
  improving newsletter quality or trying a specific pipeline change.
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
---

# /iterate — Quality Improvement Dev Loop

You are running the Astral Index quality improvement loop. Your job is to diagnose a weak scorer, propose a targeted change, implement it, run an experiment, and keep or revert based on results.

## Arguments

`$ARGUMENTS` may contain:
- A scorer name to target (e.g., `source_diversity`, `category_coverage`, `editorial_quality`)
- A dataset name (e.g., `golden-standard`, `golden-full`, `golden-smoke`)
- `--no-llm` to skip LLM judges (heuristic scorers only)
- A free-text improvement goal

Defaults: dataset = `golden-standard`, target = lowest scorer, LLM judges enabled.

## Step 1: Establish Baseline

Parse `$ARGUMENTS` for dataset name and improvement goal.

Run the baseline experiment:
```bash
uv run --package astral-eval astral-eval experiment --dataset {DATASET} --strategy baseline
```

If `--no-llm` was passed, add `--no-llm` to skip LLM judges.

Read the output. Identify all scorer results. If no specific target was given in `$ARGUMENTS`, pick the lowest-scoring scorer as the target.

Present to the user:
- Full score table (scorer, score)
- Target scorer and its current score
- Ask for confirmation or override

## Step 2: Diagnose

Based on the target scorer, read the relevant source files to understand the current behavior:

| Scorer | Files to read |
|--------|---------------|
| `source_diversity` | `packages/author/src/astral_author/rank.py`, `packages/ingest/src/astral_ingest/sources.yaml` |
| `category_coverage` | `packages/author/src/astral_author/cluster.py` |
| `section_balance` | `packages/author/src/astral_author/cluster.py` |
| `semantic_dedup` | `packages/author/src/astral_author/rank.py` |
| `editorial_quality` | `packages/author/src/astral_author/summarize.py` |
| `coherence_flow` | `packages/author/src/astral_author/draft.py` |
| `link_density` | `packages/author/src/astral_author/draft.py` |
| LLM judges | `packages/eval/src/astral_eval/scorers/llm_judges.py` |

Also read the scorer's own implementation:
- Heuristic scorers: `packages/core/src/astral_core/scoring.py`
- LLM judges: `packages/eval/src/astral_eval/scorers/llm_judges.py`

Understand what the scorer measures and what "good" means (score thresholds, rubric).

## Step 3: Propose

Present 2-3 specific, concrete changes. For each:
- **File** to modify
- **Change** description (what to add/modify)
- **Expected effect** on the target scorer
- **Risk** of regression on other scorers

Ask the user to pick one, combine ideas, or suggest their own.

## Step 4: Implement

Make the code change using the Edit tool. Keep changes minimal and focused.

After editing, validate:
```bash
uv run pre-commit run --all-files
```

If pre-commit fails, fix the issues and re-run until clean.

If the change involves a new strategy, register it in the `STRATEGIES` dict in `packages/author/src/astral_author/pipeline.py`.

## Step 5: Experiment

Run the experiment with the change:
```bash
uv run --package astral-eval astral-eval experiment \
  --dataset {DATASET} --strategy {STRATEGY} \
  --experiment-name "{change_description}-{scorer}-$(date +%Y%m%d)"
```

If `--no-llm` was passed in arguments, add `--no-llm`.

## Step 6: Compare

Parse the experiment output. Present a comparison table:

| Scorer | Baseline | New | Delta |
|--------|----------|-----|-------|
| ... | ... | ... | +/- ... |

Highlight:
- Target scorer improvement (or lack thereof)
- Any regressions > 0.05 on other scorers
- Overall average change

## Step 7: Keep or Revert

Based on results:

**If clear improvement (target up, no significant regressions):**
- Stage and commit the changed files with a message like:
  ```
  feat(author): {change description}

  Experiment: {experiment-name}
  {target_scorer}: {old} -> {new} (+{delta})
  ```

**If clear regression:**
- Revert the changes: `git checkout -- {changed_files}`
- Explain what went wrong and suggest an alternative approach

**If mixed results (target improved but something regressed):**
- Present the tradeoffs clearly
- Ask the user whether to keep, revert, or iterate further

## Important Notes

- Each iteration should be atomic: one commit on success, clean revert on failure.
- Multiple `/iterate` runs can be chained — each builds on the last commit.
- Always run pre-commit before committing.
- If the experiment command fails because the dataset is empty or missing, run `uv run --package astral-eval astral-eval setup-datasets` to create the standard datasets, then retry.
- If the experiment command fails for other reasons, read the error carefully. Common issues: missing API key, import errors from code changes.
