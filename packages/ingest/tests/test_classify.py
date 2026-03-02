"""Tests for keyword and LLM classification pipelines."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astral_core import SpaceCategory
from astral_ingest.classify.keywords import classify_by_keywords
from astral_ingest.classify.llm import (
    classify_batch_with_llm,
    classify_with_llm,
)

# ---------------------------------------------------------------------------
# Keyword classifier — parametrized over all 12 categories
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected_category"),
    [
        ("SpaceX Falcon 9 rocket launches Starlink", SpaceCategory.LAUNCH_VEHICLES),
        ("JWST discovers high-redshift galaxy", SpaceCategory.SPACE_SCIENCE),
        ("Blue Origin raises $2B funding round", SpaceCategory.COMMERCIAL_SPACE),
        ("NASA Artemis III lunar lander update", SpaceCategory.LUNAR),
        ("Perseverance Mars rover finds organics", SpaceCategory.MARS),
        ("Sentinel satellite Earth observation data", SpaceCategory.EARTH_OBSERVATION),
        ("NASA budget cuts to space policy programs", SpaceCategory.POLICY),
        ("JAXA announces new mission", SpaceCategory.INTERNATIONAL),
        ("ISS spacewalk completed successfully", SpaceCategory.ISS_STATIONS),
        ("Space Force launches classified payload", SpaceCategory.DEFENSE_SPACE),
        ("Starlink satellite internet expansion", SpaceCategory.SATELLITE_COMMS),
        ("Voyager probe enters interstellar space", SpaceCategory.DEEP_SPACE),
    ],
    ids=[c.value for c in SpaceCategory if c != SpaceCategory.OFF_TOPIC],
)
async def test_keyword_classifier_all_categories(
    title: str,
    expected_category: SpaceCategory,
):
    result = classify_by_keywords(title)
    assert expected_category in result


async def test_keyword_multi_category():
    """Title triggering 2+ categories."""
    title = "SpaceX Falcon 9 rocket launches Starlink satellites"
    result = classify_by_keywords(title)
    assert SpaceCategory.LAUNCH_VEHICLES in result
    assert SpaceCategory.SATELLITE_COMMS in result


async def test_keyword_no_match():
    """Generic title with no space keywords returns []."""
    result = classify_by_keywords("Local weather forecast for Tuesday")
    assert result == []


async def test_keyword_body_fallback():
    """Keywords in body text get picked up when title has no match."""
    result = classify_by_keywords(
        "Breaking news today",
        body="The James Webb Space Telescope discovered a new exoplanet.",
    )
    assert SpaceCategory.SPACE_SCIENCE in result


async def test_keyword_body_prefix_limit():
    """Only the first 2000 chars of body are checked."""
    # "exoplanet" at position > 2000 should not match
    body = "x " * 1050 + "exoplanet discovery"
    result = classify_by_keywords("Unrelated title", body=body)
    assert SpaceCategory.SPACE_SCIENCE not in result


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------


async def test_llm_no_api_key_returns_none():
    """Without ANTHROPIC_API_KEY (cleared by autouse fixture), returns None."""
    result = await classify_with_llm("SpaceX launch", "An excerpt.")
    assert result is None


async def test_llm_valid_response(monkeypatch):
    """Mocked valid API response returns correct SpaceCategory."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_content = MagicMock()
    mock_content.text = "launch_vehicles"
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await classify_with_llm("SpaceX Starship orbital test flight")

    assert result == SpaceCategory.LAUNCH_VEHICLES


async def test_llm_invalid_response(monkeypatch):
    """Mocked invalid category string returns None."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_content = MagicMock()
    mock_content.text = "not_a_real_category"
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await classify_with_llm("Some article")

    assert result is None


async def test_llm_batch_preserves_order(monkeypatch):
    """classify_batch_with_llm returns results in input order."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    responses = ["launch_vehicles", "space_science", "lunar"]

    call_count = 0

    async def _mock_create(**kwargs):
        nonlocal call_count
        mock_content = MagicMock()
        mock_content.text = responses[call_count]
        call_count += 1
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        return mock_response

    mock_client = AsyncMock()
    mock_client.messages.create = _mock_create

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        items = [
            ("Falcon 9 launch", "excerpt1"),
            ("JWST galaxy discovery", "excerpt2"),
            ("Artemis lunar lander", "excerpt3"),
        ]
        results = await classify_batch_with_llm(items)

    assert len(results) == 3
    assert results[0] == SpaceCategory.LAUNCH_VEHICLES
    assert results[1] == SpaceCategory.SPACE_SCIENCE
    assert results[2] == SpaceCategory.LUNAR
