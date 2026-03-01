from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

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
