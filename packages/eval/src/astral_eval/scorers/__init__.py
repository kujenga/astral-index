"""Newsletter quality scorers."""

from .heuristic import category_coverage, link_count, source_diversity
from .llm_judges import (
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
from .reference_judges import (
    editorial_depth_comparison,
    structural_similarity,
    topic_overlap,
)

__all__ = [
    "category_coverage",
    "coherence_flow",
    "coverage_adequacy",
    "editorial_depth_comparison",
    "editorial_quality",
    "introduction_quality",
    "link_count",
    "link_quality",
    "readability_fit",
    "source_diversity",
    "structural_similarity",
    "summary_faithfulness",
    "summary_informativeness",
    "tone_consistency",
    "topic_overlap",
]
