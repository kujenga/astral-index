# Operator Workflow

This guide covers the week-to-week workflow for publishing Astral Index. The pipeline has three layers — **ingest**, **author**, **serve** — each with its own CLI. Every command supports `--dry-run` for cost-free previews.

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

### 4. Deliver

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

All-in-one copy-paste for a typical weekly run:

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
