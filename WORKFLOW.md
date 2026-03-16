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
| `BRAINTRUST_API_KEY` | Braintrust observability | Experiments, datasets, prompt versioning, AI Proxy judges. Install extras: `uv sync --all-packages --extra braintrust` |
| `BRAINTRUST_TRACE` | Braintrust tracing (opt-in) | Set to `1` to enable LLM call tracing (counts toward free-tier limits) |
| `PHOENIX_COLLECTOR_ENDPOINT` | Phoenix tracing | OTLP trace ingest URL (e.g. `http://localhost:6006/v1/traces`) |
| `PHOENIX_API_URL` | Phoenix REST API | Datasets, experiments, prompts (e.g. `http://localhost:6006`) |
| `PHOENIX_API_KEY` | Phoenix auth | Optional for self-hosted Phoenix |
| `OPENAI_API_KEY` | Cross-model LLM judges (Phoenix path) | Direct OpenAI for judge calls when using Phoenix backend |
| `ASTRAL_OBSERVABILITY_BACKEND` | Backend override | `auto` (default), `braintrust`, `phoenix`, or `noop` |

Bluesky uses the public AT Protocol API — no credentials needed.

**Backend selection:** By default (`auto`), the system auto-detects: `PHOENIX_COLLECTOR_ENDPOINT` → Phoenix, `BRAINTRUST_API_KEY` → Braintrust, else noop. Override with `ASTRAL_OBSERVABILITY_BACKEND`.

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

Generate a newsletter draft. By default, output is staged in the git-tracked `issues/` directory.

```bash
# Preview structure without LLM cost
uv run --package astral-author astral-author draft --since 7 --dry-run

# Generate full draft → stages at issues/{date}/draft.md + draft.json
uv run --package astral-author astral-author draft --since 7

# Or use the headlines-only strategy (no LLM, free)
uv run --package astral-author astral-author draft --since 7 --strategy headlines-only

# Write to a custom path instead of issues/ (legacy behavior)
uv run --package astral-author astral-author draft --since 7 --output data/drafts/draft.md
```

Without `--output`, the draft is staged at `issues/{issue_date}/draft.md` (human-editable markdown) and `issues/{issue_date}/draft.json` (machine metadata). The markdown is the source of truth for content; edit it freely.

**Comparing strategies:**

```bash
uv run --package astral-author astral-author compare baseline headlines-only --since 7
```

Outputs side-by-side `.md` + `.json` files and a comparison table (word count, sections, generation time).

**Result:** A staged newsletter in `issues/{date}/` ready for review.

### 3. Review & Edit

The `issues/{date}/draft.md` file is git-tracked and human-editable. This is the editorial review step:

1. Read the generated markdown. Check for factual accuracy, link quality, section balance, and tone.
2. Edit `draft.md` directly — your edits become the source of truth for delivery.
3. Commit your edits for revision history:

```bash
git add issues/2026-03-15/
git commit -m "issue 2026-03-15: initial draft"

# ... make more edits ...
git commit -am "issue 2026-03-15: fix Artemis summary, reorder sections"
```

No need to update `draft.json` — the serve CLI reads markdown from `draft.md` and metadata from `draft.json` independently.

### 4. Evaluate (optional)

Score the draft before sending. Heuristic scorers (source diversity, category coverage, link count) run locally with no API cost. LLM judges (editorial quality, readability, coherence, etc.) need an API key.

```bash
# Heuristic only (free, fast)
uv run --package astral-eval astral-eval quality --since 7 --no-llm --draft-file issues/2026-03-15/draft.json

# Full eval with LLM judges
uv run --package astral-eval astral-eval quality --since 7 --draft-file issues/2026-03-15/draft.json

# Score an existing draft file (heuristic only, logs to Braintrust if available)
uv run --package astral-eval astral-eval score issues/2026-03-15/draft.json --since 7
```

Online scoring also runs automatically during `draft` — heuristic scores are logged to the current Braintrust span if tracing is active.

### 5. Deliver

Push the draft to Buttondown, review in their UI, then send. The serve CLI accepts a date string and reads from `issues/{date}/` — it uses `draft.md` for the email body (respecting your edits) and `draft.json` for title/metadata.

```bash
# Create a draft in Buttondown (reads from issues/2026-03-15/)
uv run --package astral-serve astral-serve draft 2026-03-15

# Review in the Buttondown dashboard, then send
uv run --package astral-serve astral-serve send 2026-03-15

# Commit the published state
git commit -am "issue 2026-03-15: published"
```

You can also pass a JSON file path directly (legacy behavior): `astral-serve draft data/drafts/draft.json`.

Both commands accept `--dry-run`. The `send` command is idempotent — it skips if the issue is already sent.

**Check status any time:**

```bash
uv run --package astral-serve astral-serve status              # all issues
uv run --package astral-serve astral-serve status 2026-03-15   # one issue
```

**State is tracked** in two places:
- `issues/{date}/meta.json` — lightweight staging state (Buttondown email ID, publish status)
- `data/newsletters/{date}/meta.json` — full Buttondown publish record (unchanged from before)

---

## Quick Reference

**Automated:** Run `scripts/weekly.sh` to execute the full pipeline in one command. Use `--dry-run` for preview mode, `--send` to include Buttondown delivery. Run `scripts/weekly.sh --help` for all options.

