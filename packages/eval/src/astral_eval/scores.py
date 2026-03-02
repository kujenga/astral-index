"""Score dataclass and helpers for newsletter quality evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Score:
    """A single evaluation score, decoupled from any eval framework."""

    name: str
    score: float  # 0.0-1.0
    metadata: dict = field(default_factory=dict)


# A-D rubric mapping used by all LLM judges
CHOICE_SCORES: dict[str, float] = {"A": 1.0, "B": 0.7, "C": 0.4, "D": 0.1}
