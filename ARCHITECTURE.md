# Architecture

Astral Index is an AI-driven space technology newsletter that monitors hundreds of sources, uses LLMs to summarize and classify content, and publishes a curated weekly digest. It fills the gap left by [The Orbital Index](https://orbitalindex.com/) (350 issues, 2019–2026) — combining that newsletter's editorial DNA (technical breadth, link density, concision) with the automation architecture pioneered by [smol.ai's AI News](https://buttondown.com/ainews).

## Design philosophy

The Orbital Index's core value was **curation and compression** — finding the 15–25 most important items from hundreds of sources weekly and summarizing them with context. That is exactly the task LLMs excel at. The pipeline handles ~80% of the work (scraping, normalization, expansion, classification, summarization), freeing the human editor to focus on the highest-value ~20%: writing lead paragraphs, verifying technical accuracy, and maintaining editorial voice.

Space news produces roughly 30,000–80,000 words daily across all sources — significantly less than AI news (~200,000–300,000 words). This makes the problem more tractable: fewer tokens to process, lower LLM costs, less noise to filter, and a weekly cadence that allows batch processing.

## Three-layer pipeline

The system follows a three-layer architecture adapted from the smol.ai pattern:

```
Sources (RSS, APIs, social)
        │
        ▼
┌─────────────────────────────────────────────────┐
│  Layer 1: INGESTION (astral-ingest)             │
│  scrape → normalize → expand → dedup → classify │
└──────────────────────┬──────────────────────────┘
                       │  ContentItems (JSON)
                       ▼
┌─────────────────────────────────────────────────┐
│  Layer 2: AUTHORING (astral-author)             │
│  cluster → summarize → rank → draft newsletter  │
└──────────────────────┬──────────────────────────┘
                       │  Newsletter draft
                       ▼
┌─────────────────────────────────────────────────┐
│  Layer 3: DELIVERY (astral-serve)               │
│  publish RSS/web → email distribution           │
└─────────────────────────────────────────────────┘
```

## Package breakdown

The monorepo uses [uv workspaces](https://docs.astral.sh/uv/concepts/workspaces/) with each package under `packages/`. All packages share a single lockfile (`uv.lock`) and use `src/` layout.

### `astral-core` — shared models and storage

The foundation layer with zero business logic beyond data modeling.

- **ContentItem** — Pydantic model that every scraper produces. Normalized schema with identity (URL hash ID), content (title, body, excerpt), metadata (author, dates, language), classification (categories, tags), dedup signals (content hash, URL hash), extraction tracking, and source-specific fields (Reddit score, arXiv ID, tweet engagement, Bluesky URI, etc.).
- **ContentStore** — JSON file storage at `data/items/{YYYY-MM-DD}/{id}.json`. One file per item. Simple filesystem-based persistence with date-partitioned directories.
- **Enums** — `ContentType` (article, tweet, reddit_post, arxiv_paper, press_release, pdf_document), `SpaceCategory` (12 categories spanning the full space industry), `ExtractionMethod` (tracks provenance of body text through the pipeline).
- **URL utilities** — normalization (strips tracking params), hashing (SHA-256 truncated to 16 hex chars), content hashing.

This package has no external dependencies beyond Pydantic. Other packages depend on it but it depends on nothing.

### `astral-ingest` — scraping, expansion, and classification

The largest and most active package. Handles everything from raw source fetching through to classified, full-text content items ready for authoring.

**Scrapers** (`scrapers/`) — each implements `BaseScraper.fetch() -> list[ContentItem]`:

| Scraper | Source type | Auth | Notes |
|---------|-----------|------|-------|
| `RSSFeedScraper` | ~25 RSS feeds | None | Conditional GET (ETag/Last-Modified), excerpt vs full-text modes |
| `SNAPIScraper` | Spaceflight News API v4 | None | Articles and blogs endpoints |
| `RedditScraper` | ~8 subreddits | OAuth (asyncpraw) | Score threshold filtering, top comment extraction |
| `ArxivScraper` | 2 astro-ph categories | None | Keyword filtering on title/abstract, feedparser |
| `BlueskyScraper` | ~9 accounts | None | Public AT Protocol AppView API, handle→DID resolution |
| `TwitterScraper` | ~10 accounts | Bearer token | SocialData.tools API, engagement filtering |

**Link expansion** (`expand/`) — three-stage cascade for excerpt-only items:
1. trafilatura (fast, high quality)
2. newspaper4k (fallback, good with news sites)
3. readability-lxml (fallback, DOM-based extraction)

Optional Playwright JS rendering for SPAs. PDF extraction via pdfplumber. Rate limiting and paywall detection built in.

**Classification** (`classify/`) — two-pass category assignment:
1. Keyword regex pass (~70% coverage, zero cost) — pre-compiled patterns with word boundaries for all 12 categories
2. Claude Haiku LLM fallback — few-shot prompt, async with concurrency control

**Dedup** (`dedup.py`) — URL normalization (strips tracking params), content hash comparison, title Levenshtein distance for fuzzy matching.

**CLI** — Click-based with commands: `sources`, `scrape`, `expand`, `classify`, `export`.

### `astral-author` — newsletter generation

Handles Layer 2 of the pipeline via a four-stage architecture with swappable implementations:

- **Rank** (`EngagementRanker`) — scores and selects the top items from the week's ContentItems based on recency, word count, source diversity, and engagement signals.
- **Cluster** (`CategoryClusterer`) — groups scored items into editorial sections by SpaceCategory. Categories with enough items become deep-dive sections; the rest are collected into "In Brief".
- **Summarize** — fills in per-item summaries. `LLMSummarizer` uses Claude Sonnet for editorial prose; `ExcerptSummarizer` uses existing excerpts (no LLM needed).
- **Draft** (`MarkdownDrafter`) — assembles sections into a complete `NewsletterDraft` with rendered markdown, metadata, and pipeline stats.

**Strategies** (`pipeline.py`) — named compositions of the four stages. "baseline" uses Claude Sonnet for summaries; "headlines-only" uses excerpts only. New strategies are registered in the `STRATEGIES` dict.

**Models** — `NewsletterDraft`, `NewsletterSection`, `ItemSummary`, `SectionType` (deep_dive, brief, links). All Pydantic models with JSON serialization for downstream consumption by eval and serve.

**CLI** — `astral-author draft`, `astral-author strategies`, `astral-author compare`.

### `astral-serve` — publishing and delivery

Handles Layer 3 via the Buttondown API with a two-step publish workflow:

- **Draft** — takes a `NewsletterDraft` JSON file, converts it to Buttondown's email format, and creates a remote draft via the API. Returns a `PublishRecord` with the Buttondown email ID.
- **Send** — promotes a previously drafted email from draft to scheduled/sent status.
- **Status** — inspects publishing state for a given date from the local `data/newsletters/{YYYY-MM-DD}/meta.json` tracking file.

**Models** — `PublishRecord` tracks issue state (draft/sent/failed), Buttondown email ID, and metadata.

**CLI** — `astral-serve draft`, `astral-serve send`, `astral-serve status`.

**Planned** — RSS feed generation, static web archive, broader distribution channels.

### `astral-eval` — quality measurement

Provides measurable feedback for iterating on ranker weights, summarizer prompts, and clustering strategies. Scores newsletter drafts across multiple dimensions.

**Heuristic scorers** (zero cost, no API key):
- `source_diversity` — Shannon entropy over source names, scored as Effective Number of Sources / target
- `category_coverage` — fraction of input categories represented in the output
- `link_count` — markdown links per output item

**LLM judges** (Claude Haiku, A-D rubrics):
- `editorial_quality` — voice, sentence variety, filler detection
- `coverage_adequacy` — whether the week's important stories are covered (uses input items as context)
- `readability_fit` — appropriate tone for space-industry audience
- `link_quality` — claims sourced, descriptive anchor text, primary sources preferred
- `coherence_flow` — logical section ordering, narrative arc, transitions

Uses Haiku rather than Sonnet for judging to avoid self-preference bias (Sonnet generates the drafts). Optional Braintrust tracing via `wrap_anthropic` when `BRAINTRUST_API_KEY` is set.

**Architecture** — scorers are standalone functions returning a `Score(name, score, metadata)` dataclass. The runner orchestrates sync heuristic + async concurrent LLM execution. All judges degrade gracefully (return `None`) without API keys.

**CLI** — `astral-eval quality`.

**Planned** — classification accuracy metrics, dedup effectiveness measurement, source health monitoring, Braintrust experiment tracking integration.

## Data flow

```
                    sources.yaml (config)
                         │
    ┌────────────────────┼────────────────────┐
    ▼                    ▼                    ▼
 RSS feeds          Social APIs         Academic feeds
 (25 feeds)      (Bluesky, Twitter,     (arXiv astro-ph)
                  Reddit)
    │                    │                    │
    └────────────────────┼────────────────────┘
                         │
                    scrape (normalize)
                         │
                         ▼
              data/items/{date}/{id}.json
                    (ContentItems)
                         │
               ┌─────────┼─────────┐
               ▼         ▼         ▼
            expand    classify    dedup
               │         │         │
               └─────────┼─────────┘
                         │
                         ▼
              Enriched ContentItems
              (full text, categories,
               dedup flags)
                         │
                         ▼
                  astral-author
              (rank, cluster, summarize,
                  draft newsletter)
                         │
                    ┌────┴────┐
                    ▼         ▼
             astral-serve  astral-eval
             (Buttondown   (heuristic +
              delivery)    LLM judges)
```

## Source coverage

The ingestion layer targets the same source diversity that made The Orbital Index valuable — spanning the full space industry spectrum:

| Category | Sources |
|----------|---------|
| Trade journalism | SpaceNews, Ars Technica Space, NASASpaceflight, Spaceflight Now, Space.com, Payload Space |
| Independent/blog | Universe Today, Behind the Black, Casey Handmer, Centauri Dreams, NASA Watch, EarthSky |
| Agency/institutional | NASA, ESA, JAXA, Nature Astronomy |
| Newsletter/Substack | Parabolic Arc, Jatan's Space, Bad Astronomy, European Spaceflight Newsletter |
| Policy | The Space Review, SpacePolicy Online, Everyday Astronaut |
| Aggregator API | Spaceflight News API (articles + blogs) |
| Social | Bluesky (9 accounts), Twitter/X (10 accounts) |
| Academic | arXiv astro-ph.EP, arXiv astro-ph.IM |
| Community | Reddit (8 subreddits, score-filtered) |

All source configuration lives in `sources.yaml` — add new sources there, not in code.

## Roadmap

Completed phases and planned work:

### Done

- **Phase 1** — Core schema, RSS scraping (25 feeds), SNAPI integration, JSON file storage, CLI, dedup
- **Phase 2** — Reddit scraper, link expansion pipeline (three-stage cascade + Playwright + PDF), enhanced dedup (URL normalization, content hash, title distance)
- **Phase 3** — arXiv scraper, Bluesky scraper, Twitter/X scraper, two-pass category classifier (keyword + LLM)
- **Phase 4** — Authoring pipeline: four-stage architecture (rank → cluster → summarize → draft) with swappable Protocol implementations, named strategies ("baseline" with Claude Sonnet, "headlines-only" with excerpts), Pydantic newsletter models, JSON sidecar output, strategy comparison CLI
- **Phase 5** — Delivery via Buttondown: two-step publish workflow (draft → send), PublishRecord state tracking, CLI for draft/send/status
- **Phase 6 (partial)** — Newsletter quality scoring: 3 heuristic scorers + 5 LLM judges with A-D rubrics, async concurrent runner, CLI, optional Braintrust tracing

### Planned

- **Phase 6 (remaining)** — Classification accuracy metrics, dedup effectiveness measurement, source health monitoring, Braintrust experiment tracking for A/B strategy comparison.
- **Golden-set evaluation against The Orbital Index** — Scrape and store source material for time periods matching actual Orbital Index issues (350 issues, 2019–2026). Generate a newsletter for the same week using `--since`/`--before` to restrict inputs to that window, then evaluate the output against the real issue. This enables reference-based scoring: did we pick the same top stories? How does our summary compare to a human-written one? An LLM judge can compare the two newsletters side-by-side on coverage overlap, editorial quality gap, and information density. Building a corpus of 10–20 golden weeks would give a stable benchmark for measuring strategy improvements — each pipeline change can be scored against the same reference set rather than relying solely on absolute quality rubrics.
- **Delivery expansion** — RSS feed generation, static web archive, broader distribution channels.
- **Ongoing** — Source list expansion (Discord servers, government documents, FAA filings, more agency feeds), editorial voice tuning, anti-hallucination safeguards, fact-checking layers.
