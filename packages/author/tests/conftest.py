"""Shared fixtures for astral-author tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from astral_core import ContentItem, ContentType, SpaceCategory
from astral_core.models import url_hash


def _make_item(
    *,
    title: str = "Test Article",
    source_url: str = "https://example.com/article",
    source_name: str = "SpaceNews",
    content_type: ContentType = ContentType.ARTICLE,
    categories: list[SpaceCategory] | None = None,
    body_text: str | None = "Full body text of the article.",
    excerpt: str | None = "Short excerpt.",
    published_at: datetime | None = None,
    reddit_score: int | None = None,
    tweet_engagement: int | None = None,
    word_count: int | None = 500,
) -> ContentItem:
    """Helper to build a ContentItem with sensible defaults."""
    if published_at is None:
        published_at = datetime.now(UTC) - timedelta(hours=6)
    return ContentItem(
        id=url_hash(source_url),
        source_url=source_url,
        content_type=content_type,
        source_name=source_name,
        title=title,
        body_text=body_text,
        excerpt=excerpt,
        published_at=published_at,
        scraped_at=datetime.now(UTC),
        word_count=word_count,
        categories=categories or [],
        url_hash=url_hash(source_url),
    )


@pytest.fixture()
def make_item():
    """Expose the item factory as a fixture."""
    return _make_item


@pytest.fixture()
def sample_items() -> list[ContentItem]:
    """A diverse set of 10 items spanning multiple categories and sources."""
    now = datetime.now(UTC)
    return [
        # Launch — 3 items (enough for a deep-dive)
        _make_item(
            title="SpaceX Starship reaches orbit",
            source_url="https://spacenews.com/starship-orbit",
            source_name="SpaceNews",
            categories=[SpaceCategory.LAUNCH_VEHICLES],
            published_at=now - timedelta(hours=2),
            word_count=800,
        ),
        _make_item(
            title="Rocket Lab Electron launches radar sat",
            source_url="https://spacenews.com/electron-radar",
            source_name="SpaceNews",
            categories=[SpaceCategory.LAUNCH_VEHICLES],
            published_at=now - timedelta(hours=12),
        ),
        _make_item(
            title="Relativity Space tests Terran R engine",
            source_url="https://arstechnica.com/terran-r",
            source_name="Ars Technica",
            categories=[SpaceCategory.LAUNCH_VEHICLES],
            published_at=now - timedelta(hours=18),
        ),
        # Science — 2 items
        _make_item(
            title="JWST finds high-redshift galaxy",
            source_url="https://universetoday.com/jwst-galaxy",
            source_name="Universe Today",
            categories=[SpaceCategory.SPACE_SCIENCE],
            published_at=now - timedelta(hours=4),
            word_count=1200,
        ),
        _make_item(
            title="Hubble spots new exoplanet candidate",
            source_url="https://nasa.gov/hubble-exoplanet",
            source_name="NASA",
            categories=[SpaceCategory.SPACE_SCIENCE],
            published_at=now - timedelta(hours=8),
        ),
        # Commercial — 2 items
        _make_item(
            title="Blue Origin raises $2B funding round",
            source_url="https://spacenews.com/blue-origin-funding",
            source_name="SpaceNews",
            categories=[SpaceCategory.COMMERCIAL_SPACE],
            published_at=now - timedelta(hours=3),
            word_count=600,
        ),
        _make_item(
            title="Virgin Galactic resumes ticket sales",
            source_url="https://space.com/vg-tickets",
            source_name="Space.com",
            categories=[SpaceCategory.COMMERCIAL_SPACE],
            published_at=now - timedelta(hours=20),
        ),
        # Single-item categories (should go to "In Brief")
        _make_item(
            title="NASA Artemis III delay announced",
            source_url="https://nasa.gov/artemis-delay",
            source_name="NASA",
            categories=[SpaceCategory.LUNAR],
            published_at=now - timedelta(hours=5),
        ),
        _make_item(
            title="India ISRO budget increase for 2026",
            source_url="https://spacenews.com/isro-budget",
            source_name="SpaceNews",
            categories=[SpaceCategory.INTERNATIONAL],
            published_at=now - timedelta(hours=10),
        ),
        # Uncategorized (should go to "In Brief")
        _make_item(
            title="Space trivia: fun facts about Mars",
            source_url="https://example.com/trivia-mars",
            source_name="Random Blog",
            categories=[],
            published_at=now - timedelta(days=2),
            body_text=None,
            excerpt="Some fun facts about the red planet.",
            word_count=None,
        ),
    ]
