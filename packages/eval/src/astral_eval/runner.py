"""Quality evaluation runner — orchestrates heuristic and LLM scorers."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from astral_author.models import NewsletterDraft
from astral_core import ContentItem

from .scorers.heuristic import (
    category_coverage,
    content_originality,
    intro_quality,
    link_count,
    off_topic_leakage,
    section_balance,
    semantic_dedup,
    source_diversity,
    summary_quality,
)
from .scorers.llm_judges import (
    coherence_flow,
    coverage_adequacy,
    editorial_quality,
    introduction_quality,
    link_quality,
    readability_fit,
    summary_faithfulness,
    summary_informativeness,
    tone_consistency,
)
from .scorers.reference_judges import (
    editorial_depth_comparison,
    structural_similarity,
    topic_overlap,
)
from .scores import Score

HEURISTIC_SCORERS = [
    source_diversity,
    category_coverage,
    link_count,
    section_balance,
    semantic_dedup,
    off_topic_leakage,
    intro_quality,
    summary_quality,
    content_originality,
]
LLM_SCORERS = [
    editorial_quality,
    coverage_adequacy,
    readability_fit,
    link_quality,
    coherence_flow,
]
THINKING_LLM_SCORERS = [
    summary_faithfulness,
    summary_informativeness,
    introduction_quality,
    tone_consistency,
]
REFERENCE_SCORERS = [
    topic_overlap,
    editorial_depth_comparison,
    structural_similarity,
]
ALL_SCORERS = HEURISTIC_SCORERS + LLM_SCORERS + THINKING_LLM_SCORERS + REFERENCE_SCORERS


async def run_quality_eval(
    draft: NewsletterDraft,
    items: list[ContentItem],
    *,
    use_llm: bool = True,
    expected: str | None = None,
) -> dict[str, Score]:
    """Run selected scorers and collect results.

    Heuristic scorers run synchronously; LLM judges run concurrently via
    asyncio.gather. Scorers that return None are silently skipped.

    When ``expected`` is provided (OI reference text), reference comparison
    judges are included in the LLM judge batch.
    """
    output = draft.model_dump(mode="json")
    input_data: list[dict[str, Any]] = [item.model_dump(mode="json") for item in items]

    results: dict[str, Score] = {}

    # Run heuristic scorers (sync)
    for scorer in HEURISTIC_SCORERS:
        score = scorer(output=output, input=input_data)
        if score is not None:
            results[score.name] = score

    # Run LLM judges (async, concurrent)
    if use_llm:
        llm_tasks = []
        scorers_to_run = LLM_SCORERS + THINKING_LLM_SCORERS + REFERENCE_SCORERS
        for scorer in scorers_to_run:
            if inspect.iscoroutinefunction(scorer):
                llm_tasks.append(
                    scorer(output=output, input=input_data, expected=expected)
                )

        llm_results = await asyncio.gather(*llm_tasks, return_exceptions=True)
        for result in llm_results:
            if isinstance(result, Score):
                results[result.name] = result
            # Exceptions and None results are silently skipped

    return results
