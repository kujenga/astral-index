"""Quality evaluation runner — orchestrates heuristic and LLM scorers."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from astral_author.models import NewsletterDraft
from astral_core import ContentItem

from .scorers.heuristic import category_coverage, link_count, source_diversity
from .scorers.llm_judges import (
    coherence_flow,
    coverage_adequacy,
    editorial_quality,
    link_quality,
    readability_fit,
)
from .scores import Score

HEURISTIC_SCORERS = [source_diversity, category_coverage, link_count]
LLM_SCORERS = [
    editorial_quality,
    coverage_adequacy,
    readability_fit,
    link_quality,
    coherence_flow,
]
ALL_SCORERS = HEURISTIC_SCORERS + LLM_SCORERS


async def run_quality_eval(
    draft: NewsletterDraft,
    items: list[ContentItem],
    *,
    use_llm: bool = True,
) -> dict[str, Score]:
    """Run selected scorers and collect results.

    Heuristic scorers run synchronously; LLM judges run concurrently via
    asyncio.gather. Scorers that return None are silently skipped.
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
        for scorer in LLM_SCORERS:
            if inspect.iscoroutinefunction(scorer):
                llm_tasks.append(scorer(output=output, input=input_data))

        llm_results = await asyncio.gather(*llm_tasks, return_exceptions=True)
        for result in llm_results:
            if isinstance(result, Score):
                results[result.name] = result
            # Exceptions and None results are silently skipped

    return results
