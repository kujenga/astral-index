"""Shared fixtures for astral-ingest tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from astral_core import (
    ContentItem,
    ContentStore,
    ContentType,
    ExtractionMethod,
    SpaceCategory,
)
from astral_core.models import content_hash, url_hash

# ---------------------------------------------------------------------------
# Canned data constants
# ---------------------------------------------------------------------------

MINIMAL_RSS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>SpaceNews</title>
    <item>
      <title>SpaceX Falcon 9 launches Starlink batch</title>
      <link>https://spacenews.com/falcon9-starlink</link>
      <description>SpaceX launched another batch of Starlink satellites.</description>
      <pubDate>Sat, 01 Mar 2026 10:00:00 GMT</pubDate>
      <author>Jeff Foust</author>
    </item>
    <item>
      <title>Rocket Lab Electron reaches orbit</title>
      <link>https://spacenews.com/electron-orbit</link>
      <description>&lt;p&gt;Rocket Lab launched its Electron.&lt;/p&gt;</description>
      <pubDate>Fri, 28 Feb 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>No link entry</title>
    </item>
  </channel>
</rss>
"""

SAMPLE_HTML_ARTICLE = """\
<html><head><title>Test Article</title></head>
<body>
<article>
<h1>SpaceX Starship Completes Orbital Test</h1>
<p>SpaceX's Starship rocket completed its first full orbital test flight today,
marking a significant milestone for the company's next-generation launch vehicle.
The massive rocket lifted off from Boca Chica, Texas, and successfully reached
orbit before performing a controlled re-entry. This achievement comes after years
of iterative testing and several high-profile failures during earlier test flights.
The successful orbital demonstration opens the door for future missions including
NASA's Artemis program lunar landers and eventual Mars transport capability.
Engineers celebrated as telemetry confirmed nominal performance throughout all
phases of the flight. The booster stage performed a successful return and landing
at the launch site, demonstrating the full reusability that SpaceX has been
working toward. Industry analysts noted that this success could reshape the
commercial launch market significantly.</p>
</article>
</body></html>
"""

SNAPI_RESPONSE = {
    "count": 2,
    "results": [
        {
            "id": 1001,
            "title": "NASA Selects New Science Missions",
            "url": "https://snapi.dev/articles/nasa-missions",
            "news_site": "NASA",
            "summary": "NASA announced two new science missions today.",
            "published_at": "2026-03-01T12:00:00Z",
        },
        {
            "id": 1002,
            "title": "ESA Ariane 6 Update",
            "url": "https://snapi.dev/articles/ariane6",
            "news_site": "ESA",
            "summary": "ESA provided an update on the Ariane 6 rocket program.",
            "published_at": "2026-02-28T09:00:00Z",
        },
    ],
}

BLUESKY_RESOLVE_RESPONSE = {"did": "did:plc:testuser123"}

BLUESKY_FEED_RESPONSE = {
    "feed": [
        {
            "post": {
                "uri": "at://did:plc:testuser123/app.bsky.feed.post/abc123",
                "record": {
                    "text": "Exciting news about the Falcon 9 launch today!",
                    "createdAt": "2026-03-01T10:00:00Z",
                },
                "embed": {"external": {"uri": "https://spacenews.com/falcon9-launch"}},
            },
        },
        {
            "post": {
                "uri": "at://did:plc:testuser123/app.bsky.feed.post/def456",
                "record": {
                    "text": "Shared a cool post",
                    "createdAt": "2026-03-01T09:00:00Z",
                },
            },
            "reason": {"$type": "app.bsky.feed.defs#reasonRepost"},
        },
        {
            "post": {
                "uri": "at://did:plc:testuser123/app.bsky.feed.post/ghi789",
                "record": {
                    "text": (
                        "The Mars rover found something interesting"
                        " in the soil samples."
                    ),
                    "createdAt": "2026-02-28T15:00:00Z",
                },
            },
        },
    ],
}

TWITTER_USER_RESPONSE = {"id_str": "44196397", "id": 44196397, "screen_name": "spacex"}

TWITTER_RESPONSE = {
    "tweets": [
        {
            "id_str": "1234567890",
            "full_text": ("SpaceX just landed the booster for the 20th time!"),
            "favorite_count": 500,
            "retweet_count": 100,
            "tweet_created_at": "2026-03-01T10:00:00Z",
            "entities": {
                "urls": [
                    {
                        "expanded_url": "https://spacex.com/updates/booster-landing",
                    }
                ]
            },
        },
        {
            "id_str": "1234567891",
            "full_text": "RT @someone: Old tweet",
            "retweeted_tweet": {"id_str": "9999"},
            "favorite_count": 50,
            "retweet_count": 10,
            "entities": {},
        },
        {
            "id_str": "1234567892",
            "full_text": "Reply to a discussion",
            "in_reply_to_status_id": "8888",
            "favorite_count": 20,
            "retweet_count": 5,
            "entities": {},
        },
        {
            "id_str": "1234567893",
            "full_text": "Low engagement tweet about space",
            "favorite_count": 2,
            "retweet_count": 0,
            "entities": {},
        },
    ],
}

