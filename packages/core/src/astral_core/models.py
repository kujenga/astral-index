from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field


class ContentType(StrEnum):
    ARTICLE = "article"
    TWEET = "tweet"
    REDDIT_POST = "reddit_post"
    ARXIV_PAPER = "arxiv_paper"
    PRESS_RELEASE = "press_release"
    PDF_DOCUMENT = "pdf_document"


class SpaceCategory(StrEnum):
    LAUNCH_VEHICLES = "launch_vehicles"
    SPACE_SCIENCE = "space_science"
    COMMERCIAL_SPACE = "commercial_space"
    LUNAR = "lunar"
    MARS = "mars"
    EARTH_OBSERVATION = "earth_observation"
    POLICY = "policy"
    INTERNATIONAL = "international"
    ISS_STATIONS = "iss_stations"
    DEFENSE_SPACE = "defense_space"
    SATELLITE_COMMS = "satellite_comms"
    DEEP_SPACE = "deep_space"


class ExtractionMethod(StrEnum):
    FEED_FULL_TEXT = "feed_full_text"
    FEED_EXCERPT = "feed_excerpt"
    REDDIT_SELF = "reddit_self"
    REDDIT_LINK = "reddit_link"
    TRAFILATURA = "trafilatura"
    NEWSPAPER = "newspaper"
    READABILITY = "readability"
    PLAYWRIGHT = "playwright"
    PDF = "pdf"
    SNAPI = "snapi"
    BLUESKY_API = "bluesky_api"
    SOCIALDATA_API = "socialdata_api"
    ARXIV_RSS = "arxiv_rss"


# Tracking params stripped during URL normalization
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "ref",
        "source",
        "mc_cid",
        "mc_eid",
    }
)


def normalize_url(url: str) -> str:
    """Strip tracking params and normalize a URL for dedup."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=False)
    cleaned = {k: v for k, v in params.items() if k not in _TRACKING_PARAMS}
    # Rebuild with sorted params for deterministic output
    new_query = urlencode(cleaned, doseq=True) if cleaned else ""
    return urlunparse(parsed._replace(query=new_query, fragment=""))


def url_hash(url: str) -> str:
    """SHA-256 of a URL, truncated to 16 hex chars."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def content_hash(text: str) -> str:
    """SHA-256 of normalized body text."""
    normalized = " ".join(text.split()).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


class ContentItem(BaseModel):
    # Identity
    id: str = Field(description="SHA-256(source_url)[:16]")
    source_url: str
    canonical_url: str | None = None
    content_type: ContentType
    source_name: str

    # Content
    title: str
    body_text: str | None = None
    excerpt: str | None = Field(default=None, max_length=500)

    # Metadata
    author: str | None = None
    published_at: datetime | None = None
    scraped_at: datetime
    language: str = "en"
    word_count: int | None = None

    # Classification (filled downstream by keyword tagger + LLM)
    categories: list[SpaceCategory] = []
    tags: list[str] = []

    # Deduplication
    content_hash: str | None = None
    url_hash: str

    # Quality signals
    is_paywalled: bool = False
    links_referenced: list[str] = []

    # Extraction tracking (Phase 2)
    extraction_method: ExtractionMethod | None = None
    expanded_at: datetime | None = None

    # Reddit-specific signals
    reddit_score: int | None = None
    top_comment: str | None = None

    # arXiv-specific
    arxiv_id: str | None = None
    arxiv_categories: list[str] = []

    # Social media signals (Bluesky/Twitter)
    bluesky_uri: str | None = None
    tweet_id: str | None = None
    tweet_engagement: int | None = None
    social_author_handle: str | None = None
