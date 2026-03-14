---
name: brainstorm
description: |
  Strategic brainstorming for newsletter quality. Analyzes the pipeline holistically,
  identifies gaps in source coverage, and proposes new features, strategies, and
  scorer dimensions. Use for high-level quality improvement ideas.
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
---

# /brainstorm — Strategic Quality Brainstorming

You are running a strategic brainstorming session for Astral Index. Your job is to analyze the current pipeline holistically and propose high-impact improvements to source coverage, pipeline stages, strategies, and evaluation.

## Arguments

`$ARGUMENTS` may contain a focus area:
- `sources` — focus on source coverage gaps
- `pipeline` — focus on pipeline stage improvements
- `strategies` — focus on new authoring strategies
- `eval` — focus on evaluation system gaps
- (empty) — cover everything

## Step 1: Current State Inventory

Read the following to understand the current state:

```bash
# List configured sources
uv run --package astral-ingest astral-ingest sources

# List available strategies
uv run --package astral-author astral-author strategies
```

Read these files:
- `ARCHITECTURE.md` — roadmap and design overview
- `packages/ingest/src/astral_ingest/sources.yaml` — all configured sources
- `packages/author/src/astral_author/pipeline.py` — strategy definitions

Check for recent drafts and eval results:
```bash
ls -t data/drafts/*.md 2>/dev/null | head -3
ls -t data/eval/*.json 2>/dev/null | head -3
```

If recent drafts or eval results exist, read them for context on current output quality.

## Step 2: Reference Analysis

Read `ARCHITECTURE.md` for the description of The Orbital Index's editorial DNA and the project's aspirations.

Identify gaps between current output and the reference:
- **Link density**: The Orbital Index typically had 15-25 links per issue. How does the current output compare?
- **"Paper of the Week"**: A signature feature — deep technical analysis of one academic paper. Does the current pipeline support this?
- **Technical depth**: Per-item analysis vs. surface-level summaries
- **Editorial voice**: Consistent, knowledgeable, opinionated vs. neutral aggregation
- **Issue consistency**: Predictable structure readers can rely on across hundreds of issues

## Step 3: Source Gap Analysis

Analyze `sources.yaml` for coverage gaps:

### By organization type
- **Space agencies**: NASA, ESA, JAXA — check which are present. Look for missing: ISRO, CNSA/CASC, Roscosmos, KARI, CSA, ASA, UKSA
- **Commercial**: SpaceX, Blue Origin, Rocket Lab, etc. — check blog/press feeds
- **Government/regulatory**: FAA (launch licenses), FCC (spectrum filings), GAO reports
- **Academic**: arXiv, NASA ADS, specific journal RSS feeds

### By geography
- Are non-US/European sources adequately represented?
- Asia-Pacific space programs (JAXA, ISRO, KARI, CNSA)
- Emerging space nations

### By content type
- Launch manifests and schedules
- Financial/investment news (space SPACs, funding rounds)
- Policy and regulatory developments
- Earth observation and climate applications

### Source health
If item data exists, check for sources that produce very few or no items:
```bash
ls data/items/ 2>/dev/null | head -20
```

## Step 4: Pipeline Proposals

For each pipeline stage, propose specific improvements:

### Ranker (`rank.py`)
- Authority-weighted scoring (original reporting > aggregator rewrites)
- Breaking news time bonus (items < 24h old get a boost)
- Source tier system (primary > secondary > aggregator)
- Geographic diversity bonus

### Clusterer (`cluster.py`)
- Cross-category narrative threads (e.g., "Artemis update" spanning policy + launch + science)
- "Paper of the Week" as a dedicated section type
- Configurable section templates per strategy
- Better handling of small categories (the "In Brief" problem)

### Summarizer (`summarize.py`)
- Fact-checking layer (compare summary claims against source text)
- Trend identification (connect current item to previous coverage)
- Technical depth levels (brief/standard/deep for different section types)
- Multi-source synthesis (combine overlapping items into richer summaries)

### Drafter (`draft.py`)
- "In Brief" section with editorial prose (not just bullet points)
- Configurable output formats (full newsletter, digest, breaking-news flash)
- Section-level editorial voice calibration
- Statistics/data callout formatting

### Eval (`scoring.py`, `llm_judges.py`)
- Timeliness scorer (are recent items prioritized appropriately?)
- Factual grounding scorer (do summaries match sources?)
- Information density metric (insight per word)
- Link quality scorer (are links to primary sources, not rewrites?)
- Reader engagement proxy (headline quality, hook effectiveness)

## Step 5: Strategy Proposals

Propose 2-3 new strategies with specific configurations:

### `deep-analysis`
- Fewer items (top 10-15 instead of 20-30)
- Longer prose per item (3-4 sentences instead of 1-2)
- Trend identification enabled
- Higher `min_group_size` to force only strong clusters
- Target audience: industry professionals who want depth

### `breaking-news`
- 24-48h lookback window
- Minimal prose (headline + 1 sentence)
- Aggressive recency weighting (`w_recency` > 0.6)
- Fast turnaround, lower quality bar
- Target audience: people who want to know what happened today

### `research-focus`
- Prioritize arXiv papers and agency technical reports
- "Paper of the Week" section mandatory
- Technical depth setting = deep
- Lower weight on news aggregators
- Target audience: researchers and engineers

For each strategy, specify the config values that would differ from baseline.

## Step 6: Prioritized Output

Rank all proposals by:
- **Impact** (H/M/L) — how much would this improve newsletter quality?
- **Effort** (H/M/L) — how much work to implement?
- **Dependencies** — does this require other changes first?

Format as an actionable list:

```
### High Impact, Low Effort (do first)
1. ...

### High Impact, High Effort (plan for)
2. ...

### Medium Impact, Low Effort (quick wins)
3. ...

### Ideas for Later
4. ...
```

For each item, note which `/iterate` target it maps to (scorer name or pipeline stage).

## Important Notes

- This skill is read-only — it does NOT modify any files or code.
- All output is conversational, presented to the user for decision-making.
- Be specific and actionable. "Improve the ranker" is not useful. "Add a source_tier field to sources.yaml and weight items by tier in rank.py" is.
- Ground proposals in what you actually see in the code, not hypotheticals.
- If you identify a source that should be added, include the actual URL if you can find it in the existing sources.yaml patterns.
