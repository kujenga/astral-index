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
├── serve/      # astral-serve   — content serving (the app)
└── eval/       # astral-eval    — evaluation and quality iteration
```

Each package uses `src/` layout (e.g., `packages/core/src/astral_core/`).

### Key concepts

- **ContentItem** (`astral_core.models`) — the normalized schema all scrapers produce. ID is `sha256(url)[:16]`.
- **ContentStore** (`astral_core.store`) — JSON file storage at `data/items/{YYYY-MM-DD}/{id}.json`. One file per item.
- **Sources config** (`astral_ingest/sources.yaml`) — all RSS feeds and API endpoints. Add new sources here, not in code.
- Dedup is URL-hash based: scrapers check `store.exists(id)` before saving.

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
```

## Design references

The [Space News Scraping Infrastructure](https://www.notion.so/31677391e16b80719cbeefbf3d39d2fd) Notion doc contains the full source-by-source feasibility analysis, content schema rationale, and multi-phase roadmap. Consult it when adding new source types or evolving the pipeline.