ARXIV_RSS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <item rdf:about="http://arxiv.org/abs/2401.12345">
    <title>Discovery of a New Exoplanet in the Habitable Zone</title>
    <link>http://arxiv.org/abs/2401.12345</link>
    <summary>We report a new exoplanet in the habitable zone.</summary>
    <dc:creator>Smith, J. and Doe, A.</dc:creator>
  </item>
  <item rdf:about="http://arxiv.org/abs/2401.67890">
    <title>Quantum Error Correction in Topological Codes</title>
    <link>http://arxiv.org/abs/2401.67890</link>
    <summary>We present a novel approach to quantum error correction.</summary>
    <dc:creator>Zhang, W.</dc:creator>
  </item>
  <item rdf:about="http://arxiv.org/abs/2401.11111">
    <title>Mars Soil Analysis Using Spectroscopic Methods</title>
    <link>http://arxiv.org/abs/2401.11111</link>
    <summary>Spectroscopic analysis of Mars soil samples from Perseverance.</summary>
    <dc:creator>Lee, K.</dc:creator>
  </item>
</rdf:RDF>
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    content_hash_val: str | None = None,
    canonical_url: str | None = None,
    extraction_method: ExtractionMethod | None = None,
    expanded_at: datetime | None = None,
) -> ContentItem:
    """Build a ContentItem with sensible defaults."""
    if published_at is None:
        published_at = datetime.now(UTC) - timedelta(hours=6)
    c_hash = content_hash_val or (content_hash(body_text) if body_text else None)
    return ContentItem(
        id=url_hash(source_url),
        source_url=source_url,
        canonical_url=canonical_url,
        content_type=content_type,
        source_name=source_name,
        title=title,
        body_text=body_text,
        excerpt=excerpt,
        published_at=published_at,
        scraped_at=datetime.now(UTC),
        word_count=word_count,
        categories=categories or [],
        content_hash=c_hash,
        url_hash=url_hash(source_url),
        reddit_score=reddit_score,
        tweet_engagement=tweet_engagement,
        extraction_method=extraction_method,
        expanded_at=expanded_at,
    )


@pytest.fixture()
def make_item():
    """Expose the item factory as a fixture."""
    return _make_item


@pytest.fixture()
def canned():
    """Bundle all canned data constants into a namespace."""

    class _Canned:
        minimal_rss_xml = MINIMAL_RSS_XML
        sample_html_article = SAMPLE_HTML_ARTICLE
        snapi_response = SNAPI_RESPONSE
        bluesky_resolve_response = BLUESKY_RESOLVE_RESPONSE
        bluesky_feed_response = BLUESKY_FEED_RESPONSE
        twitter_user_response = TWITTER_USER_RESPONSE
        twitter_response = TWITTER_RESPONSE
        arxiv_rss_xml = ARXIV_RSS_XML

    return _Canned()


@pytest.fixture()
def tmp_store(tmp_path):
    """ContentStore backed by a temp directory."""
    return ContentStore(base_dir=tmp_path / "data")


@pytest.fixture(autouse=True)
def _no_api_keys(monkeypatch):
    """Clear all API keys so scrapers degrade gracefully by default."""
    for key in (
        "ANTHROPIC_API_KEY",
        "SOCIALDATA_API_KEY",
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def patch_http(monkeypatch):
    """Factory: ``patch_http(handler)`` injects a MockTransport.

    Patches every module that imports make_http_client.
    """

    def _patch(handler):
        transport = httpx.MockTransport(handler)

        def _make_mock_client(**kwargs: Any) -> httpx.AsyncClient:
            kwargs.pop("transport", None)
            return httpx.AsyncClient(transport=transport, **kwargs)

        # Patch at every import site (each module binds its own reference)
        for mod in (
            "astral_ingest.scrapers.base",
            "astral_ingest.scrapers.rss",
            "astral_ingest.scrapers.snapi",
            "astral_ingest.scrapers.arxiv",
            "astral_ingest.scrapers.bluesky",
            "astral_ingest.scrapers.twitter",
            "astral_ingest.expand.url_cleaner",
            "astral_ingest.expand.pipeline",
        ):
            monkeypatch.setattr(f"{mod}.make_http_client", _make_mock_client)

    return _patch
