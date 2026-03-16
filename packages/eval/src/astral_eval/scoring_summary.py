"""Weighted score aggregation with quality/structural tiers and floor reporting."""

from __future__ import annotations

from dataclasses import dataclass, field

from .scores import Score

# LLM judges that assess editorial quality
QUALITY_TIER: set[str] = {
    "editorial_quality",
    "summary_faithfulness",
    "summary_informativeness",
    "introduction_quality",
    "coverage_adequacy",
    "readability_fit",
    "coherence_flow",
    "tone_consistency",
    "link_quality",
}

# Heuristic structural checks
STRUCTURAL_TIER: set[str] = {
    "source_diversity",
    "category_coverage",
    "section_balance",
    "semantic_dedup",
    "off_topic_leakage",
    "intro_quality",
    "summary_quality",
    "content_originality",
}

_EXPECTED_QUALITY_COUNT = 9
_EXPECTED_STRUCTURAL_COUNT = 8


@dataclass
class ScoreSummary:
    """Aggregated score summary with tier breakdown and floor reporting."""

    quality_avg: float | None  # None if no quality scorers ran
    structural_avg: float
    weighted_avg: float  # quality 2x, structural 1x
    floor_score: float  # minimum across all scorers
    floor_scorer: str  # name of the worst scorer
    warnings: list[str] = field(default_factory=list)
    quality_count: int = 0
    structural_count: int = 0


def summarize_scores(scores: dict[str, Score]) -> ScoreSummary:
    """Compute weighted average with quality/structural tiers."""
    if not scores:
        return ScoreSummary(
            quality_avg=None,
            structural_avg=0.0,
            weighted_avg=0.0,
            floor_score=0.0,
            floor_scorer="(none)",
            warnings=["No scores provided"],
        )

    quality_scores = [s for name, s in scores.items() if name in QUALITY_TIER]
    structural_scores = [s for name, s in scores.items() if name in STRUCTURAL_TIER]

    warnings: list[str] = []

    # Quality tier
    quality_avg: float | None = None
    if quality_scores:
        quality_avg = sum(s.score for s in quality_scores) / len(quality_scores)
        if len(quality_scores) < _EXPECTED_QUALITY_COUNT:
            warnings.append(
                f"Expected {_EXPECTED_QUALITY_COUNT} quality scorers, "
                f"got {len(quality_scores)}"
            )
    else:
        warnings.append(
            f"Expected {_EXPECTED_QUALITY_COUNT} quality scorers, got 0 — "
            "weighted average uses structural scores only"
        )

    # Structural tier
    structural_avg = (
        sum(s.score for s in structural_scores) / len(structural_scores)
        if structural_scores
        else 0.0
    )
    if len(structural_scores) < _EXPECTED_STRUCTURAL_COUNT:
        warnings.append(
            f"Expected {_EXPECTED_STRUCTURAL_COUNT} structural scorers, "
            f"got {len(structural_scores)}"
        )

    # Weighted average: quality 2x, structural 1x
    if quality_avg is not None:
        weighted_avg = (2 * quality_avg + structural_avg) / 3
    else:
        weighted_avg = structural_avg

    # Floor score
    floor = min(scores.values(), key=lambda s: s.score)

    return ScoreSummary(
        quality_avg=quality_avg,
        structural_avg=round(structural_avg, 3),
        weighted_avg=round(weighted_avg, 3),
        floor_score=round(floor.score, 3),
        floor_scorer=floor.name,
        warnings=warnings,
        quality_count=len(quality_scores),
        structural_count=len(structural_scores),
    )
