"""Heuristic (non-LLM) newsletter quality scorers.

Re-exported from ``astral_core.scoring`` where the implementations live.
This keeps backward compatibility for existing imports from ``astral_eval``.
"""

from astral_core.scoring import (
    Score,
    category_coverage,
    intro_quality,
    link_count,
    off_topic_leakage,
    section_balance,
    semantic_dedup,
    source_diversity,
    summary_quality,
)

__all__ = [
    "Score",
    "category_coverage",
    "intro_quality",
    "link_count",
    "off_topic_leakage",
    "section_balance",
    "semantic_dedup",
    "source_diversity",
    "summary_quality",
]
