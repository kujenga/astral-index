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
- **Strategies** (`astral_author.pipeline`) — named compositions of stages. "baseline" uses Claude Sonnet for summaries; "headlines-only" uses excerpts only (no LLM); "wide-coverage" uses more deep-dive sections (max_deep_dives=5, min_group_size=1); "recency-biased" weights freshness heavily (w_recency=0.50).
- **Newsletter models** (`astral_author.models`) — `NewsletterDraft`, `NewsletterSection`, `ItemSummary`, `SectionType` (deep_dive, brief, links).
- **Newsletter delivery** (`astral_serve`) — two-step publish via Buttondown API: `draft` creates a remote draft, `send` promotes it. State tracked in `data/newsletters/{YYYY-MM-DD}/meta.json`.
- **PublishRecord** (`astral_serve.models`) — tracks issue publishing state (draft/sent/failed), Buttondown email ID, and metadata.
- **`get_llm_client`** (`astral_core.llm`) — shared factory returning an `AsyncAnthropic` client (or `None` when `ANTHROPIC_API_KEY` is unset). Automatically wraps with Braintrust tracing when `BRAINTRUST_API_KEY` is set. All LLM callsites (classifier, summarizer, drafter, eval judges) use this instead of creating clients directly.
- **Quality evaluation** (`astral_eval`) — multi-dimensional newsletter scoring: 3 heuristic scorers (source diversity, category coverage, link count) + 5 LLM judges (editorial quality, coverage adequacy, readability, link quality, coherence). Scorers return a `Score` dataclass (0.0–1.0). LLM judges use GPT-4o-mini via Braintrust AI Proxy (or Claude Haiku fallback) with A–D rubrics.
- **Score** (`astral_core.scoring`) — lightweight dataclass: `name`, `score` (0.0–1.0), `metadata` dict. Lives in core so both eval and author can import it.
- **Heuristic scorers** (`astral_core.scoring`) — the 3 heuristic scorer implementations live in core (re-exported by `astral_eval.scorers.heuristic` for backward compat). This avoids a circular dep so the author pipeline can run online scoring.
- **Eval runner** (`astral_eval.runner`) — `run_quality_eval(draft, items, use_llm=True)` orchestrates heuristic (sync) and LLM (async concurrent) scorers.
- **Braintrust experiment runner** (`astral_eval.experiment`) — `run_experiment()` wraps `braintrust.EvalAsync()` with adapted scorers. Falls back to local `run_quality_eval()` when Braintrust is not available.
- **Braintrust scorer adapters** (`astral_eval.braintrust_scorers`) — `wrap_scorer()` bridges astral-eval's `(output=, input=)` signature to Braintrust's `(input, output)` signature.
- **Golden-week datasets** (`astral_eval.datasets`) — `upload_golden_week()` pushes frozen ContentItem sets to Braintrust for reproducible regression testing.
- **Prompt management** (`astral_core.prompts`) — `load_prompt(slug, fallback)` fetches versioned prompts from Braintrust when available, with zero-change fallback to hardcoded strings. All 4 LLM prompts (item-summarizer, prose-generator, newsletter-intro, category-classifier) use this.
- **Online scoring** — `DraftPipeline.run()` automatically runs heuristic scorers after every draft and logs scores to the current Braintrust span.

### Braintrust integration

Braintrust is wired into the project at multiple layers. Everything degrades gracefully when `BRAINTRUST_API_KEY` is unset — hardcoded fallbacks are used and no errors are raised (only a one-time warning from `get_llm_client()`).

**Touch points — know these when modifying LLM or eval code:**

