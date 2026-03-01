# Agents

## Project Overview

Astral Index is an AI-generated space technology newsletter. It scrapes space industry sources, uses LLMs to summarize and editorialize, and publishes curated content via RSS.

Inspired by [The Orbital Index](https://orbitalindex.com/) and [AI News](https://buttondown.com/ainews).

## Stack

- Python, managed with `uv`

## Project Structure

TBD as the project takes shape.

## Development

- Keep implementations simple — avoid premature abstraction

### uv

This project uses [uv](https://docs.astral.sh/uv/) for Python package and project management.

- `uv add <package>` — add a dependency
- `uv add --dev <package>` — add a dev dependency
- `uv sync` — install all dependencies from the lockfile
- `uv run <command>` — run a command in the project environment
- `uv run python <script>` — run a Python script
- `uv lock` — update the lockfile without installing

Dependencies are declared in `pyproject.toml`. The lockfile (`uv.lock`) should be committed. Never edit it manually.

For more details, see https://docs.astral.sh/uv/llms.txt
