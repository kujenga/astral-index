# Operator Workflow

This guide covers the week-to-week workflow for publishing Astral Index. The pipeline has four layers — **ingest**, **author**, **serve**, **eval** — each with its own CLI. Every command supports `--dry-run` for cost-free previews.

## Prerequisites

### Dependencies

```bash
uv sync --all-packages
uv run pre-commit install
```

### Credentials

All stored in `.env` (gitignored), loaded automatically via `python-dotenv`.

| Variable | Required for | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Classification (Haiku), authoring (Sonnet) | Pipeline degrades gracefully without it |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit scraping | Create app at reddit.com/prefs/apps |
| `SOCIALDATA_API_KEY` | Twitter/X scraping | SocialData.tools bearer token; scraper skips if missing |
| `BUTTONDOWN_API_KEY` | Newsletter delivery | Required for `draft` and `send` commands |
| `BRAINTRUST_API_KEY` | Evaluation & prompt management | Enables experiments, datasets, prompt versioning, LLM judge routing via AI Proxy. Install extras: `uv sync --all-packages --extra braintrust` |

Bluesky uses the public AT Protocol API — no credentials needed.

---

## Weekly Pipeline

### 1. Ingest

Scrape sources, expand excerpts to full text, and classify by category.

```bash
# Scrape all ~50 sources
uv run --package astral-ingest astral-ingest scrape

# Fetch full article text for excerpt-only items
uv run --package astral-ingest astral-ingest expand --since 7

# Classify items (keyword regex first, Claude Haiku fallback)
uv run --package astral-ingest astral-ingest classify --since 7
```

Each step is idempotent — re-running skips already-processed items.

**Optional flags:**
- `--source "SpaceNews"` — scrape a single source
- `--js` — enable Playwright for JS-rendered pages (slower, more thorough)
- `--concurrency 3` — parallel expansion workers
- `--no-llm` — skip LLM classification (keywords only, free)
- `--dry-run` — preview without saving

**Result:** ~500–1000 classified, full-text items in `data/items/{YYYY-MM-DD}/`.

### 2. Author

Generate a newsletter draft from the ingested items.

```bash
# Preview structure without LLM cost
uv run --package astral-author astral-author draft --since 7 --dry-run

# Generate full draft (uses Claude Sonnet for summaries)
uv run --package astral-author astral-author draft --since 7 --output data/drafts/draft.md

# Or use the headlines-only strategy (no LLM, free)
uv run --package astral-author astral-author draft --since 7 --strategy headlines-only --output data/drafts/draft.md
```

The `--output` flag writes both `draft.md` (rendered newsletter) and `draft.json` (full structured model for the delivery step).

**Comparing strategies:**

```bash
uv run --package astral-author astral-author compare baseline headlines-only --since 7
```

Outputs side-by-side `.md` + `.json` files and a comparison table (word count, sections, generation time).

**Result:** A polished markdown newsletter and its JSON sidecar in `data/drafts/`.

### 3. Review

Read the generated markdown. Check for:
- Factual accuracy of summaries
- Link quality and relevance
- Section balance and categorization
- Tone and readability

If something's off, tweak parameters and re-run `draft`, or edit the markdown directly. (If editing markdown directly, also update the `.json` sidecar or regenerate it.)

### 4. Evaluate (optional)

Score the draft before sending. Heuristic scorers (source diversity, category coverage, link count) run locally with no API cost. LLM judges (editorial quality, readability, coherence, etc.) need an API key.

```bash
# Heuristic only (free, fast)
uv run --package astral-eval astral-eval quality --since 7 --no-llm --draft-file data/drafts/draft.json

# Full eval with LLM judges
uv run --package astral-eval astral-eval quality --since 7 --draft-file data/drafts/draft.json

# Score an existing draft file (heuristic only, logs to Braintrust if available)
uv run --package astral-eval astral-eval score data/drafts/draft.json --since 7
```

Online scoring also runs automatically during `draft` — heuristic scores are logged to the current Braintrust span if tracing is active.

### 5. Deliver

Push the draft to Buttondown, review in their UI, then send.

```bash
# Create a draft in Buttondown
uv run --package astral-serve astral-serve draft data/drafts/draft.json

# Review in the Buttondown dashboard, then send
uv run --package astral-serve astral-serve send 2026-03-01
```

