"""arXiv RSS scraper with keyword filtering for space-related papers."""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime
from typing import Any

import feedparser

from astral_core import (
    ContentItem,
    ContentType,
    ExtractionMethod,
    SpaceCategory,
    content_hash,
    url_hash,
)

from .base import BaseScraper, make_http_client

# Default keywords for filtering space-relevant papers
_DEFAULT_KEYWORDS = (
    r"exoplanet|satellite|orbit|telescope|Mars|Moon|asteroid|comet|mission|"
    r"spacecraft|propulsion|habitable|spectroscop|planet\s?form|"
    r"gravitational\s?wave|pulsar|magnetar|solar\s?wind|"
    r"interstellar|interplanetary|cislunar|astrobiolog|"
    r"cubesat|smallsat|space\s?debris|rocket|launch\s?vehicle"
)


class ArxivScraper(BaseScraper):
    def __init__(
        self, feed_config: dict[str, Any], arxiv_config: dict[str, Any]
    ) -> None:
        self.name: str = feed_config["name"]
        self.url: str = feed_config["url"]
        self.keyword_filter: bool = arxiv_config.get("keyword_filter", True)
        self.category_hints: list[str] = arxiv_config.get("category_hints", [])
        self._keyword_re = re.compile(_DEFAULT_KEYWORDS, re.IGNORECASE)

    def _matches_keywords(self, title: str, abstract: str) -> bool:
        if not self.keyword_filter:
            return True
        return bool(self._keyword_re.search(title) or self._keyword_re.search(abstract))

    @staticmethod
    def _extract_arxiv_id(url: str) -> str | None:
        """Extract arXiv ID from abs or pdf URL (e.g. '2401.12345')."""
        m = re.search(r"(\d{4}\.\d{4,5})", url)
        return m.group(1) if m else None

    async def fetch(self) -> list[ContentItem]:
        async with make_http_client() as client:
            resp = await client.get(self.url)
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        now = datetime.now(UTC)
        items: list[ContentItem] = []

        categories = [
            SpaceCategory(c)
            for c in self.category_hints
            if c in SpaceCategory.__members__.values()
        ]

        for entry in feed.entries:
            link = entry.get("link", "")
            if not link:
                continue

            title = entry.get("title", "Untitled")
            # arXiv RSS puts the abstract in <summary> or <description>
            abstract = ""
            if hasattr(entry, "summary"):
                abstract = entry.summary or ""

            if not self._matches_keywords(title, abstract):
                continue

            item_id = url_hash(link)
            arxiv_id = self._extract_arxiv_id(link)

            # Collect arXiv categories from entry tags
            arxiv_cats = []
            for tag in entry.get("tags", []):
                term = tag.get("term", "")
                if term:
                    arxiv_cats.append(term)

            published = None
            if hasattr(entry, "published") and entry.published:
                with contextlib.suppress(ValueError, OverflowError):
                    from dateutil.parser import parse as parse_date

                    published = parse_date(entry.published)

            body_text = abstract.strip() or None
            excerpt = (
                body_text[:500] if body_text and len(body_text) > 500 else body_text
            )
            wc = len(body_text.split()) if body_text else None
            c_hash = content_hash(body_text) if body_text else None

            author = entry.get("author")

            items.append(
                ContentItem(
                    id=item_id,
                    source_url=link,
                    canonical_url=link,
                    content_type=ContentType.ARXIV_PAPER,
                    source_name=f"arXiv: {self.name}",
                    title=title,
                    body_text=body_text,
                    excerpt=excerpt,
                    author=author,
                    published_at=published,
                    scraped_at=now,
                    word_count=wc,
                    categories=categories,
                    content_hash=c_hash,
                    url_hash=url_hash(link),
                    extraction_method=ExtractionMethod.ARXIV_RSS,
                    arxiv_id=arxiv_id,
                    arxiv_categories=arxiv_cats or [self.name],
                )
            )

        return items
