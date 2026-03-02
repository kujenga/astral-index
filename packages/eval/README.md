# astral-eval

Quality evaluation for Astral Index newsletters. Scores newsletter drafts across multiple dimensions using heuristic metrics and LLM judges, providing measurable feedback for iterating on ranker weights, summarizer prompts, and clustering strategies.

## Scorers

Every scorer returns a `Score(name, score, metadata)` where `score` is 0.0-1.0.

### Heuristic (no API key needed)

| Scorer | What it measures | How it scores |
|--------|-----------------|---------------|
| `source_diversity` | Distribution of news sources in the output | Shannon entropy -> Effective Number of Sources (ENS = e^H), scored as `min(1.0, ENS / 5)` |
| `category_coverage` | Whether input categories are represented | Fraction of input categories found in output sections |
| `link_count` | Markdown links per output item | `min(1.0, links / total_output_items)` |

### LLM judges (requires `ANTHROPIC_API_KEY`)

Each judge sends the newsletter markdown to Claude Haiku with an A-D rubric and maps the response to a score (A=1.0, B=0.7, C=0.4, D=0.1). Uses Haiku rather than Sonnet to avoid self-preference bias, since Sonnet generates the drafts.

| Scorer | What it evaluates |
|--------|------------------|
| `editorial_quality` | Voice, sentence variety, filler detection |
| `coverage_adequacy` | Whether the week's important stories are covered (uses input items as context) |
| `readability_fit` | Appropriate tone for space-industry professionals |
| `link_quality` | Claims sourced, descriptive anchor text, primary sources preferred |
| `coherence_flow` | Logical section ordering, narrative arc, transitions |

## CLI usage

```bash
# Heuristic-only eval (free, no API key needed)
uv run --package astral-eval astral-eval quality --since 30 --no-llm

# Full eval with LLM judges
uv run --package astral-eval astral-eval quality --since 30

# Use a specific authoring strategy (default: headlines-only)
uv run --package astral-eval astral-eval quality --since 30 --strategy baseline

# Evaluate an existing draft JSON file
uv run --package astral-eval astral-eval quality --since 30 --draft-file data/drafts/draft.json

# Save results to a file
uv run --package astral-eval astral-eval quality --since 30 --no-llm --output data/eval/results.json
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--since` | `7` | Days back (integer) or start date (YYYY-MM-DD) |
| `--strategy` | `headlines-only` | Authoring strategy for draft generation |
| `--max-items` | `50` | Maximum items to feed the pipeline |
| `--no-llm` | off | Skip LLM judges, run heuristics only |
| `--draft-file` | none | Load a `NewsletterDraft` JSON instead of generating |
| `--output` | none | Write full results JSON to this path |

## Evaluation workflow

A typical iteration cycle:

1. **Generate a draft** with `astral-author`:
   ```bash
   uv run --package astral-author astral-author draft --since 30 --strategy baseline --output data/drafts/draft.md
   ```

2. **Score the draft** against the same input items:
   ```bash
   uv run --package astral-eval astral-eval quality --since 30 --draft-file data/drafts/draft.json
   ```

3. **Compare strategies** by scoring each one:
   ```bash
   uv run --package astral-eval astral-eval quality --since 30 --strategy baseline --output data/eval/baseline.json
   uv run --package astral-eval astral-eval quality --since 30 --strategy headlines-only --output data/eval/headlines.json
   ```

4. **Iterate** - tweak ranker weights, summarizer prompts, or clustering thresholds, then re-score to measure impact.

### Interpreting results

The CLI prints a table like:

```
Scorer                     Score  Details
-----------------------------------------------------------------
category_coverage          0.800  input_cats=5, output_cats=4, missing=['mars']
coherence_flow             0.700  choice=B
coverage_adequacy          1.000  choice=A
editorial_quality          0.700  choice=B
link_count                 1.000  links=12, total_items=10, ratio=1.20
link_quality               0.700  choice=B
readability_fit            1.000  choice=A
source_diversity           0.850  ens=4.25, n_sources=6

Average                    0.844
```

- **Heuristic scores** include diagnostic metadata (ENS value, missing categories, link counts)
- **LLM judge scores** include the letter grade and raw justification text (in `--output` JSON)
- **Average** is a simple mean across all scorers - useful for quick comparison, but individual scores matter more for targeted improvements

## Programmatic usage

```python
from astral_eval.runner import run_quality_eval
from astral_author.pipeline import build_strategy
from astral_core import ContentStore

store = ContentStore()
items = store.list_items(since=since)

pipeline = build_strategy("headlines-only")
draft = await pipeline.run(items)

# All scorers
scores = await run_quality_eval(draft, items)

# Heuristic only (no API key needed)
scores = await run_quality_eval(draft, items, use_llm=False)

for name, score in sorted(scores.items()):
    print(f"{name}: {score.score:.3f}")
```

## Braintrust tracing

When `BRAINTRUST_API_KEY` is set, all LLM calls across the system (classification, summarization, drafting, and eval judges) are automatically traced via `braintrust.wrap_anthropic`. This is handled by the shared `astral_core.get_llm_client()` factory that all callsites use. Install the optional dependency:

```bash
uv sync --all-packages --extra braintrust
```

This logs every LLM call (prompt, response, score) to Braintrust for analysis without any code changes.

## Credentials

| Variable | Required for | Notes |
|----------|-------------|-------|
| `ANTHROPIC_API_KEY` | LLM judges | Judges degrade gracefully (return `None`) without it |
| `BRAINTRUST_API_KEY` | Tracing (optional) | Enables automatic trace logging for all LLM calls system-wide |
