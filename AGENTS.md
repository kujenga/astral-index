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

issues/           # git-tracked newsletter staging (one dir per issue date)
└── 2026-03-15/
    ├── draft.md    # human-editable, source of truth for email body
    ├── draft.json  # machine-generated metadata (sections, scores, strategy)
    └── meta.json   # publish state (Buttondown email ID, status)
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
- **Strategies** (`astral_author.pipeline`) — named compositions of stages. "baseline" uses Claude Sonnet for summaries; "headlines-only" uses excerpts only (no LLM); "wide-coverage" uses more deep-dive sections (max_deep_dives=5, min_group_size=1); "recency-biased" weights freshness heavily (w_recency=0.50). **Always use `baseline` (or another LLM-backed strategy) when generating newsletters for review or publication.** The `headlines-only` strategy produces raw, unprocessed excerpts with truncation artifacts, boilerplate, and formatting issues — it exists only for unit testing and fast pipeline validation where output quality doesn't matter.
- **Newsletter models** (`astral_author.models`) — `NewsletterDraft`, `NewsletterSection`, `ItemSummary`, `SectionType` (deep_dive, brief, links).
- **Newsletter staging** (`issues/`) — git-tracked directory for human-in-the-loop review. `astral-author draft` stages output here by default. The markdown (`draft.md`) is the human-editable source of truth; the JSON sidecar (`draft.json`) is machine-generated metadata. `astral-serve draft {date}` reads the edited markdown from staging.
- **Newsletter delivery** (`astral_serve`) — two-step publish via Buttondown API: `draft` creates a remote draft, `send` promotes it. Accepts a date string (reads from `issues/{date}/`) or a JSON file path. State tracked in both `issues/{date}/meta.json` (staging) and `data/newsletters/{YYYY-MM-DD}/meta.json` (Buttondown record).
- **PublishRecord** (`astral_serve.models`) — tracks issue publishing state (draft/sent/failed), Buttondown email ID, and metadata.
- **`get_llm_client`** (`astral_core.llm`) — shared factory returning an `AsyncAnthropic` client (or `None` when `ANTHROPIC_API_KEY` is unset). Instruments the client via the active observability backend (Braintrust tracing, Phoenix OTEL, or noop). All LLM callsites (classifier, summarizer, drafter, eval judges) use this instead of creating clients directly.
- **Quality evaluation** (`astral_eval`) — multi-dimensional newsletter scoring: 8 heuristic scorers (structural tier) + 9 LLM judges (quality tier) + 3 reference comparison judges. Scores are aggregated with weighted averaging: quality tier gets 2x weight, structural tier gets 1x. Floor score (worst individual scorer) is always surfaced. The 5 standard judges (editorial quality, coverage adequacy, readability, link quality, coherence) use GPT-4o-mini via Braintrust AI Proxy (or Claude Haiku fallback) with A–D rubrics. The 4 thinking-mode judges (summary faithfulness, summary informativeness, introduction quality, tone consistency) use Claude Sonnet with extended thinking and 3-call ensemble averaging for reduced variance. The 3 reference judges (oi_topic_overlap, oi_editorial_depth, oi_structural_similarity) compare generated newsletters against The Orbital Index issues for the same week — they require `expected` text and return None when unavailable. Scorers return a `Score` dataclass (0.0–1.0).
- **OI reference cache** (`astral_eval.oi_reference`) — scrapes the OI archive listing, builds a date→URL index, fetches individual issue text via trafilatura, and caches everything locally in `data/oi_reference/`. The `golden-oi` dataset tier uses this to populate the `expected` field for 2025 windows.
- **Score** (`astral_core.scoring`) — lightweight dataclass: `name`, `score` (0.0–1.0), `metadata` dict. Lives in core so both eval and author can import it.
- **Heuristic scorers** (`astral_core.scoring`) — 8 structural scorers live in core (re-exported by `astral_eval.scorers.heuristic` for backward compat): source_diversity, category_coverage, section_balance, semantic_dedup, off_topic_leakage, intro_quality, summary_quality, content_originality. `link_count` was removed from active lists (always 1.0 by construction). This avoids a circular dep so the author pipeline can run online scoring.
- **Eval runner** (`astral_eval.runner`) — `run_quality_eval(draft, items, use_llm=True)` orchestrates heuristic (sync) and LLM (async concurrent) scorers.
- **Experiment runner** (`astral_eval.experiment`) — `run_experiment()` delegates to the active observability backend for tracked experiments. Falls back to local `run_quality_eval()` when no backend is configured.
- **Scorer adapters** (`astral_eval.braintrust_scorers`) — `wrap_scorer()` bridges astral-eval's `(output=, input=)` signature to the experiment backend's scorer interface.
- **Standard datasets** (`astral_eval.datasets`) — four-tier golden datasets for reproducible experiments: `golden-smoke` (1 row, fast sanity check), `golden-standard` (4 rows, default for iteration), `golden-full` (8 rows, CI regression), `golden-oi` (4 rows, 2025-only windows with OI reference text in `expected`). Created via `setup-datasets` command. All CRUD goes through `get_datasets()`.
- **Prompt management** (`astral_core.prompts`) — `load_prompt(slug, fallback)` fetches versioned prompts from Braintrust when available, with zero-change fallback to hardcoded strings. All 4 LLM prompts (item-summarizer, prose-generator, newsletter-intro, category-classifier) use this.
- **Online scoring** — `DraftPipeline.run()` automatically runs heuristic scorers after every draft and logs scores to the current Braintrust span.

