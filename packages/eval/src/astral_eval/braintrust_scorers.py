"""Adapter: astral-eval scorers to experiment backend scorer interface.

Delegates ``wrap_scorer()`` to the active observability backend. Kept as a
backward-compat shim so existing imports (``ALL_BT_SCORERS``, etc.) continue
to work.
"""

from __future__ import annotations

from collections.abc import Callable

from astral_core.observability import get_experiments


def wrap_scorer(scorer: Callable, *, name: str | None = None) -> Callable:
    """Wrap an astral-eval scorer for use with the experiment backend."""
    return get_experiments().wrap_scorer(scorer, name=name)


def _make_all() -> dict[str, Callable]:
    """Build wrapped versions of all scorers, imported lazily to avoid cycles."""
    from .scorers.heuristic import (
        category_coverage,
        content_originality,
        intro_quality,
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

    scorers = [
        source_diversity,
        category_coverage,
        section_balance,
        semantic_dedup,
        off_topic_leakage,
        intro_quality,
        summary_quality,
        content_originality,
        editorial_quality,
        coverage_adequacy,
        readability_fit,
        link_quality,
        coherence_flow,
        summary_faithfulness,
        summary_informativeness,
        introduction_quality,
        tone_consistency,
        topic_overlap,
        editorial_depth_comparison,
        structural_similarity,
    ]
    return {f"bt_{s.__name__}": wrap_scorer(s) for s in scorers}


# Pre-built wrapped scorers for direct import
_ALL = _make_all()

bt_source_diversity = _ALL["bt_source_diversity"]
bt_category_coverage = _ALL["bt_category_coverage"]
bt_section_balance = _ALL["bt_section_balance"]
bt_semantic_dedup = _ALL["bt_semantic_dedup"]
bt_off_topic_leakage = _ALL["bt_off_topic_leakage"]
bt_intro_quality = _ALL["bt_intro_quality"]
bt_summary_quality = _ALL["bt_summary_quality"]
bt_content_originality = _ALL["bt_content_originality"]
bt_editorial_quality = _ALL["bt_editorial_quality"]
bt_coverage_adequacy = _ALL["bt_coverage_adequacy"]
bt_readability_fit = _ALL["bt_readability_fit"]
bt_link_quality = _ALL["bt_link_quality"]
bt_coherence_flow = _ALL["bt_coherence_flow"]
bt_summary_faithfulness = _ALL["bt_summary_faithfulness"]
bt_summary_informativeness = _ALL["bt_summary_informativeness"]
bt_introduction_quality = _ALL["bt_introduction_quality"]
bt_tone_consistency = _ALL["bt_tone_consistency"]
bt_topic_overlap = _ALL["bt_topic_overlap"]
bt_editorial_depth_comparison = _ALL["bt_editorial_depth_comparison"]
bt_structural_similarity = _ALL["bt_structural_similarity"]

HEURISTIC_BT_SCORERS = [
    bt_source_diversity,
    bt_category_coverage,
    bt_section_balance,
    bt_semantic_dedup,
    bt_off_topic_leakage,
    bt_intro_quality,
    bt_summary_quality,
    bt_content_originality,
]
LLM_BT_SCORERS = [
    bt_editorial_quality,
    bt_coverage_adequacy,
    bt_readability_fit,
    bt_link_quality,
    bt_coherence_flow,
    bt_summary_faithfulness,
    bt_summary_informativeness,
    bt_introduction_quality,
    bt_tone_consistency,
]
REFERENCE_BT_SCORERS = [
    bt_topic_overlap,
    bt_editorial_depth_comparison,
    bt_structural_similarity,
]
ALL_BT_SCORERS = HEURISTIC_BT_SCORERS + LLM_BT_SCORERS + REFERENCE_BT_SCORERS
