# astral-eval

Quality evaluation for Astral Index newsletters. Scores newsletter drafts across multiple dimensions using heuristic metrics and LLM judges, providing measurable feedback for iterating on ranker weights, summarizer prompts, and clustering strategies.

Integrates with [Braintrust](https://www.braintrust.dev/) for experiment tracking, golden-week datasets, prompt versioning, and CI/CD quality gates — with full graceful degradation when Braintrust is not configured.

## Scorers

Every scorer returns a `Score(name, score, metadata)` where `score` is 0.0-1.0.

### Heuristic (no API key needed)

| Scorer | What it measures | How it scores |
|--------|-----------------|---------------|
| `source_diversity` | Distribution of news sources in the output | Shannon entropy -> Effective Number of Sources (ENS = e^H), scored as `min(1.0, ENS / 5)` |
| `category_coverage` | Whether input categories are represented | Fraction of input categories found in output sections |
| `link_count` | Markdown links per output item | `min(1.0, links / total_output_items)` |

### LLM judges (requires `BRAINTRUST_API_KEY` or `ANTHROPIC_API_KEY`)

Each judge sends the newsletter markdown to an LLM with an A-D rubric and maps the response to a score (A=1.0, B=0.7, C=0.4, D=0.1).

**Primary path:** GPT-4o-mini via Braintrust AI Proxy (when `BRAINTRUST_API_KEY` is set) — uses a different model family than the Sonnet drafter to avoid self-preference bias.

**Fallback:** Claude Haiku via direct Anthropic SDK (when only `ANTHROPIC_API_KEY` is set).

| Scorer | What it evaluates |
|--------|------------------|
| `editorial_quality` | Voice, sentence variety, filler detection |
| `coverage_adequacy` | Whether the week's important stories are covered (uses input items as context) |
| `readability_fit` | Appropriate tone for space-industry professionals |
| `link_quality` | Claims sourced, descriptive anchor text, primary sources preferred |
| `coherence_flow` | Logical section ordering, narrative arc, transitions |

## CLI usage

### Local quality eval (existing)

```bash
# Heuristic-only eval (free, no API key needed)
uv run --package astral-eval astral-eval quality --since 30 --no-llm

# Full eval with LLM judges
uv run --package astral-eval astral-eval quality --since 30

# Evaluate an existing draft JSON file
uv run --package astral-eval astral-eval quality --since 30 --draft-file data/drafts/draft.json
```

### Braintrust experiments

```bash
# Run a tracked experiment (local fallback if no BRAINTRUST_API_KEY)
uv run --package astral-eval astral-eval experiment --since 7 --strategy headlines-only --no-llm

# Run against a golden-week dataset
uv run --package astral-eval astral-eval experiment --dataset golden-week --strategy baseline

# Compare multiple strategies
uv run --package astral-eval astral-eval compare baseline headlines-only --since 7
```

### Datasets

```bash
# Upload a golden-week dataset for reproducible evals
uv run --package astral-eval astral-eval upload-dataset --since 2026-02-22 --name golden-week

# Use it in experiments
uv run --package astral-eval astral-eval experiment --dataset golden-week --strategy baseline --no-llm
```

### Post-hoc scoring

```bash
# Score an existing draft file (heuristic only)
uv run --package astral-eval astral-eval score data/drafts/draft.json --since 7
```

### Prompt management

```bash
# Push hardcoded prompts to Braintrust (one-time setup)
uv run --package astral-eval astral-eval seed-prompts

# Preview without pushing
uv run --package astral-eval astral-eval seed-prompts --dry-run
```

## Options reference

### `quality` command
| Flag | Default | Description |
|------|---------|-------------|
| `--since` | `7` | Days back (integer) or start date (YYYY-MM-DD) |
| `--strategy` | `headlines-only` | Authoring strategy for draft generation |
| `--max-items` | `50` | Maximum items to feed the pipeline |
| `--no-llm` | off | Skip LLM judges, run heuristics only |
| `--draft-file` | none | Load a `NewsletterDraft` JSON instead of generating |
| `--output` | none | Write full results JSON to this path |

### `experiment` command
| Flag | Default | Description |
|------|---------|-------------|
| `--since` | `7` | Days back or start date |
| `--strategy` | `headlines-only` | Pipeline strategy |
| `--experiment-name` | `{strategy}-{date}` | Braintrust experiment name |
| `--dataset` | none | Braintrust dataset name (overrides local items) |
| `--max-items` | `50` | Maximum items |
| `--no-llm` | off | Skip LLM judges |

## Braintrust integration

When `BRAINTRUST_API_KEY` is set, the eval package integrates with Braintrust in several ways:

1. **Experiment tracking** — `experiment` and `compare` commands log results to Braintrust for dashboard visualization and regression tracking.
2. **Golden-week datasets** — frozen item sets uploaded via `upload-dataset`, enabling reproducible experiments across code changes.
3. **AI Proxy judges** — LLM judges route through the Braintrust AI Proxy (GPT-4o-mini) for cross-model evaluation, avoiding self-preference bias.
4. **Prompt versioning** — all LLM prompts load from Braintrust when available (via `load_prompt()`), enabling A/B testing without code changes.
5. **Online scoring** — the author pipeline logs heuristic scores to the current Braintrust span on every run.
6. **CI/CD** — `.github/workflows/eval.yml` runs heuristic eval on PRs, with optional full eval via `eval-full` label.

All features degrade gracefully — without `BRAINTRUST_API_KEY`, everything falls back to local-only behavior with no errors.

Install Braintrust support:
```bash
uv sync --all-packages --extra braintrust
```

## Credentials

| Variable | Required for | Notes |
|----------|-------------|-------|
| `ANTHROPIC_API_KEY` | LLM judges (fallback) | Used when Braintrust proxy is not available |
| `BRAINTRUST_API_KEY` | Experiments, datasets, prompts, proxy judges, online scoring | Enables full Braintrust integration; all features degrade gracefully without it |
