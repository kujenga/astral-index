"""Heuristic (non-LLM) newsletter quality scorers.

Re-exported from ``astral_core.scoring`` where the implementations live.
This keeps backward compatibility for existing imports from ``astral_eval``.
"""

from astral_core.scoring import (
    Score,
    category_coverage,
    link_count,
    source_diversity,
)

__all__ = ["Score", "category_coverage", "link_count", "source_diversity"]