**Manual:** Copy-paste for a typical weekly run:

```bash
# Ingest
uv run --package astral-ingest astral-ingest scrape
uv run --package astral-ingest astral-ingest expand --since 7
uv run --package astral-ingest astral-ingest classify --since 7

# Author (stages at issues/{date}/)
uv run --package astral-author astral-author draft --since 7

# Review & edit issues/{date}/draft.md, then commit
git add issues/ && git commit -m "issue YYYY-MM-DD: initial draft"

# Deliver (reads from issues/{date}/)
uv run --package astral-serve astral-serve draft YYYY-MM-DD
# ... review in Buttondown UI ...
uv run --package astral-serve astral-serve send YYYY-MM-DD
git commit -am "issue YYYY-MM-DD: published"
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

## Quality Iteration

An observability backend (Braintrust or Phoenix) enables reproducible evaluation: freeze a dataset, change code or prompts, and compare scores across runs.

### One-time setup (Braintrust)

```bash
uv sync --all-packages --extra braintrust
uv run --package astral-eval astral-eval setup-datasets
uv run --package astral-eval astral-eval seed-prompts
```

### One-time setup (Phoenix)

```bash
uv sync --all-packages --extra phoenix
# Start Phoenix locally (or use a remote instance)
phoenix serve  # runs on http://localhost:6006
# Set env vars:
export PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
export PHOENIX_API_URL=http://localhost:6006
# Optionally, for cross-model judges:
export OPENAI_API_KEY=sk-...
# Create datasets and seed prompts
uv run --package astral-eval astral-eval setup-datasets
uv run --package astral-eval astral-eval seed-prompts
```

Three standard dataset tiers are available:
- **`golden-smoke`** (1 row) — fast sanity check during rapid iteration (~5s)
- **`golden-standard`** (4 rows) — default for `/iterate` and `/autoiterate`
- **`golden-full`** (8 rows) — comprehensive regression testing, CI

**Dataset-first rule:** Quality iteration (experiments, `/iterate`, `/autoiterate`) should always use `--dataset` for linked, reproducible results. Operational use (`/publish`) uses `--since` for live data.

### Run an experiment

Each experiment generates a draft from the frozen dataset, scores it, and logs everything to Braintrust for comparison.

```bash
# Run against the standard dataset (recommended for iteration)
uv run --package astral-eval astral-eval experiment \
  --dataset golden-standard --strategy baseline

# Or against live data (for operational use — warns about unlinked results)
uv run --package astral-eval astral-eval experiment \
  --since 7 --strategy baseline

# Heuristic scorers only (no LLM cost)
uv run --package astral-eval astral-eval experiment \
  --dataset golden-standard --strategy baseline --no-llm
```

### Compare strategies

Runs experiments in parallel for each strategy and prints a side-by-side score table. Available strategies: `baseline`, `headlines-only`, `wide-coverage`, `recency-biased`.

```bash
uv run --package astral-eval astral-eval compare \
  baseline headlines-only --dataset golden-standard

# Compare all four strategies against the full dataset (heuristic only)
uv run --package astral-eval astral-eval compare \
  baseline headlines-only wide-coverage recency-biased \
  --dataset golden-full --no-llm
```

### The iteration loop

1. **Make a change** — tweak a prompt in the Braintrust UI, adjust ranker weights, modify clustering thresholds, or add a new strategy.
2. **Run an experiment** against the same golden dataset.
3. **Compare in the Braintrust dashboard** — diff any two experiments to see which scores improved or regressed.
4. **Repeat.**

The golden dataset holds input constant, so score changes are attributable to your code/prompt changes rather than different input data.

### Agent-driven iteration (Claude Code skills)

The manual loop above can be automated with project-local Claude Code skills:

- **`/iterate source_diversity`** — agent-driven version of the loop: diagnoses the weak scorer, proposes a change, implements it, runs the experiment, and commits on improvement (reverts on regression). Each run is atomic.
- **`/audit-eval`** — meta-quality check that independently assesses a draft, compares to scorer output, and identifies blind spots or miscalibrations. Produces an audit report with targets for `/iterate`.
- **`/brainstorm`** — strategic analysis of source coverage, pipeline gaps, and eval dimensions. Read-only; output feeds into `/iterate`.
- **`/publish --since 7`** — full pipeline with quality gates (replaces `scripts/weekly.sh`). Includes strategy comparison, score thresholds, and editorial review before delivery.

**Autonomous mode:** `/autoiterate` runs the full loop without human input — sweep across all scorers, modify, experiment, keep/revert, repeat. Target a single scorer with `/autoiterate source_diversity`, bound iterations with `/loop 10 /autoiterate`, or set a finish condition with `--until "all scorers above 0.6"`. Control what files the agent may touch with `--scope` (author, prompts, strategies, eval, sources, full). For parallel exploration, see `.claude/skills/autoiterate/TEAM.md` for an agent team prompt that spawns 3 teammates in worktrees.

Typical workflow: `/brainstorm` to identify targets, `/iterate` (manual) or `/autoiterate` (autonomous) to implement them, `/audit-eval` to validate scorers, `/publish` to ship.

### CI integration

PRs that touch `packages/author/` or `packages/eval/` automatically run heuristic evaluation. Add the `eval-full` label to also run LLM judges. See `.github/workflows/eval.yml`.
