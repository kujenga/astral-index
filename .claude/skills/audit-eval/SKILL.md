---
name: audit-eval
description: |
  Audit the evaluation system. Generates a test draft, independently assesses quality,
  compares to scorer output, and identifies blind spots or miscalibrations.
  Use to validate scorers are measuring what matters.
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Grep
  - Glob
  - Agent
---

# /audit-eval — Evaluation System QA

You are auditing the Astral Index evaluation system. Your job is to independently assess newsletter quality, compare your assessment to what the scorers report, and identify blind spots or miscalibrations.

## Arguments

`$ARGUMENTS` may contain:
- `--since N` — lookback window (default: 14, wider than normal for diversity)
- `--strategy X` — strategy to audit (default: baseline)
- `--draft-file PATH` — use an existing draft instead of generating one

## Step 1: Generate Test Draft

If `--draft-file` was provided, use that. Otherwise generate a fresh draft:

```bash
uv run --package astral-author astral-author draft --since {SINCE} --strategy {STRATEGY} --output data/drafts/audit_draft.md
```

Confirm both `audit_draft.md` and `audit_draft.json` exist.

## Step 2: Run Full Eval

```bash
mkdir -p data/eval
uv run --package astral-eval astral-eval quality --since {SINCE} --draft-file data/drafts/audit_draft.json --output data/eval/audit_results.json
```

Read and parse `data/eval/audit_results.json`. Record every scorer name and score.

## Step 3: Independent Assessment

Read the draft markdown from `data/drafts/audit_draft.md`.

Read 5-10 source ContentItem JSON files from `data/items/` directories within the lookback window. Pick items from different dates and categories to get a representative sample.

Now independently assess the draft across these dimensions (many of which no scorer currently covers):

### Factual Grounding
- Do the summaries accurately reflect the source material?
- Are there claims not supported by the source items?
- Are numbers, dates, and names correct?

### Timeliness
- Are breaking/recent items given appropriate prominence?
- Are stale items (> 2 weeks old) included when fresher alternatives exist?

### Insight Depth
- Does the prose add analytical value beyond summarization?
- Are trends or connections between items identified?
- Or is it purely extractive?

### Source Authority
- Are primary sources (agency press releases, company announcements) prioritized over aggregator rewrites?
- Is there over-reliance on any single source?

### Completeness
- Based on the source items you read, are important stories missing from the draft?
- Are any categories underrepresented despite having good source material?

### Tone Consistency
- Does the editorial voice remain consistent across sections?
- Are there jarring transitions or style shifts?

Rate each dimension: Strong / Adequate / Weak / Not Assessed.

## Step 4: Compare

For each scorer in the eval results, compare what it reported to your independent assessment:

| Scorer | Reported Score | Independent Assessment | Agreement? |
|--------|---------------|----------------------|------------|
| source_diversity | 0.XX | ... | Yes/No |
| ... | ... | ... | ... |

Identify:

### Blind Spots
Quality dimensions with **no corresponding scorer**. For each blind spot, describe what a scorer would need to measure and how it could be implemented (heuristic vs. LLM judge).

### Miscalibrations
Cases where a scorer reports high but actual quality is low (or vice versa). Explain the discrepancy and what's causing it.

### Silent Failures
Check for scorers that returned `None` or were skipped. This is a known issue — `_judge_with_anthropic` has a broad `except Exception` that silently swallows errors. Note any missing scores.

## Step 5: Known Issue Validation

Check the known issues from the project memory:

### category_coverage underreporting
Read `packages/core/src/astral_core/scoring.py` and check if the `category_coverage` scorer examines item-level categories or only section-level. If it still only checks `section.category`, this bug persists.

### Silent LLM judge failures
Read `packages/eval/src/astral_eval/scorers/llm_judges.py` and check if the broad `except Exception` in `_judge_with_anthropic` still exists. Note whether errors are logged or silently swallowed.

Report the status of each known issue: Fixed / Still Present / Partially Fixed.

## Step 6: Report

Write a structured report to `data/eval/audit_report.md`:

```markdown
# Eval System Audit Report
Date: {TODAY}
Draft: {draft file used}
Strategy: {strategy}

## Scorer Results Summary
{table of all scorer results}

## Independent Assessment
{your assessment across the 6 dimensions}

## Blind Spots
{quality dimensions with no scorer — prioritized by importance}

## Miscalibrations
{scorers that disagree with independent assessment}

## Silent Failures
{scorers that returned None or were skipped}

## Known Issues Status
- category_coverage: {status}
- LLM judge error handling: {status}

## Recommendations
{prioritized list of:}
1. New scorers to implement (with approach: heuristic vs. LLM)
2. Existing scorer fixes
3. Rubric improvements for LLM judges
4. Other eval system improvements

## Suggested /iterate Targets
{2-3 specific improvements that could be implemented via /iterate}
```

Present a summary of the report to the user.

## Important Notes

- This skill is purely analytical — it does NOT modify any code.
- The report is designed to feed into `/iterate` as a list of improvement targets.
- Be honest about limitations: your independent assessment is based on a sample of source items, not all of them.
- When assessing factual grounding, compare specific claims in the draft against the source JSONs you read.
