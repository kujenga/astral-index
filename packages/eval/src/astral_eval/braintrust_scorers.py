"""Adapter layer bridging astral-eval scorers to Braintrust Eval's scorer interface.

Braintrust scorers expect ``(input, output, expected=None, **kwargs) -> Score``.
Our scorers use ``(*, output: dict, input: list[dict], **kwargs) -> Score | None``.
``wrap_scorer()`` bridges these signatures.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from .scores import Score


def wrap_scorer(scorer: Callable[..., Any], *, name: str | None = None) -> Callable:
    """Wrap an astral-eval scorer for use with ``braintrust.Eval()``.

    The returned function accepts Braintrust's ``(input, output, **kwargs)``
    signature and returns a dict with ``name``, ``score``, and ``metadata``.
    """
    scorer_name = name or getattr(scorer, "__name__", "unknown")
    is_async = inspect.iscoroutinefunction(scorer)

    async def _bt_scorer(
        input: Any, output: Any, expected: Any = None, **kwargs: Any
    ) -> dict[str, Any] | None:
        # Our scorers expect keyword-only output= and input=
        if is_async:
            result: Score | None = await scorer(output=output, input=input)
        else:
            result = scorer(output=output, input=input)

        if result is None:
            return None

        return {
            "name": result.name,
            "score": result.score,
            "metadata": result.metadata,
        }

    _bt_scorer.__name__ = f"bt_{scorer_name}"
    _bt_scorer.__qualname__ = f"bt_{scorer_name}"
    return _bt_scorer


def _make_all() -> dict[str, Callable]:
    """Build wrapped versions of all scorers, imported lazily to avoid cycles."""
    from .scorers.heuristic import category_coverage, link_count, source_diversity
    from .scorers.llm_judges import (
        coherence_flow,
        coverage_adequacy,
        editorial_quality,
        link_quality,
        readability_fit,
    )

    scorers = [
        source_diversity,
        category_coverage,
        link_count,
        editorial_quality,
        coverage_adequacy,
        readability_fit,
        link_quality,
        coherence_flow,
    ]
    return {f"bt_{s.__name__}": wrap_scorer(s) for s in scorers}


# Pre-built wrapped scorers for direct import
_ALL = _make_all()

bt_source_diversity = _ALL["bt_source_diversity"]
bt_category_coverage = _ALL["bt_category_coverage"]
bt_link_count = _ALL["bt_link_count"]
bt_editorial_quality = _ALL["bt_editorial_quality"]
bt_coverage_adequacy = _ALL["bt_coverage_adequacy"]
bt_readability_fit = _ALL["bt_readability_fit"]
bt_link_quality = _ALL["bt_link_quality"]
bt_coherence_flow = _ALL["bt_coherence_flow"]

HEURISTIC_BT_SCORERS = [bt_source_diversity, bt_category_coverage, bt_link_count]
LLM_BT_SCORERS = [
    bt_editorial_quality,
    bt_coverage_adequacy,
    bt_readability_fit,
    bt_link_quality,
    bt_coherence_flow,
]
ALL_BT_SCORERS = HEURISTIC_BT_SCORERS + LLM_BT_SCORERS
