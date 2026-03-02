"""Tests for LLM judge scorers.

These tests run with API keys cleared (via autouse _no_api_keys fixture)
to verify graceful degradation. They do NOT make real API calls.
"""

from __future__ import annotations

from astral_eval.scorers.llm_judges import (
    _COHERENCE_FLOW_SYSTEM,
    _COVERAGE_ADEQUACY_SYSTEM,
    _EDITORIAL_QUALITY_SYSTEM,
    _LINK_QUALITY_SYSTEM,
    _READABILITY_FIT_SYSTEM,
    coherence_flow,
    coverage_adequacy,
    editorial_quality,
    link_quality,
    readability_fit,
)

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
