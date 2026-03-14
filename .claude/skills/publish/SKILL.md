---
name: publish
description: |
  Run the full Astral Index weekly publishing pipeline with quality gates.
  Scrapes sources, generates drafts, evaluates quality, and delivers via Buttondown.
  Use when publishing a newsletter issue.
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
---

# /publish — Intelligent Weekly Publishing

You are running the Astral Index weekly publishing pipeline. You execute the full ingest-author-eval-deliver pipeline with quality gates and editorial review.

## Arguments

`$ARGUMENTS` may contain:
- `--since N` — lookback window in days (default: 7)
- `--dry-run` — preview mode, no delivery
- `--send` — include Buttondown delivery at the end
- `--no-expand` — skip the expand step
- `--strategy X` — skip strategy comparison, use this strategy directly

Parse these from `$ARGUMENTS`. Set defaults: `SINCE=7`, `DRY_RUN=false`, `SEND=false`, `TODAY=$(date +%Y-%m-%d)`.

## Step 1: Pre-flight

Check that required environment is set up:
```bash
# Check for API keys (existence, not values)
test -f .env && grep -q "ANTHROPIC_API_KEY" .env && echo "ANTHROPIC_API_KEY: set" || echo "ANTHROPIC_API_KEY: MISSING"
test -f .env && grep -q "BRAINTRUST_API_KEY" .env && echo "BRAINTRUST_API_KEY: set" || echo "BRAINTRUST_API_KEY: MISSING"
test -f .env && grep -q "BUTTONDOWN_API_KEY" .env && echo "BUTTONDOWN_API_KEY: set" || echo "BUTTONDOWN_API_KEY: MISSING"
```

Report which keys are present. If `--send` was requested and `BUTTONDOWN_API_KEY` is missing, warn that delivery won't work.

Set output paths:
- `DRAFT_MD=data/drafts/${TODAY}_weekly.md`
- `DRAFT_JSON=data/drafts/${TODAY}_weekly.json`
- `EVAL_OUTPUT=data/eval/${TODAY}_results.json`

## Step 2: Ingest

Run sequentially:
```bash
uv run --package astral-ingest astral-ingest scrape
uv run --package astral-ingest astral-ingest expand --since {SINCE} --js
uv run --package astral-ingest astral-ingest classify --since {SINCE}
```

If `--dry-run`, add `--dry-run` to each command.
If `--no-expand`, skip the expand step.

After scraping, check item count:
```bash
uv run --package astral-ingest astral-ingest export --since {SINCE} --format json | head -5
```

Or count items in `data/items/` directories from the lookback window.

**Quality gate:** If fewer than 20 items were ingested, warn the user and ask whether to:
- Continue anyway
- Widen the window (suggest `--since {SINCE * 2}`)
- Abort

Report: total items, category breakdown if available.

## Step 3: Strategy Comparison

If `--strategy` was specified, skip this step and use that strategy.

Otherwise, compare all strategies:
```bash
uv run --package astral-eval astral-eval compare baseline headlines-only wide-coverage recency-biased --since {SINCE} --no-llm
```

Parse the comparison output. Present a table with scores per strategy. Recommend the highest-scoring strategy with a brief rationale.

Ask the user to confirm the strategy or pick a different one.

## Step 4: Draft

Generate the newsletter:
```bash
uv run --package astral-author astral-author draft --since {SINCE} --strategy {STRATEGY} --output {DRAFT_MD}
```

If `--dry-run`, add `--dry-run` and skip the output flag.

Confirm the draft files were written:
```bash
ls -la {DRAFT_MD} {DRAFT_JSON}
```

## Step 5: Evaluate

Skip if `--dry-run`.

```bash
mkdir -p data/eval
uv run --package astral-eval astral-eval quality --since {SINCE} --draft-file {DRAFT_JSON} --output {EVAL_OUTPUT}
```

Read the eval results. Present a score table.

**Quality gate:** If the average score < 0.5 or any individual scorer < 0.3:
- Flag the problematic scorers
- Recommend re-generating with a different strategy
- Ask whether to continue, re-draft, or abort

## Step 6: Editorial Review

Read the full markdown draft from `{DRAFT_MD}`.

Check for and report:
- Empty sections (no items)
- Sections with only 1 item (thin sections)
- Deep-dive sections missing prose/summaries
- Near-duplicate titles across sections
- Items without links
- Very short or very long sections (imbalance)
- Broken markdown formatting

Present a bullet-point editorial critique. If issues are found, suggest whether they warrant re-drafting or are acceptable.

## Step 7: Deliver

Only proceed if:
- `--send` was passed OR user explicitly confirms delivery
- Not in `--dry-run` mode
- Quality gates passed (or user overrode)

```bash
# Push draft to Buttondown
uv run --package astral-serve astral-serve draft {DRAFT_JSON}
```

After the draft is pushed, ask for **explicit confirmation** before sending:

> The draft has been pushed to Buttondown. Review it in the dashboard, then confirm: should I send it now?

Only on explicit "yes":
```bash
uv run --package astral-serve astral-serve send {TODAY}
```

Report the final status:
```bash
uv run --package astral-serve astral-serve status {TODAY}
```

## Important Notes

- This skill has three hard stops requiring user input: strategy selection, quality gate, and send confirmation. Everything else runs autonomously.
- If any step fails, report the error and ask whether to retry, skip, or abort.
- The draft JSON sidecar (`{DRAFT_JSON}`) is what gets sent to Buttondown, not the markdown.
- All `uv run` commands should be run from the project root directory.
