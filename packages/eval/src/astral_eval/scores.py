"""Score dataclass and helpers for newsletter quality evaluation."""

from __future__ import annotations

# Re-export Score from core to avoid duplicate definitions
from astral_core.scoring import Score

# A-D rubric mapping used by all LLM judges
CHOICE_SCORES: dict[str, float] = {"A": 1.0, "B": 0.7, "C": 0.4, "D": 0.1}

__all__ = ["CHOICE_SCORES", "Score"]
