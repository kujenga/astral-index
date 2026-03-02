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

*Not yet implemented.* Will handle Layer 2 of the pipeline:

- **Topic clustering** — group the week's ContentItems into the newsletter's editorial sections (launch vehicles, space science, commercial space, lunar, Mars, Earth observation, policy, international, ISS/stations, defense, satellite comms, deep space)
- **Multi-stage summarization** — recursive summarization following the smol.ai pattern: chunk content, summarize each chunk, then summarize the summaries. Compress a week of content into ~1,500–2,500 words.
- **Parallel pipeline variants** — run 2–4 pipeline instances with different prompts or model configurations, select the best output
- **Newsletter drafting** — produce the Orbital Index's distinctive structure: 2–4 deep-dive paragraphs on top stories, a dense "News in brief" section, curated links, and a closing space image
- **NER and fact-checking** — flag entity names, mission designations, and dates for human verification

### `astral-serve` — publishing and delivery

*Not yet implemented.* Will handle Layer 3:

- **RSS feed generation** — publish the newsletter as an RSS/Atom feed
- **Web frontend** — static site (likely Astro or similar) for the newsletter archive
- **Email delivery** — integration with Buttondown or Resend for subscriber distribution
- **API** — optional REST API for programmatic access to newsletter content and the underlying content store

### `astral-eval` — quality measurement

*Not yet implemented.* Will provide feedback loops for iterating on pipeline quality:

- **Coverage metrics** — are we catching the stories that matter? Compare against manually curated reference sets.
- **Summary quality** — factual accuracy, information density, readability scoring
- **Classification accuracy** — measure keyword vs LLM classifier precision/recall
- **Dedup effectiveness** — false positive/negative rates for duplicate detection
- **Source health** — monitor feed reliability, detect broken/stale sources

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
                  astral-author (TODO)
                  (summarize, cluster,
                   draft newsletter)
                         │
                         ▼
                  astral-serve (TODO)
                  (RSS, web, email)
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

### Planned

- **Phase 4: Authoring pipeline** — Topic clustering, multi-stage recursive summarization, parallel pipeline variants, newsletter draft generation. This is the core LLM-heavy layer that transforms a week of classified ContentItems into a readable newsletter.
- **Phase 5: Delivery** — RSS feed generation, static web archive, email distribution via Buttondown/Resend. The "last mile" from draft to readers.
- **Phase 6: Evaluation and iteration** — Coverage metrics, summary quality scoring, classifier accuracy measurement, source health monitoring. Feedback loops to improve pipeline quality over time.
- **Ongoing** — Source list expansion (Discord servers, government documents, FAA filings, more agency feeds), editorial voice tuning, anti-hallucination safeguards, fact-checking layers.
