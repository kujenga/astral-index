"""Tests for ranker content filtering (NON_INFORMATIONAL_RE)."""

from __future__ import annotations

import pytest

from astral_author.rank import EngagementRanker
from astral_core import SpaceCategory


@pytest.mark.asyncio
async def test_ranker_filters_entertainment_items(make_item) -> None:
    """Items with entertainment titles are excluded by the ranker."""
    items = [
        make_item(
            title="SpaceX launches Starship on orbital test",
            source_url="https://spacenews.com/starship",
            categories=[SpaceCategory.LAUNCH_VEHICLES],
        ),
        make_item(
            title="Stunning image of Jupiter captured by Hubble",
            source_url="https://example.com/jupiter-photo",
            categories=[SpaceCategory.SPACE_SCIENCE],
        ),
        make_item(
            title="Best sci-fi movies set in space this year",
            source_url="https://example.com/scifi-movies",
            categories=[SpaceCategory.SPACE_SCIENCE],
        ),
        make_item(
            title="Stargazing guide for March: planets and meteors",
            source_url="https://example.com/stargazing",
            categories=[SpaceCategory.SPACE_SCIENCE],
        ),
    ]
    ranker = EngagementRanker()
    ranked = await ranker.rank(items, max_items=50)
    titles = [item.title for item, _ in ranked]

    assert "SpaceX launches Starship on orbital test" in titles
    assert "Stunning image of Jupiter captured by Hubble" not in titles
    assert "Best sci-fi movies set in space this year" not in titles
    assert "Stargazing guide for March: planets and meteors" not in titles


@pytest.mark.asyncio
async def test_ranker_keeps_technical_content(make_item) -> None:
    """Technical space content passes through the ranker."""
    items = [
        make_item(
            title="NASA selects new lunar lander design",
            source_url="https://nasa.gov/lander",
            categories=[SpaceCategory.LUNAR],
        ),
        make_item(
            title="JWST discovers high-redshift galaxy at z=14",
            source_url="https://nasa.gov/jwst-galaxy",
            categories=[SpaceCategory.SPACE_SCIENCE],
        ),
    ]
    ranker = EngagementRanker()
    ranked = await ranker.rank(items, max_items=50)
    titles = [item.title for item, _ in ranked]

    assert len(titles) == 2
    assert "NASA selects new lunar lander design" in titles
    assert "JWST discovers high-redshift galaxy at z=14" in titles
