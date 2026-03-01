"""Spaceflight News API (SNAPI) v4 client."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from astral_core import ContentItem, ContentType, content_hash, url_hash

from .base import BaseScraper, make_http_client

SNAPI_BASE = "https://api.spaceflightnewsapi.net/v4"


class SNAPIScraper(BaseScraper):
    def __init__(
        self,
        *,
        base_url: str = SNAPI_BASE,
        endpoints: list[str] | None = None,
        since: datetime | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoints = endpoints or ["/articles/", "/blogs/"]
        self.since = since

    async def fetch(self) -> list[ContentItem]:
        items: list[ContentItem] = []
        async with make_http_client() as client:
            for endpoint in self.endpoints:
                params: dict[str, str] = {"limit": "50", "ordering": "-published_at"}
                if self.since:
                    params["published_at_gte"] = self.since.isoformat()

                url = f"{self.base_url}{endpoint}"
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                for result in data.get("results", []):
                    items.append(_to_content_item(result))
        return items


def _to_content_item(entry: dict[str, Any]) -> ContentItem:
    now = datetime.now(UTC)
    link = entry.get("url", "")
    item_id = url_hash(link)
    body = entry.get("summary") or ""
    excerpt = body[:500] if body else None

    published = None
    if entry.get("published_at"):
        with contextlib.suppress(ValueError, TypeError):
            published = datetime.fromisoformat(entry["published_at"])

    c_hash = content_hash(body) if body else None

    return ContentItem(
        id=item_id,
        source_url=link,
        canonical_url=link,
        content_type=ContentType.ARTICLE,
        source_name=entry.get("news_site", "SNAPI"),
        title=entry.get("title", "Untitled"),
        body_text=body or None,
        excerpt=excerpt,
        author=None,
        published_at=published,
        scraped_at=now,
        word_count=len(body.split()) if body else None,
        content_hash=c_hash,
        url_hash=url_hash(link),
    )
