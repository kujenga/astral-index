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
├── core/       # astral-core    — shared models and storage
├── ingest/     # astral-ingest  — data scraping
├── author/     # astral-author  — turning scraped data into newsletters
├── serve/      # astral-serve   — content serving (the app)
└── eval/       # astral-eval    — evaluation and quality iteration
```

Each package uses `src/` layout (e.g., `packages/core/src/astral_core/`).

## Development

- Keep implementations simple — avoid premature abstraction
- Always use `uv run` to execute Python commands — never call `python` or `python3` directly

### uv

This project uses [uv](https://docs.astral.sh/uv/) for Python package and project management.

- `uv sync --all-packages` — install all workspace packages and their dependencies
- `uv run --package <name> <command>` — run a command in a specific package's environment
- `uv add --package <name> <dep>` — add a dependency to a specific package
- `uv add --dev <dep>` — add a dev dependency (root-level)
- `uv lock` — update the lockfile without installing

Dependencies are declared per-package in each `packages/*/pyproject.toml`. The single workspace lockfile (`uv.lock`) at the root should be committed. Never edit it manually.

For more details, see https://docs.astral.sh/uv/llms.txt
