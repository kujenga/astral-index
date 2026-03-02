# astral-author

Newsletter authoring pipeline for [Astral Index](../../README.md). Turns scraped space news into curated, editorially structured newsletter drafts.

## Architecture

Four-stage pipeline, executed sequentially:

```
ContentItems → Rank → Cluster → Summarize → Draft → NewsletterDraft
```

Each stage is a Python [Protocol](src/astral_author/stages.py) (structural interface), so implementations are swappable without inheritance. Named **strategies** compose stages into reusable pipelines:

| Strategy | Summarizer | LLM required? |
|---|---|---|
| `baseline` | `LLMSummarizer` (Claude Sonnet) | Yes |
| `headlines-only` | `ExcerptSummarizer` (existing excerpts) | No |

### Stages

| Stage | Implementation | What it does |
|---|---|---|
| **Rank** | `EngagementRanker` | Scores items by recency (48h half-life), social engagement, source tier, and content quality. No LLM. |
| **Cluster** | `CategoryClusterer` | Groups by `SpaceCategory`. Top groups (≥2 items) become deep-dive sections; the rest go to "In Brief". |
| **Summarize** | `LLMSummarizer` / `ExcerptSummarizer` | Fills in 1-2 sentence item summaries and optional editorial prose for deep-dive sections. |
| **Draft** | `MarkdownDrafter` | Assembles title, introduction, sections, and closing into rendered markdown. |

### Graceful degradation

The pipeline never hard-fails on a missing API key:

- `LLMSummarizer` falls back to `ExcerptSummarizer` when `ANTHROPIC_API_KEY` is unset.
- `MarkdownDrafter` uses a template introduction if the LLM intro call fails.
- `headlines-only` strategy works fully offline.

## Usage

```bash
# List available strategies
uv run --package astral-author astral-author strategies

# Generate a draft (headlines-only requires no API key)
uv run --package astral-author astral-author draft --since 7 --strategy headlines-only

# Date window: half-open [since, before) interval
uv run --package astral-author astral-author draft --since 2026-02-22 --before 2026-03-01

# Dry run: rank and cluster only, skip summarization
uv run --package astral-author astral-author draft --since 7 --dry-run

# Write output to file (creates .md + .json sidecar)
uv run --package astral-author astral-author draft --since 7 --output data/drafts/draft.md

# Compare strategies side-by-side
uv run --package astral-author astral-author compare baseline headlines-only --since 7
```

### CLI options

**`draft`** — Generate a newsletter draft.

| Option | Default | Description |
|---|---|---|
| `--since` | `7` | Days back (integer) or start date (`YYYY-MM-DD`) |
| `--before` | none | Exclusive upper-bound date (`YYYY-MM-DD`) |
| `--strategy` | `baseline` | Pipeline strategy name |
| `--max-items` | `50` | Maximum items to include |
| `--dry-run` | off | Rank and cluster only |
| `--output` | stdout | Write markdown to file |

**`compare STRATEGY [STRATEGY ...]`** — Run multiple strategies on the same input.

Writes per-strategy `.md` and `.json` files plus a `_comparison.json` summary to `--output-dir` (default `data/drafts/`).

## Models

- **`NewsletterDraft`** — Complete draft with markdown, metadata, and timing.
- **`NewsletterSection`** — One thematic section (deep-dive or brief) with heading, optional prose, and item summaries.
- **`ItemSummary`** — Single item: title, URL, source, summary, relevance score.
- **`SectionType`** — `deep_dive`, `brief`, or `links`.

## Adding a new strategy

1. Implement any stage Protocol (`Ranker`, `Clusterer`, `Summarizer`, or `Drafter`) in a new module.
2. Register a factory in [`pipeline.py`](src/astral_author/pipeline.py):

```python
def _build_my_strategy() -> DraftPipeline:
    return DraftPipeline(
        name="my-strategy",
        ranker=MyCustomRanker(),
        clusterer=CategoryClusterer(),
        summarizer=LLMSummarizer(),
        drafter=MarkdownDrafter(),
    )

STRATEGIES["my-strategy"] = _build_my_strategy
```

3. It's immediately available via CLI: `astral-author draft --strategy my-strategy`

## Testing

```bash
uv run pytest packages/author/tests/ -v
```

Tests use the `headlines-only` strategy (no API key needed) and cover the full pipeline end-to-end, individual stage integration, the strategy registry, CLI commands, and edge cases.