1. **Tracing** — `get_llm_client()` in `astral_core.llm` wraps the Anthropic client with `braintrust.wrap_anthropic()`. Every LLM call (classify, summarize, draft, judge) is automatically traced. No per-callsite changes needed.
2. **Prompts** — `load_prompt(slug, fallback)` in `astral_core.prompts` fetches versioned prompts from Braintrust. The 4 prompt slugs are: `item-summarizer`, `prose-generator`, `newsletter-intro`, `category-classifier`. When adding a new LLM prompt, add a slug and pass the hardcoded string as `fallback`.
3. **Online scoring** — `DraftPipeline.run()` runs heuristic scorers after every draft and logs scores to the active Braintrust span. The scorers live in `astral_core.scoring` (not `astral_eval`) to avoid a circular dependency.
4. **Experiments** — `run_experiment()` in `astral_eval.experiment` wraps `braintrust.EvalAsync()`. Pass a `Dataset` object (not `list(dataset)`) so the SDK links the experiment to the dataset. Falls back to the local `run_quality_eval()` runner when Braintrust is unavailable.
5. **Scorer adapters** — `wrap_scorer()` in `astral_eval.braintrust_scorers` bridges the astral-eval scorer signature `(*, output=, input=)` to Braintrust's `(input, output, expected=None)`. When adding a new scorer, wrap it and add to `ALL_BT_SCORERS`.
6. **Datasets** — `upload_golden_week()` in `astral_eval.datasets` uploads a frozen set of ContentItems as a single-row Braintrust dataset (input = list of all items). `upload_golden_set()` uploads multiple week-windows as separate rows for multi-week baselines. Each experiment row is one full newsletter generation.
7. **LLM judges** — the 5 LLM judges in `astral_eval.scorers.llm_judges` route through Braintrust AI Proxy (GPT-4o-mini) when available, falling back to Claude Haiku via the Anthropic client.
8. **CI** — `.github/workflows/eval.yml` runs heuristic evals on PRs touching `packages/author/` or `packages/eval/`. Add the `eval-full` label for LLM judges.

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
- **`load_prompt(slug, fallback)`** (`astral_core.prompts`) — load a versioned prompt from Braintrust, or return the fallback string. Use this for all system prompts sent to LLMs. The fallback is always the hardcoded constant (e.g., `_ITEM_SYSTEM`), so behavior is unchanged without Braintrust.

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

# Run a Braintrust-tracked experiment (needs BRAINTRUST_API_KEY)
uv run --package astral-eval astral-eval experiment --since 7 --strategy headlines-only --no-llm
uv run --package astral-eval astral-eval experiment --dataset golden-week --strategy baseline

# Compare strategies in parallel (separate experiments per strategy)
uv run --package astral-eval astral-eval compare baseline headlines-only --since 7
uv run --package astral-eval astral-eval compare baseline wide-coverage recency-biased --dataset golden-3week --no-llm

# Upload a golden-week dataset for reproducible evals
uv run --package astral-eval astral-eval upload-dataset --since 2026-02-22 --name golden-week

# Upload a multi-week golden set (one row per week)
uv run --package astral-eval astral-eval upload-dataset \
    --since 2026-02-17 --until 2026-03-10 --name golden-3week --multi-week

# Score an existing draft file (heuristic only, optional Braintrust logging)
uv run --package astral-eval astral-eval score data/drafts/draft.json --since 7

# Push hardcoded prompts to Braintrust as initial versions
uv run --package astral-eval astral-eval seed-prompts
uv run --package astral-eval astral-eval seed-prompts --dry-run

# Run the full weekly pipeline (scrape → expand → classify → draft → eval)
scripts/weekly.sh
scripts/weekly.sh --dry-run              # preview mode, minimal LLM cost
scripts/weekly.sh --send                 # include Buttondown delivery
scripts/weekly.sh --since 14             # two-week lookback
scripts/weekly.sh --no-expand            # skip expansion (already expanded)
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
- **Braintrust**: `BRAINTRUST_API_KEY` — optional, enables: (1) automatic trace logging for all LLM calls via `wrap_anthropic`, (2) experiment tracking via `braintrust.EvalAsync()`, (3) golden-week datasets for reproducible evals, (4) versioned prompt loading via `load_prompt()`, (5) online scoring logged to spans, (6) LLM judge routing via AI Proxy (GPT-4o-mini). Install with `uv sync --all-packages --extra braintrust`.
- **Bluesky**: No credentials needed — uses public AT Protocol AppView API.

## Operator workflow

