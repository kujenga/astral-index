# Agents

## Project Overview

Astral Index is an AI-generated space technology newsletter. It scrapes space industry sources, uses LLMs to summarize and editorialize, and publishes curated content via RSS.

Inspired by [The Orbital Index](https://orbitalindex.com/) and [AI News](https://buttondown.com/ainews).

## Stack

- Python, managed with `uv`

## Project Structure

Monorepo using [uv workspaces](https://docs.astral.sh/uv/concepts/workspaces/). The root `pyproject.toml` defines the workspace; each member lives under `packages/`:

```
packages/
├── core/       # astral-core    — shared models and storage (ContentItem, ContentStore)
├── ingest/     # astral-ingest  — RSS/API scrapers and CLI
├── author/     # astral-author  — turning scraped data into newsletters
├── serve/      # astral-serve   — newsletter delivery via Buttondown
└── eval/       # astral-eval    — evaluation and quality iteration
```

Each package uses `src/` layout (e.g., `packages/core/src/astral_core/`).

### Key concepts

- **ContentItem** (`astral_core.models`) — the normalized schema all scrapers produce. ID is `sha256(url)[:16]`.
- **ContentStore** (`astral_core.store`) — JSON file storage at `data/items/{YYYY-MM-DD}/{id}.json`. One file per item.
- **Sources config** (`astral_ingest/sources.yaml`) — all RSS feeds, API endpoints, Reddit subreddits, arXiv feeds, Bluesky accounts, and Twitter accounts. Add new sources here, not in code.
- **ExtractionMethod** (`astral_core.models`) — enum tracking how body text was obtained (feed, Reddit, trafilatura, newspaper, readability, playwright, pdf, snapi, bluesky_api, socialdata_api, arxiv_rss).
- **Link expansion** (`astral_ingest.expand`) — three-stage cascade (trafilatura → newspaper4k → readability-lxml) to fetch full article text for excerpt-only items. Optional Playwright JS rendering and PDF extraction.
- **Category classifier** (`astral_ingest.classify`) — two-pass classification: keyword regex (~70% coverage, free) then Claude Haiku LLM fallback for the rest.
- **Enhanced dedup** (`astral_ingest.dedup`) — URL normalization (strips tracking params), content hash, and title Levenshtein distance.
- Basic dedup: scrapers check `store.exists(id)` before saving.
- **Authoring pipeline** (`astral_author`) — four-stage pipeline (rank → cluster → summarize → draft) with swappable implementations via Protocol interfaces.
- **Pipeline stages**: `Ranker` (scores items), `Clusterer` (groups into sections), `Summarizer` (fills in summaries/prose), `Drafter` (assembles markdown).
- **Strategies** (`astral_author.pipeline`) — named compositions of stages. "baseline" uses Claude Sonnet for summaries; "headlines-only" uses excerpts only (no LLM).
- **Newsletter models** (`astral_author.models`) — `NewsletterDraft`, `NewsletterSection`, `ItemSummary`, `SectionType` (deep_dive, brief, links).
- **Newsletter delivery** (`astral_serve`) — two-step publish via Buttondown API: `draft` creates a remote draft, `send` promotes it. State tracked in `data/newsletters/{YYYY-MM-DD}/meta.json`.
- **PublishRecord** (`astral_serve.models`) — tracks issue publishing state (draft/sent/failed), Buttondown email ID, and metadata.
- **`get_llm_client`** (`astral_core.llm`) — shared factory returning an `AsyncAnthropic` client (or `None` when `ANTHROPIC_API_KEY` is unset). Automatically wraps with Braintrust tracing when `BRAINTRUST_API_KEY` is set. All LLM callsites (classifier, summarizer, drafter, eval judges) use this instead of creating clients directly.
- **Quality evaluation** (`astral_eval`) — multi-dimensional newsletter scoring: 3 heuristic scorers (source diversity, category coverage, link count) + 5 LLM judges (editorial quality, coverage adequacy, readability, link quality, coherence). Scorers return a `Score` dataclass (0.0–1.0). LLM judges use Claude Haiku with A–D rubrics.
- **Score** (`astral_eval.scores`) — lightweight dataclass: `name`, `score` (0.0–1.0), `metadata` dict. Decoupled from any eval framework.
- **Eval runner** (`astral_eval.runner`) — `run_quality_eval(draft, items, use_llm=True)` orchestrates heuristic (sync) and LLM (async concurrent) scorers.

## Public repository

This repo is public. Keep this in mind:

- **Never commit secrets** — API keys, tokens, credentials, and `.env` files must stay out of version control. Use environment variables or untracked config files.
- **Commit messages are visible** — write them as if anyone can read them. No internal shorthand, TODOs referencing private systems, or sloppy language.
- **Code quality matters from the start** — every commit is part of the public history. Prefer clean, intentional commits over fixup noise.
- **Be mindful of scraped data** — `data/` is gitignored for a reason. Don't commit raw content that may have licensing or copyright implications.

## Development

- Keep implementations simple — avoid premature abstraction
- Always use `uv run` to execute Python commands — never call `python` or `python3` directly
- Workspace packages depend on each other via `tool.uv.sources` (e.g., `astral-core = { workspace = true }` in astral-ingest's pyproject.toml)
- Scraped data lives in `data/` (gitignored) — never commit it

### Shared helpers in `astral_core`

Use these instead of rolling your own:

- **`bootstrap()`** (`astral_core.bootstrap`) — call once at CLI startup. Loads `.env` via `python-dotenv` and silences known-harmless warnings. Every CLI entry point (ingest, author, serve, eval) already calls this.
- **`get_llm_client()`** (`astral_core.llm`) — the **only** way to create an Anthropic client. Returns `AsyncAnthropic` or `None`. Never instantiate `anthropic.AsyncAnthropic` directly — this factory handles API key checks, graceful degradation, and Braintrust tracing. When adding a new LLM callsite, import from `astral_core` and check for `None` before calling.

### uv

This project uses [uv](https://docs.astral.sh/uv/) for Python package and project management.

- `uv sync --all-packages` — install all workspace packages and their dependencies
- `uv run --package <name> <command>` — run a command in a specific package's environment
- `uv add --package <name> <dep>` — add a dependency to a specific package
- `uv add --dev <dep>` — add a dev dependency (root-level)
- `uv lock` — update the lockfile without installing

Dependencies are declared per-package in each `packages/*/pyproject.toml`. The single workspace lockfile (`uv.lock`) at the root should be committed. Never edit it manually.

For more details, see https://docs.astral.sh/uv/llms.txt

### CLI

```bash
# List all configured news sources
uv run --package astral-ingest astral-ingest sources

# Scrape all sources (or one with --source "Name")
uv run --package astral-ingest astral-ingest scrape
uv run --package astral-ingest astral-ingest scrape --source "SpaceNews" --dry-run

# Export stored items as markdown or JSON
uv run --package astral-ingest astral-ingest export --since 7 --format markdown

# Expand excerpt-only items by fetching full article text
uv run --package astral-ingest astral-ingest expand --since 7
uv run --package astral-ingest astral-ingest expand --since 1 --js --concurrency 3 --dry-run

# Classify uncategorized items (keywords first, then LLM fallback)
uv run --package astral-ingest astral-ingest classify --since 7
uv run --package astral-ingest astral-ingest classify --since 7 --no-llm --dry-run

# List available authoring strategies
uv run --package astral-author astral-author strategies

# Generate a newsletter draft (headlines-only = no LLM needed)
uv run --package astral-author astral-author draft --since 7 --strategy headlines-only
uv run --package astral-author astral-author draft --since 7 --dry-run

# Write draft to file (writes both .md and .json sidecar)
uv run --package astral-author astral-author draft --since 7 --output data/drafts/draft.md

# Compare strategies side-by-side
uv run --package astral-author astral-author compare baseline headlines-only --since 7

# Create a Buttondown draft from a NewsletterDraft JSON file
uv run --package astral-serve astral-serve draft data/drafts/draft.json --dry-run
uv run --package astral-serve astral-serve draft data/drafts/draft.json

# Send a previously drafted newsletter
uv run --package astral-serve astral-serve send 2026-03-01 --dry-run
uv run --package astral-serve astral-serve send 2026-03-01

# View publishing status
uv run --package astral-serve astral-serve status
uv run --package astral-serve astral-serve status 2026-03-01

# Evaluate newsletter quality (heuristic only, no LLM needed)
uv run --package astral-eval astral-eval quality --since 30 --no-llm --strategy headlines-only

# Full quality eval with LLM judges (needs ANTHROPIC_API_KEY)
uv run --package astral-eval astral-eval quality --since 30 --strategy headlines-only

# Evaluate from an existing draft JSON file
uv run --package astral-eval astral-eval quality --since 30 --draft-file data/drafts/draft.json

# Write evaluation results to file
uv run --package astral-eval astral-eval quality --since 30 --no-llm --output data/eval/results.json
```

### Testing

```bash
uv run pytest -v                          # all packages
uv run pytest packages/ingest/tests/ -v   # one package
```

**No `__init__.py` in test directories.** The uv workspace has multiple `packages/*/tests/` dirs; adding `__init__.py` creates conflicting `tests` packages that cause `ImportPathMismatchError`. Test filenames must also be **unique across packages** — if two packages both have `test_cli.py`, pytest will hit `ImportPathMismatchError`. Use package-prefixed names (e.g., `test_eval_cli.py`) when a basename already exists elsewhere.

**HTTP mock seam:** All scrapers and expansion modules import `make_http_client` from `scrapers.base`. The `patch_http` conftest fixture patches this at every import site to inject `httpx.MockTransport`. When adding a new module that makes HTTP calls, use `make_http_client` and add the module path to `patch_http`'s patch list. No extra test dependencies needed — uses httpx's built-in `MockTransport`.

### Linting, Formatting, and Type Checking

Pre-commit hooks run automatically on `git commit`:
- **ruff** — linting (`ruff check --fix`) and formatting (`ruff format`)
- **ty** — type checking (`ty check`)

After cloning, install hooks:
```bash
uv sync --all-packages
uv run pre-commit install
```

To run all checks manually:
```bash
uv run pre-commit run --all-files
```

Configuration lives in the root `pyproject.toml`.

### Credentials

All credentials are stored in `.env` (gitignored) and loaded automatically via `python-dotenv`.

- **Reddit**: `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (create an app at https://www.reddit.com/prefs/apps). Optional `REDDIT_USER_AGENT`.
- **Twitter/X**: `SOCIALDATA_API_KEY` — Bearer token for the SocialData.tools API. Scraper skips gracefully when not set.
- **LLM**: `ANTHROPIC_API_KEY` — for classification (Claude Haiku) and authoring (Claude Sonnet summaries/prose). Both degrade gracefully without it.
- **Buttondown**: `BUTTONDOWN_API_KEY` — for newsletter delivery via the Buttondown API. The `draft` and `send` commands require this; `status` works without it.
- **Braintrust**: `BRAINTRUST_API_KEY` — optional, enables automatic trace logging for all LLM calls (classification, summarization, drafting, eval judges) via `wrap_anthropic`. Install with `uv sync --all-packages --extra braintrust`.
- **Bluesky**: No credentials needed — uses public AT Protocol AppView API.

## Keeping docs current

When adding a new package, feature, or pipeline stage, update these files:

- **`AGENTS.md`** (this file) — add key concepts, CLI commands, and credentials. This is the primary reference for agents working in the codebase.
- **`ARCHITECTURE.md`** — update the package breakdown, data flow diagram, and roadmap. This is the high-level design document for humans. Mark completed phases as "Done" and remove "Not yet implemented" / `(TODO)` labels.
- **Package `README.md`** — each package under `packages/` should have a README describing its scorers, commands, workflow, or API surface.

## Design references

The [Space News Scraping Infrastructure](https://www.notion.so/31677391e16b80719cbeefbf3d39d2fd) Notion doc contains the full source-by-source feasibility analysis, content schema rationale, and multi-phase roadmap. Consult it when adding new source types or evolving the pipeline.