Both commands accept `--dry-run`. The `send` command is idempotent — it skips if the issue is already sent.

**Check status any time:**

```bash
uv run --package astral-serve astral-serve status              # all issues
uv run --package astral-serve astral-serve status 2026-03-01   # one issue
```

**State is tracked** in `data/newsletters/{YYYY-MM-DD}/meta.json` (publish record) alongside `draft.md` (markdown snapshot).

---

## Quick Reference

**Automated:** Run `scripts/weekly.sh` to execute the full pipeline in one command. Use `--dry-run` for preview mode, `--send` to include Buttondown delivery. Run `scripts/weekly.sh --help` for all options.

**Manual:** Copy-paste for a typical weekly run:

```bash
# Ingest
uv run --package astral-ingest astral-ingest scrape
uv run --package astral-ingest astral-ingest expand --since 7
uv run --package astral-ingest astral-ingest classify --since 7

# Author
uv run --package astral-author astral-author draft --since 7 --output data/drafts/draft.md

# Review the draft, then deliver
uv run --package astral-serve astral-serve draft data/drafts/draft.json
# ... review in Buttondown UI ...
uv run --package astral-serve astral-serve send YYYY-MM-DD
```

---

## Maintenance

### Managing sources

Edit `packages/ingest/src/astral_ingest/sources.yaml` to add, remove, or adjust sources. No code changes needed.

```bash
# Verify your source list
uv run --package astral-ingest astral-ingest sources
```

### Inspecting data

```bash
# Export recent items as markdown or JSON
uv run --package astral-ingest astral-ingest export --since 7 --format markdown
uv run --package astral-ingest astral-ingest export --since 7 --format json

# Filter by source
uv run --package astral-ingest astral-ingest export --since 7 --source "SpaceNews"
```

### Custom date ranges

Every `--since` flag accepts either days-back (integer) or an ISO date. Combine with `--before` for bounded windows.

```bash
uv run --package astral-ingest astral-ingest expand --since 2026-02-01 --before 2026-02-15
uv run --package astral-author astral-author draft --since 2026-02-01 --before 2026-02-08
```

### Running checks

```bash
uv run pytest -v                          # all tests
uv run pre-commit run --all-files         # ruff lint + format + ty type check
```

---

## Quality Iteration (Braintrust)

Braintrust enables reproducible evaluation: freeze a dataset, change code or prompts, and compare scores across runs. All commands below require `BRAINTRUST_API_KEY`.

### One-time setup

```bash
# Install Braintrust extras
uv sync --all-packages --extra braintrust

# Freeze a week of data as a golden dataset
uv run --package astral-eval astral-eval upload-dataset \
  --since 2026-03-01 --name golden-week

# Push current hardcoded prompts to Braintrust as initial versions
uv run --package astral-eval astral-eval seed-prompts
```

### Run an experiment

Each experiment generates a draft from the frozen dataset, scores it, and logs everything to Braintrust for comparison.

```bash
# Run against the golden dataset
uv run --package astral-eval astral-eval experiment \
  --dataset golden-week --strategy baseline

# Or against live data
uv run --package astral-eval astral-eval experiment \
  --since 7 --strategy baseline

# Heuristic scorers only (no LLM cost)
uv run --package astral-eval astral-eval experiment \
  --dataset golden-week --strategy baseline --no-llm
```

### Compare strategies

Runs separate experiments per strategy and prints a side-by-side score table.

```bash
uv run --package astral-eval astral-eval compare \
  baseline headlines-only --dataset golden-week
```

### The iteration loop

1. **Make a change** — tweak a prompt in the Braintrust UI, adjust ranker weights, modify clustering thresholds, or add a new strategy.
2. **Run an experiment** against the same golden dataset.
3. **Compare in the Braintrust dashboard** — diff any two experiments to see which scores improved or regressed.
4. **Repeat.**

The golden dataset holds input constant, so score changes are attributable to your code/prompt changes rather than different input data.

### CI integration

PRs that touch `packages/author/` or `packages/eval/` automatically run heuristic evaluation. Add the `eval-full` label to also run LLM judges. See `.github/workflows/eval.yml`.
