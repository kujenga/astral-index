"""Tests for weighted score aggregation and floor reporting."""

from __future__ import annotations

import pytest

from astral_eval.scores import Score
from astral_eval.scoring_summary import (
    QUALITY_TIER,
    STRUCTURAL_TIER,
    summarize_scores,
)


def _score(name: str, value: float) -> Score:
    return Score(name=name, score=value)


class TestSummarizeScoresAllPresent:
    """All quality + structural scorers present."""

    def test_weighted_avg_math(self):
        scores = {
            # Quality tier (9 scorers)
            "editorial_quality": _score("editorial_quality", 0.7),
            "summary_faithfulness": _score("summary_faithfulness", 0.7),
            "summary_informativeness": _score("summary_informativeness", 0.7),
            "introduction_quality": _score("introduction_quality", 0.7),
            "coverage_adequacy": _score("coverage_adequacy", 0.7),
            "readability_fit": _score("readability_fit", 0.7),
            "coherence_flow": _score("coherence_flow", 0.7),
            "tone_consistency": _score("tone_consistency", 0.7),
            "link_quality": _score("link_quality", 0.7),
            # Structural tier (8 scorers)
            "source_diversity": _score("source_diversity", 0.4),
            "category_coverage": _score("category_coverage", 0.4),
            "section_balance": _score("section_balance", 0.4),
            "semantic_dedup": _score("semantic_dedup", 0.4),
            "off_topic_leakage": _score("off_topic_leakage", 0.4),
            "intro_quality": _score("intro_quality", 0.4),
            "summary_quality": _score("summary_quality", 0.4),
            "content_originality": _score("content_originality", 0.4),
        }
        summary = summarize_scores(scores)

        assert summary.quality_avg == pytest.approx(0.7)
        assert summary.structural_avg == pytest.approx(0.4)
        # weighted = (2 * 0.7 + 0.4) / 3 = 0.6
        assert summary.weighted_avg == pytest.approx(0.6, abs=0.001)
        assert summary.quality_count == 9
        assert summary.structural_count == 8
        assert summary.warnings == []

    def test_floor_score_identified(self):
        scores = {
            "editorial_quality": _score("editorial_quality", 0.9),
            "source_diversity": _score("source_diversity", 0.2),
            "section_balance": _score("section_balance", 0.8),
        }
        summary = summarize_scores(scores)
        assert summary.floor_score == pytest.approx(0.2)
        assert summary.floor_scorer == "source_diversity"


class TestSummarizeScoresHeuristicOnly:
    """No quality scorers — heuristic-only run."""

    def test_quality_none_and_warning(self):
        scores = {
            "source_diversity": _score("source_diversity", 0.8),
            "section_balance": _score("section_balance", 0.6),
        }
        summary = summarize_scores(scores)

        assert summary.quality_avg is None
        assert summary.quality_count == 0
        # weighted_avg falls back to structural
        assert summary.weighted_avg == summary.structural_avg
        assert any("quality scorers, got 0" in w for w in summary.warnings)


class TestSummarizeScoresEmpty:
    def test_empty_scores(self):
        summary = summarize_scores({})
        assert summary.quality_avg is None
        assert summary.structural_avg == 0.0
        assert summary.weighted_avg == 0.0
        assert summary.floor_score == 0.0
        assert summary.floor_scorer == "(none)"
        assert len(summary.warnings) > 0


class TestTierMembership:
    """Sanity check that tier sets cover expected scorer names."""

    def test_quality_tier_count(self):
        assert len(QUALITY_TIER) == 9

    def test_structural_tier_count(self):
        assert len(STRUCTURAL_TIER) == 8

    def test_no_overlap(self):
        assert set() == QUALITY_TIER & STRUCTURAL_TIER