See **`WORKFLOW.md`** for the week-to-week publishing workflow: ingest → author → evaluate → deliver. Also covers Braintrust quality iteration (golden-week datasets, experiments, strategy comparison).

## Skills

Project-local Claude Code skills in `.claude/skills/` automate key development workflows. Invoke with `/<name>` in Claude Code.

### `/publish` — Intelligent Weekly Publishing

Replaces `scripts/weekly.sh` with agent-driven pipeline execution. Runs the full ingest-author-eval-deliver pipeline with quality gates at three checkpoints: strategy selection, quality score threshold, and send confirmation. Supports `--since N`, `--dry-run`, `--send`, `--strategy X`.

### `/iterate` — Quality Improvement Dev Loop

The core build loop: diagnose a weak scorer, propose a targeted change, implement it, run a Braintrust experiment, and keep or revert based on results. Each iteration is atomic (commit on success, revert on failure). Chain multiple runs to compound improvements. Accepts a scorer name, dataset name, or free-text goal.

### `/audit-eval` — Evaluation System QA

Meta-quality check: generates a test draft, runs all scorers, then independently assesses quality to find blind spots (dimensions with no scorer), miscalibrations (scorer disagrees with reality), and silent failures (scorers returning None). Writes `data/eval/audit_report.md` with prioritized improvement targets for `/iterate`.

### `/brainstorm` — Strategic Quality Brainstorming

Read-only analysis: examines source coverage, pipeline stages, strategy configs, and eval gaps. Proposes new sources, pipeline improvements, strategies, and scorers — prioritized by impact and effort. Output feeds into `/iterate` as actionable targets.

### `/autoiterate` — Autonomous Quality Loop

Fully autonomous iteration inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch). Loops: ideate → modify → experiment → keep/revert. No human confirmation gates — runs until interrupted, bounded via `/loop N`, or until a finish condition is met. Each iteration is atomic (commit before verify, revert on regression). Results logged to `data/eval/autoiterate_log.md`.

**Modes:** `--mode single` targets one scorer. `--mode sweep` (default) rotates through all scorers, weakest first, with stuck-detection after 3 consecutive failures.

**Scope:** `--scope author` (default), `prompts`, `strategies`, `eval`, `sources`, or `full` (all of the above). In `full` scope the agent picks the highest-impact lever for each target.

**Finish conditions:** `--until "all scorers above 0.6"`, `--until "average score exceeds 0.75"`, `--until "no scorer below 0.4"`, etc. Evaluated mechanically after each iteration.

**Parallel mode (agent teams):** See `.claude/skills/autoiterate/TEAM.md` for a ready-to-paste prompt that spawns 3 teammates in git worktrees, each trying a different approach. The lead merges the winner each generation. Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (set in `.claude/settings.json`).

### Skill composition

```
/brainstorm ──(ideas)──> /iterate ──(code changes)──> /publish
                              ^                            |
                              |                            |
/audit-eval ──(scorer fixes)──┘       (low scores) ───────┘

/autoiterate ── autonomous loop (serial or parallel via agent teams)
     ├── --mode sweep: rotates through weakest scorers
     ├── --scope full: touches pipeline code, prompts, strategies, eval, sources
     └── --until "condition": stops when quality target is met
```

## Keeping docs current

When adding a new package, feature, or pipeline stage, update these files:

- **`AGENTS.md`** (this file) — add key concepts, CLI commands, and credentials. This is the primary reference for agents working in the codebase.
- **`WORKFLOW.md`** — update if the operator-facing workflow changes (new CLI commands, new pipeline steps, new credentials).
- **`ARCHITECTURE.md`** — update the package breakdown, data flow diagram, and roadmap. This is the high-level design document for humans. Mark completed phases as "Done" and remove "Not yet implemented" / `(TODO)` labels.
- **Package `README.md`** — each package under `packages/` should have a README describing its scorers, commands, workflow, or API surface.

## Design references

The [Space News Scraping Infrastructure](https://www.notion.so/31677391e16b80719cbeefbf3d39d2fd) Notion doc contains the full source-by-source feasibility analysis, content schema rationale, and multi-phase roadmap. Consult it when adding new source types or evolving the pipeline.
