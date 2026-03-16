"""Tests for the reference comparison judges."""

from __future__ import annotations

import pytest

from astral_eval.scorers.reference_judges import (
    editorial_depth_comparison,
    structural_similarity,
    topic_overlap,
)
from astral_eval.scores import Score


class TestReferenceJudgesSkipWithoutExpected:
    """All reference judges should return None when no expected text is provided."""

    @pytest.fixture
    def output(self) -> dict:
        return {"markdown": "# Newsletter\n\nSome content about space."}

    async def test_topic_overlap_returns_none_without_expected(self, output):
        result = await topic_overlap(output=output, input=[])
        assert result is None

    async def test_topic_overlap_returns_none_with_none_expected(self, output):
        result = await topic_overlap(output=output, input=[], expected=None)
        assert result is None

    async def test_editorial_depth_returns_none_without_expected(self, output):
        result = await editorial_depth_comparison(output=output, input=[])
        assert result is None

    async def test_structural_similarity_returns_none_without_expected(self, output):
        result = await structural_similarity(output=output, input=[])
        assert result is None


class TestReferenceJudgesWithExpected:
    """When expected is provided but no API keys are set, judges return None."""

    @pytest.fixture
    def output(self) -> dict:
        return {"markdown": "# Newsletter\n\nSpaceX launched Starship."}

    @pytest.fixture
    def expected_text(self) -> str:
        return "The Orbital Index covered SpaceX Starship launch this week."

    async def test_topic_overlap_graceful_no_api_key(self, output, expected_text):
        """Without API keys, returns None (not an error)."""
        result = await topic_overlap(output=output, input=[], expected=expected_text)
        # No API key → _judge returns None
        assert result is None

    async def test_editorial_depth_graceful_no_api_key(self, output, expected_text):
        result = await editorial_depth_comparison(
            output=output, input=[], expected=expected_text
        )
        assert result is None

    async def test_structural_similarity_graceful_no_api_key(
        self, output, expected_text
    ):
        result = await structural_similarity(
            output=output, input=[], expected=expected_text
        )
        assert result is None


class TestReferenceJudgeNames:
    """Verify score names use the oi_ prefix."""

    async def test_score_names_have_oi_prefix(self, monkeypatch):
        """When a judge does produce a score, it should use oi_ prefix."""
        from unittest.mock import AsyncMock

        from astral_eval.scorers import reference_judges

        mock_judge = AsyncMock(
            return_value=Score(name="test", score=0.7, metadata={"choice": "B"})
        )
        monkeypatch.setattr(reference_judges, "_judge", mock_judge)

        output = {"markdown": "# Test newsletter"}
        expected = "OI reference text"

        result = await topic_overlap(output=output, input=[], expected=expected)
        assert result is not None
        # _judge was called with oi_ prefixed name
        call_args = mock_judge.call_args
        assert call_args[0][0] == "oi_topic_overlap"


class TestRunnerWithExpected:
    """Test that run_quality_eval properly threads expected to reference scorers."""

    async def test_expected_none_produces_no_reference_scores(
        self, sample_items, make_draft
    ):
        """Without expected, reference scorers return None and are excluded."""
        from astral_eval.runner import run_quality_eval

        draft = make_draft()
        scores = await run_quality_eval(
            draft, sample_items, use_llm=True, expected=None
        )

        # No oi_ prefixed scores should appear
        oi_scores = {k: v for k, v in scores.items() if k.startswith("oi_")}
        assert oi_scores == {}
