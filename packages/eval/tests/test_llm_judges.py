"""Tests for LLM judge scorers.

These tests run with API keys cleared (via autouse _no_api_keys fixture)
to verify graceful degradation. They do NOT make real API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from astral_eval.scorers.llm_judges import (
    _COHERENCE_FLOW_SYSTEM,
    _COVERAGE_ADEQUACY_SYSTEM,
    _EDITORIAL_QUALITY_SYSTEM,
    _INTRODUCTION_QUALITY_SYSTEM,
    _LINK_QUALITY_SYSTEM,
    _READABILITY_FIT_SYSTEM,
    _SUMMARY_FAITHFULNESS_SYSTEM,
    _SUMMARY_INFORMATIVENESS_SYSTEM,
    _TECHNICAL_FOCUS_SYSTEM,
    _TONE_CONSISTENCY_SYSTEM,
    _ensemble_judge,
    _judge_thinking,
    coherence_flow,
    coverage_adequacy,
    editorial_quality,
    introduction_quality,
    link_quality,
    readability_fit,
    summary_faithfulness,
    summary_informativeness,
    technical_focus,
    tone_consistency,
)
from astral_eval.scores import Score

# -- Graceful degradation (no API keys) --


class TestGracefulDegradation:
    """All judges return None when no API key is available."""

    async def test_editorial_quality_returns_none(self):
        result = await editorial_quality(output={"markdown": "test"})
        assert result is None

    async def test_coverage_adequacy_returns_none(self):
        result = await coverage_adequacy(output={"markdown": "test"}, input=[])
        assert result is None

    async def test_readability_fit_returns_none(self):
        result = await readability_fit(output={"markdown": "test"})
        assert result is None

    async def test_link_quality_returns_none(self):
        result = await link_quality(output={"markdown": "test"})
        assert result is None

    async def test_coherence_flow_returns_none(self):
        result = await coherence_flow(output={"markdown": "test"})
        assert result is None

    async def test_summary_faithfulness_returns_none(self):
        result = await summary_faithfulness(output={"markdown": "test"})
        assert result is None

    async def test_summary_informativeness_returns_none(self):
        result = await summary_informativeness(output={"markdown": "test"})
        assert result is None

    async def test_introduction_quality_returns_none(self):
        result = await introduction_quality(
            output={"markdown": "test", "introduction": "Hello"}
        )
        assert result is None

    async def test_tone_consistency_returns_none(self):
        result = await tone_consistency(output={"markdown": "test"})
        assert result is None

    async def test_technical_focus_returns_none(self):
        result = await technical_focus(output={"markdown": "test"})
        assert result is None

    async def test_technical_focus_with_sections_returns_none(self):
        result = await technical_focus(
            output={
                "markdown": "test",
                "sections": [
                    {"items": [{"title": "SpaceX launch"}, {"title": "Mars rover"}]}
                ],
            }
        )
        assert result is None


# -- Prompt templates --


class TestPromptTemplates:
    """Verify prompt templates are non-empty and contain key terms."""

    def test_editorial_quality_prompt(self):
        assert len(_EDITORIAL_QUALITY_SYSTEM) > 50
        assert "editorial" in _EDITORIAL_QUALITY_SYSTEM.lower()

    def test_coverage_adequacy_prompt(self):
        assert len(_COVERAGE_ADEQUACY_SYSTEM) > 50
        assert "coverage" in _COVERAGE_ADEQUACY_SYSTEM.lower()

    def test_readability_fit_prompt(self):
        assert len(_READABILITY_FIT_SYSTEM) > 50
        assert "readability" in _READABILITY_FIT_SYSTEM.lower()

    def test_link_quality_prompt(self):
        assert len(_LINK_QUALITY_SYSTEM) > 50
        assert "link" in _LINK_QUALITY_SYSTEM.lower()

    def test_coherence_flow_prompt(self):
        assert len(_COHERENCE_FLOW_SYSTEM) > 50
        assert "coherence" in _COHERENCE_FLOW_SYSTEM.lower()

    def test_summary_faithfulness_prompt(self):
        assert len(_SUMMARY_FAITHFULNESS_SYSTEM) > 50
        assert "faithful" in _SUMMARY_FAITHFULNESS_SYSTEM.lower()

    def test_summary_informativeness_prompt(self):
        assert len(_SUMMARY_INFORMATIVENESS_SYSTEM) > 50
        assert "informative" in _SUMMARY_INFORMATIVENESS_SYSTEM.lower()

    def test_introduction_quality_prompt(self):
        assert len(_INTRODUCTION_QUALITY_SYSTEM) > 50
        assert "introduction" in _INTRODUCTION_QUALITY_SYSTEM.lower()
        # Verify updated rubric evaluates substance / tl;dr value
        assert "substance" in _INTRODUCTION_QUALITY_SYSTEM.lower()
        assert "tl;dr" in _INTRODUCTION_QUALITY_SYSTEM.lower()

    def test_technical_focus_prompt(self):
        assert len(_TECHNICAL_FOCUS_SYSTEM) > 50
        assert "technical" in _TECHNICAL_FOCUS_SYSTEM.lower()
        assert "entertainment" in _TECHNICAL_FOCUS_SYSTEM.lower()

    def test_tone_consistency_prompt(self):
        assert len(_TONE_CONSISTENCY_SYSTEM) > 50
        assert "tone" in _TONE_CONSISTENCY_SYSTEM.lower()


# -- Thinking-mode judge parsing --


class TestJudgeThinking:
    """Test _judge_thinking response parsing."""

    async def test_extracts_text_block_skipping_thinking(self):
        """Verify that thinking blocks are skipped and text block is parsed."""
        mock_thinking_block = type(
            "ThinkingBlock", (), {"type": "thinking", "thinking": "reasoning..."}
        )()
        mock_text_block = type(
            "TextBlock", (), {"type": "text", "text": "B — mostly faithful"}
        )()
        mock_response = type(
            "Response", (), {"content": [mock_thinking_block, mock_text_block]}
        )()

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch(
            "astral_eval.scorers.llm_judges.get_llm_client",
            return_value=mock_client,
        ):
            result = await _judge_thinking("test_judge", "system", "user content")

        assert result is not None
        assert result.name == "test_judge"
        assert result.score == 0.7  # B
        assert result.metadata["choice"] == "B"

    async def test_returns_none_when_no_client(self):
        """No API key → None."""
        result = await _judge_thinking("test", "sys", "user")
        assert result is None


# -- Ensemble judge --


class TestEnsembleJudge:
    """Test _ensemble_judge median aggregation."""

    async def test_median_selection_odd(self):
        """With scores B, A, C the median should be B (0.7)."""
        scores = [
            Score(name="x", score=0.7, metadata={"choice": "B"}),
            Score(name="x", score=1.0, metadata={"choice": "A"}),
            Score(name="x", score=0.4, metadata={"choice": "C"}),
        ]
        call_count = 0

        async def mock_thinking(name, system, user_content, *, model=None):
            nonlocal call_count
            result = scores[call_count]
            call_count += 1
            return result

        with patch(
            "astral_eval.scorers.llm_judges._judge_thinking",
            side_effect=mock_thinking,
        ):
            result = await _ensemble_judge("test", "sys", "user", n=3)

        assert result is not None
        assert result.score == 0.7
        assert result.metadata["choice"] == "B"
        assert result.metadata["ensemble_size"] == 3
        assert result.metadata["all_scores"] == [0.4, 0.7, 1.0]
        assert result.metadata["all_choices"] == ["C", "B", "A"]
        assert result.metadata["aggregation"] == "median"

    async def test_all_none_returns_none(self):
        """If all calls fail, ensemble returns None."""

        async def mock_thinking(name, system, user_content, *, model=None):
            return None

        with patch(
            "astral_eval.scorers.llm_judges._judge_thinking",
            side_effect=mock_thinking,
        ):
            result = await _ensemble_judge("test", "sys", "user", n=3)

        assert result is None

    async def test_partial_failures_still_work(self):
        """If 1 of 3 calls fails, median is computed from the remaining 2."""
        call_count = 0

        async def mock_thinking(name, system, user_content, *, model=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return None
            return Score(
                name="x",
                score=0.7 if call_count == 1 else 1.0,
                metadata={"choice": "B" if call_count == 1 else "A"},
            )

        with patch(
            "astral_eval.scorers.llm_judges._judge_thinking",
            side_effect=mock_thinking,
        ):
            result = await _ensemble_judge("test", "sys", "user", n=3)

        assert result is not None
        # 2 scores: [0.7, 1.0] → median is index 1 → 1.0
        assert result.score in (0.7, 1.0)

    async def test_zero_scores_excluded(self):
        """Scores of 0.0 (parse failures) are excluded from median."""

        async def mock_thinking(name, system, user_content, *, model=None):
            return Score(name="x", score=0.0, metadata={"error": "no_choice_found"})

        with patch(
            "astral_eval.scorers.llm_judges._judge_thinking",
            side_effect=mock_thinking,
        ):
            result = await _ensemble_judge("test", "sys", "user", n=3)

        assert result is None
