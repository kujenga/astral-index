from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import feedparser
from astral_core import ContentItem, ContentType, SpaceCategory, content_hash, url_hash
from dateutil.parser import parse as parse_date

from ..util import extract_links, strip_html
from .base import BaseScraper, make_http_client


class RSSFeedScraper(BaseScraper):
    def __init__(self, source_config: dict[str, Any]) -> None:
        self.name: str = source_config["name"]
        self.url: str = source_config["url"]
        self.content_mode: str = source_config.get("content_type", "excerpt")
        self.category_hints: list[str] = source_config.get("category_hints", [])
        self.is_paywalled: bool = source_config.get("is_paywalled", False)

        # Conditional GET state (populated after first fetch)
        self._etag: str | None = None
        self._last_modified: str | None = None

    async def fetch(self) -> list[ContentItem]:
        headers: dict[str, str] = {}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified

        async with make_http_client() as client:
            resp = await client.get(self.url, headers=headers)

        if resp.status_code == 304:
            return []

        resp.raise_for_status()

        # Save conditional GET tokens for next time
        self._etag = resp.headers.get("ETag")
        self._last_modified = resp.headers.get("Last-Modified")

        feed = feedparser.parse(resp.text)
        now = datetime.now(timezone.utc)
        items: list[ContentItem] = []

        for entry in feed.entries:
            link = entry.get("link", "")
            if not link:
                continue

            item_id = url_hash(link)

            # Best-effort body extraction from feed content
            raw_body = ""
            if hasattr(entry, "content") and entry.content:
                raw_body = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                raw_body = entry.summary or ""

            body_text = strip_html(raw_body) if raw_body else None
            links = extract_links(raw_body) if raw_body else []

            excerpt = None
            if body_text:
                excerpt = body_text[:500] if len(body_text) > 500 else body_text

            # For excerpt-only feeds, body_text is just the excerpt
            if self.content_mode == "excerpt":
                body_text = None

            published = None
            if hasattr(entry, "published") and entry.published:
                try:
                    published = parse_date(entry.published)
                except (ValueError, OverflowError):
                    pass

            word_count = len(body_text.split()) if body_text else None
            c_hash = content_hash(body_text) if body_text else None

            categories = [
                SpaceCategory(c) for c in self.category_hints if c in SpaceCategory.__members__.values()
            ]

            items.append(
                ContentItem(
                    id=item_id,
                    source_url=link,
                    canonical_url=link,
                    content_type=ContentType.ARTICLE,
                    source_name=self.name,
                    title=entry.get("title", "Untitled"),
                    body_text=body_text,
                    excerpt=excerpt,
                    author=entry.get("author"),
                    published_at=published,
                    scraped_at=now,
                    word_count=word_count,
                    categories=categories,
                    content_hash=c_hash,
                    url_hash=url_hash(link),
                    is_paywalled=self.is_paywalled,
                    links_referenced=links,
                )
            )

        return items
