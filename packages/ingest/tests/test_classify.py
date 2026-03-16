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
# Keyword classifier — entertainment / OFF_TOPIC negative signal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "body"),
    [
        ("Photo of the day: aurora over Alaska", None),
        ("Photo of the week: Milky Way over the desert", None),
        ("Stargazing guide for March 2026", None),
        ("Best sci-fi movies about space", None),
        ("Stunning image of the night sky", None),
        ("When to see the Perseid meteor shower", None),
        ("Podcast episode 42: talking about space", None),
        ("How to photograph the aurora borealis", None),
    ],
    ids=[
        "photo_of_the_day",
        "photo_of_the_week",
        "stargazing_guide",
        "scifi_movies",
        "stunning_image",
        "when_to_see",
        "podcast_episode",
        "how_to_photograph",
    ],
)
async def test_entertainment_titles_off_topic(title: str, body: str | None):
    """Entertainment titles with no technical content -> OFF_TOPIC."""
    result = classify_by_keywords(title, body)
    assert result == [SpaceCategory.OFF_TOPIC]


async def test_entertainment_title_with_positive_category_match():
    """Entertainment title that also matches a real category gets the real category."""
    # "JWST" triggers SPACE_SCIENCE, so OFF_TOPIC should NOT appear
    result = classify_by_keywords("Stunning JWST image of distant galaxy")
    assert SpaceCategory.SPACE_SCIENCE in result
    assert SpaceCategory.OFF_TOPIC not in result


async def test_stunning_with_technical_category_not_off_topic():
    """'Stunning' in a title with a real category match -> real category wins."""
    result = classify_by_keywords("Stunning Hubble image of supernova remnant")
    assert SpaceCategory.SPACE_SCIENCE in result
    assert SpaceCategory.OFF_TOPIC not in result


async def test_entertainment_title_with_technical_body_override():
    """Entertainment title + technical body -> no OFF_TOPIC (defer to LLM)."""
    result = classify_by_keywords(
        "Stunning image of the week",
        body="The mission team revealed new data from the experiment.",
    )
    assert result == []


async def test_stunning_jwst_reveals_gets_space_science():
    """'Stunning JWST image reveals...' -> space_science (positive match priority)."""
    result = classify_by_keywords("Stunning JWST image reveals new galaxy formation")
    assert SpaceCategory.SPACE_SCIENCE in result
    assert SpaceCategory.OFF_TOPIC not in result


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------


async def test_llm_no_api_key_returns_none():
    """Without ANTHROPIC_API_KEY (cleared by autouse fixture), returns None."""
    result = await classify_with_llm("SpaceX launch", "An excerpt.")
    assert result is None


async def test_llm_valid_response():
    """Mocked valid API response returns correct SpaceCategory."""
    mock_content = MagicMock()
    mock_content.text = "launch_vehicles"
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("astral_ingest.classify.llm.get_llm_client", return_value=mock_client):
        result = await classify_with_llm("SpaceX Starship orbital test flight")

    assert result == SpaceCategory.LAUNCH_VEHICLES


async def test_llm_invalid_response():
    """Mocked invalid category string returns None."""
    mock_content = MagicMock()
    mock_content.text = "not_a_real_category"
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("astral_ingest.classify.llm.get_llm_client", return_value=mock_client):
        result = await classify_with_llm("Some article")

    assert result is None


async def test_llm_batch_preserves_order():
    """classify_batch_with_llm returns results in input order."""
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

    with patch("astral_ingest.classify.llm.get_llm_client", return_value=mock_client):
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


# ---------------------------------------------------------------------------
# LLM classifier — entertainment content → off_topic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "excerpt"),
    [
        (
            "Astrophotographer spends nearly 70 hours "
            "capturing a delicate blue nebula in Orion (photo)",
            "This stunning deep-sky image required 70 hours "
            "of exposure time across multiple nights.",
        ),
        (
            "Best time to see Mars in the night sky this March",
            "Mars reaches peak visibility this month. Here's when and where to look.",
        ),
        (
            "Looking back at 'Red Dwarf', the sci-fi show "
            "that had a huge impact on my childhood",
            "The classic British sci-fi comedy remains one "
            "of the most beloved space shows ever made.",
        ),
        (
            "The 10 best space photos of the week",
            "From stunning auroras to galaxy close-ups, "
            "here are this week's best space photos.",
        ),
        (
            "Stargazing guide: Jupiter and Saturn conjunction tonight",
            "Head outside after sunset for a rare chance to "
            "see Jupiter and Saturn appear close together.",
        ),
    ],
    ids=[
        "astrophotography",
        "stargazing_guide",
        "scifi_review",
        "photo_gallery",
        "observing_calendar",
    ],
)
async def test_llm_entertainment_classified_as_off_topic(
    title: str,
    excerpt: str,
):
    """Entertainment content should be classified as off_topic."""
    mock_content = MagicMock()
    mock_content.text = "off_topic"
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("astral_ingest.classify.llm.get_llm_client", return_value=mock_client):
        result = await classify_with_llm(title, excerpt)

    assert result == SpaceCategory.OFF_TOPIC

    # Verify the title and excerpt were sent to the LLM
    call_args = mock_client.messages.create.call_args
    user_msg = call_args.kwargs["messages"][-1]["content"]
    assert title in user_msg


async def test_llm_few_shot_includes_entertainment_examples():
    """Verify the few-shot list contains entertainment off_topic examples."""
    from astral_ingest.classify.llm import _FEW_SHOT

    off_topic_user_msgs = [
        _FEW_SHOT[i]["content"]
        for i in range(len(_FEW_SHOT))
        if (
            _FEW_SHOT[i].get("role") == "user"
            and i + 1 < len(_FEW_SHOT)
            and _FEW_SHOT[i + 1].get("content") == "off_topic"
        )
    ]

    # Should have at least 4 off_topic examples (3 entertainment + 1 xkcd)
    assert len(off_topic_user_msgs) >= 4

    # Check specific entertainment patterns are represented
    all_text = " ".join(off_topic_user_msgs).lower()
    assert "astrophotographer" in all_text
    assert "night sky" in all_text
    assert "red dwarf" in all_text


async def test_llm_system_prompt_mentions_entertainment():
    """System prompt should explicitly mention entertainment filtering."""
    from astral_ingest.classify.llm import _SYSTEM_PROMPT

    assert "entertainment" in _SYSTEM_PROMPT.lower()
    assert "astrophotography" in _SYSTEM_PROMPT.lower()
    assert "space technology" in _SYSTEM_PROMPT.lower()