### Observability layer

All observability (tracing, prompts, datasets, experiments, LLM proxy) routes through `astral_core.observability`. One env var `ASTRAL_OBSERVABILITY_BACKEND` selects the backend (`auto`/`braintrust`/`phoenix`/`noop`). `auto` (default) detects from env vars. Everything degrades gracefully to noop — hardcoded fallbacks are used and no errors are raised.

**Backends:**
- **Braintrust** — `BRAINTRUST_API_KEY` enables all capabilities. Tracing additionally requires `BRAINTRUST_TRACE=1`. LLM judges route through Braintrust AI Proxy (GPT-4o-mini).
- **Phoenix** — open-source, self-hostable. `PHOENIX_COLLECTOR_ENDPOINT` for OTLP tracing, `PHOENIX_API_URL` for REST API (datasets, experiments, prompts). LLM judges use direct OpenAI when `OPENAI_API_KEY` is set.
- **Noop** — no env vars set. All capabilities return None/empty, callers use their existing fallback paths.

**Touch points — know these when modifying LLM or eval code:**

1. **Tracing** — `get_llm_client()` in `astral_core.llm` delegates to `get_tracing().initialize()` + `instrument_anthropic()`. For Braintrust this calls `init_logger` + `wrap_anthropic`; for Phoenix this calls `phoenix.otel.register()` + `AnthropicInstrumentor().instrument()`. No per-callsite changes needed.
2. **Prompts** — `load_prompt(slug, fallback)` in `astral_core.prompts` delegates to `get_prompts().load_prompt()`, applies fallback in the wrapper. The 4 prompt slugs are: `item-summarizer`, `prose-generator`, `newsletter-intro`, `category-classifier`. When adding a new LLM prompt, add a slug and pass the hardcoded string as `fallback`.
3. **Online scoring** — `DraftPipeline.run()` runs heuristic scorers after every draft and logs via `get_tracing().log_scores()`. The scorers live in `astral_core.scoring` (not `astral_eval`) to avoid a circular dependency.
4. **Experiments** — `run_experiment()` in `astral_eval.experiment` delegates to `get_experiments().run_experiment()`. Falls back to the local `run_quality_eval()` runner when backend is noop.
5. **Scorer adapters** — `wrap_scorer()` in `astral_eval.braintrust_scorers` delegates to `get_experiments().wrap_scorer()`. When adding a new scorer, wrap it and add to `ALL_BT_SCORERS`.
6. **Datasets** — Four standard tiers (`golden-smoke`, `golden-standard`, `golden-full`, `golden-oi`) defined in `STANDARD_DATASETS` in `astral_eval.datasets`. Created via `setup-datasets` CLI command. All CRUD goes through `get_datasets()`.
7. **LLM judges** — 12 total judges (quality tier): 9 intrinsic in `astral_eval.scorers.llm_judges` + 3 reference in `astral_eval.scorers.reference_judges`. The 5 standard judges route through `get_llm_proxy().judge()` (Braintrust AI Proxy or direct OpenAI), falling back to Claude Haiku via Anthropic SDK. The 4 thinking-mode judges use Claude Sonnet with extended thinking and 3-call ensemble median aggregation — Anthropic SDK only, no proxy path. The 3 reference judges (oi_topic_overlap, oi_editorial_depth, oi_structural_similarity) compare against Orbital Index issues and return None when no `expected` text is available. **Score aggregation:** quality tier (LLM judges) gets 2x weight, structural tier (heuristics) gets 1x weight. Floor score (worst scorer) is always surfaced.
8. **CI** — `.github/workflows/eval.yml` runs heuristic evals on PRs touching `packages/author/` or `packages/eval/`. Add the `eval-full` label for LLM judges.

## Public repository

This repo is public. Keep this in mind:

- **Never commit secrets** — API keys, tokens, credentials, and `.env` files must stay out of version control. Use environment variables or untracked config files.
- **Commit messages are visible** — write them as if anyone can read them. No internal shorthand, TODOs referencing private systems, or sloppy language.
- **Code quality matters from the start** — every commit is part of the public history. Prefer clean, intentional commits over fixup noise.
- **Be mindful of scraped data** — `data/` is gitignored for a reason. Don't commit raw content that may have licensing or copyright implications.

## Development

- **`gh` CLI commands require sandbox bypass** — GitHub CLI calls (e.g., `gh pr create`, `gh api`) fail inside the Claude Code sandbox due to TLS certificate verification. Run these with `dangerouslyDisableSandbox: true`.
- Keep implementations simple — avoid premature abstraction
- Always use `uv run` to execute Python commands — never call `python` or `python3` directly
- Workspace packages depend on each other via `tool.uv.sources` (e.g., `astral-core = { workspace = true }` in astral-ingest's pyproject.toml)
- Scraped data lives in `data/` (gitignored) — never commit it

### Shared helpers in `astral_core`

Use these instead of rolling your own:

- **`bootstrap()`** (`astral_core.bootstrap`) — call once at CLI startup. Loads `.env` via `python-dotenv` and silences known-harmless warnings. Every CLI entry point (ingest, author, serve, eval) already calls this.
- **`get_llm_client()`** (`astral_core.llm`) — the **only** way to create an Anthropic client. Returns `AsyncAnthropic` or `None`. Never instantiate `anthropic.AsyncAnthropic` directly — this factory handles API key checks, graceful degradation, and tracing via the active observability backend. When adding a new LLM callsite, import from `astral_core` and check for `None` before calling.
- **`load_prompt(slug, fallback)`** (`astral_core.prompts`) — load a versioned prompt from the active backend, or return the fallback string. Use this for all system prompts sent to LLMs. The fallback is always the hardcoded constant (e.g., `_ITEM_SYSTEM`), so behavior is unchanged without a backend.

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

# Generate a newsletter draft → stages at issues/{date}/draft.md + draft.json
uv run --package astral-author astral-author draft --since 7
uv run --package astral-author astral-author draft --since 7 --dry-run

# headlines-only: raw excerpts, no LLM — for testing/validation only, not publishable output
uv run --package astral-author astral-author draft --since 7 --strategy headlines-only

# Write draft to a custom path instead of issues/ (legacy)
uv run --package astral-author astral-author draft --since 7 --output data/drafts/draft.md

# Compare strategies side-by-side
uv run --package astral-author astral-author compare baseline headlines-only --since 7

# Create a Buttondown draft (reads from issues/{date}/ or a JSON file path)
uv run --package astral-serve astral-serve draft 2026-03-15 --dry-run
uv run --package astral-serve astral-serve draft 2026-03-15
uv run --package astral-serve astral-serve draft data/drafts/draft.json  # legacy file path

# Send a previously drafted newsletter
uv run --package astral-serve astral-serve send 2026-03-15 --dry-run
uv run --package astral-serve astral-serve send 2026-03-15

# View publishing status
uv run --package astral-serve astral-serve status
uv run --package astral-serve astral-serve status 2026-03-01

# Evaluate newsletter quality (needs ANTHROPIC_API_KEY)
uv run --package astral-eval astral-eval quality --since 30

# Evaluate from an existing draft JSON file
uv run --package astral-eval astral-eval quality --since 30 --draft-file data/drafts/draft.json

# Write evaluation results to file
uv run --package astral-eval astral-eval quality --since 30 --output data/eval/results.json

# Run a Braintrust-tracked experiment (needs BRAINTRUST_API_KEY)
uv run --package astral-eval astral-eval experiment --dataset golden-standard

# Compare strategies in parallel (separate experiments per strategy)
uv run --package astral-eval astral-eval compare baseline headlines-only --since 7
uv run --package astral-eval astral-eval compare baseline wide-coverage recency-biased --dataset golden-full

# Create standard dataset tiers (smoke, standard, full) in Braintrust
uv run --package astral-eval astral-eval setup-datasets
uv run --package astral-eval astral-eval setup-datasets --dry-run

# Upload a custom dataset for reproducible evals
uv run --package astral-eval astral-eval upload-dataset --since 2026-02-22 --name my-dataset

# Upload a multi-week custom dataset (one row per week)
uv run --package astral-eval astral-eval upload-dataset \
    --since 2026-02-17 --until 2026-03-10 --name my-multiweek --multi-week

# Score an existing draft file (heuristic only, optional Braintrust logging)
uv run --package astral-eval astral-eval score data/drafts/draft.json --since 7

# Push hardcoded prompts to Braintrust as initial versions
uv run --package astral-eval astral-eval seed-prompts
uv run --package astral-eval astral-eval seed-prompts --dry-run

# Pre-populate the local OI reference cache for golden windows
uv run --package astral-eval astral-eval fetch-oi-reference

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
- **Braintrust**: `BRAINTRUST_API_KEY` — optional, enables: (1) experiment tracking, (2) golden datasets, (3) versioned prompts, (4) online scoring, (5) LLM judge routing via AI Proxy (GPT-4o-mini). Install with `uv sync --all-packages --extra braintrust`. `BRAINTRUST_TRACE=1` — opt-in, enables automatic tracing of all LLM calls (creates spans that count toward free-tier limits; off by default).
- **Phoenix**: `PHOENIX_COLLECTOR_ENDPOINT` — OTLP trace ingest URL (e.g. `http://localhost:6006/v1/traces`). `PHOENIX_API_URL` — REST API base URL for datasets, experiments, prompts (e.g. `http://localhost:6006`). `PHOENIX_API_KEY` — auth token (optional for self-hosted). Open-source, self-hostable, unlimited storage. Install with `uv sync --all-packages --extra phoenix`.
- **Backend selection**: `ASTRAL_OBSERVABILITY_BACKEND` — `auto` (default), `braintrust`, `phoenix`, or `noop`. Auto-detection: `PHOENIX_COLLECTOR_ENDPOINT` → phoenix, `BRAINTRUST_API_KEY` → braintrust, else noop.
- **Cross-model judges**: `OPENAI_API_KEY` — direct OpenAI for LLM judge calls when using Phoenix backend (same GPT-4.1-mini model as Braintrust AI Proxy). Falls back to Claude Haiku when not set.
- **Bluesky**: No credentials needed — uses public AT Protocol AppView API.

## Operator workflow

See **`WORKFLOW.md`** for the week-to-week publishing workflow: ingest → author → evaluate → deliver. Also covers quality iteration with Braintrust or Phoenix (standard datasets, experiments, strategy comparison).

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

**Scope:** `--scope full` (default — lets the agent fix whatever's actually broken), `author`, `prompts`, `strategies`, `eval`, or `sources`. In `full` scope the agent picks the highest-impact lever for each target. **Important:** autoiterate must never modify scorer implementations (`packages/eval/` or `packages/core/src/astral_core/scoring.py`) — scorer improvements require dedicated `/audit-eval` cycles.

**Finish conditions:** `--until "all scorers above 0.6"`, `--until "average score exceeds 0.75"`, `--until "no scorer below 0.4"`, etc. Evaluated mechanically after each iteration.

**Parallel mode:** `--parallel N` spawns N teammates per generation using the Agent tool (`isolation: "worktree"`, `model: "sonnet"`, `run_in_background: true`). The lead ideates N approaches, teammates implement and experiment concurrently in isolated worktrees, lead merges the winner. `--generations G` controls how many rounds (default 3). Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (set in `.claude/settings.json`). See `.claude/skills/autoiterate/TEAM.md` for design rationale and troubleshooting.

### Skill composition

```
/brainstorm ──(ideas)──> /iterate ──(code changes)──> /publish
                              ^                            |
                              |                            |
/audit-eval ──(scorer fixes)──┘       (low scores) ───────┘

/autoiterate ── autonomous loop (serial or parallel)
     ├── --mode sweep: rotates through weakest scorers
     ├── --scope full: touches pipeline code, prompts, strategies, eval, sources
     ├── --until "condition": stops when quality target is met
     └── --parallel 3: spawns 3 Sonnet teammates per generation in worktrees
```

## Keeping docs current

When adding a new package, feature, or pipeline stage, update these files:

- **`AGENTS.md`** (this file) — add key concepts, CLI commands, and credentials. This is the primary reference for agents working in the codebase.
- **`WORKFLOW.md`** — update if the operator-facing workflow changes (new CLI commands, new pipeline steps, new credentials).
- **`ARCHITECTURE.md`** — update the package breakdown, data flow diagram, and roadmap. This is the high-level design document for humans. Mark completed phases as "Done" and remove "Not yet implemented" / `(TODO)` labels.
- **Package `README.md`** — each package under `packages/` should have a README describing its scorers, commands, workflow, or API surface.

## Design references

The [Space News Scraping Infrastructure](https://www.notion.so/31677391e16b80719cbeefbf3d39d2fd) Notion doc contains the full source-by-source feasibility analysis, content schema rationale, and multi-phase roadmap. Consult it when adding new source types or evolving the pipeline.
