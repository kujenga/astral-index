"""Bluesky scraper using the public AT Protocol AppView API."""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import UTC, datetime
from typing import Any

from astral_core import (
    ContentItem,
    ContentType,
    ExtractionMethod,
    content_hash,
    url_hash,
)

from .base import BaseScraper, make_http_client

logger = logging.getLogger(__name__)

APPVIEW_BASE = "https://public.api.bsky.app/xrpc"


class BlueskyScraper(BaseScraper):
    def __init__(self, bluesky_config: dict[str, Any]) -> None:
        self.accounts: list[str] = bluesky_config.get("accounts", [])
        self.limit: int = bluesky_config.get("limit", 30)

    async def _resolve_did(self, client: Any, handle: str) -> str | None:
        """Resolve a Bluesky handle to a DID."""
        try:
            resp = await client.get(
                f"{APPVIEW_BASE}/com.atproto.identity.resolveHandle",
                params={"handle": handle},
            )
            resp.raise_for_status()
            return resp.json().get("did")
        except Exception:
            logger.warning("Failed to resolve Bluesky handle: %s", handle)
            return None

    async def _fetch_author_feed(
        self, client: Any, did: str, handle: str
    ) -> list[ContentItem]:
        """Fetch recent posts from an author's feed."""
        try:
            resp = await client.get(
                f"{APPVIEW_BASE}/app.bsky.feed.getAuthorFeed",
                params={
                    "actor": did,
                    "limit": str(self.limit),
                    "filter": "posts_no_replies",
                },
            )
            resp.raise_for_status()
        except Exception:
            logger.warning("Failed to fetch feed for @%s", handle)
            return []

        items: list[ContentItem] = []
        now = datetime.now(UTC)

        for feed_item in resp.json().get("feed", []):
            post = feed_item.get("post", {})
            record = post.get("record", {})

            # Skip reposts
            reason_type = feed_item.get("reason", {}).get("$type")
            if reason_type == "app.bsky.feed.defs#reasonRepost":
                continue

            text = record.get("text", "").strip()
            if not text:
                continue

            uri = post.get("uri", "")

            # Build a web-accessible URL
            # at://did:plc:xxx/app.bsky.feed.post/rkey -> bsky.app profile URL
            rkey = uri.split("/")[-1] if uri else ""
            web_url = f"https://bsky.app/profile/{handle}/post/{rkey}"

            item_id = url_hash(web_url)

            # Extract embedded link if present
            canonical = None
            embed = post.get("embed", {})
            external = embed.get("external") if embed else None
            if external:
                canonical = external.get("uri")
            # Also check record embeds for link cards
            if not canonical:
                record_embed = record.get("embed", {})
                if record_embed.get("$type") == "app.bsky.embed.external":
                    ext = record_embed.get("external", {})
                    canonical = ext.get("uri")

            # Extract links from facets
            if not canonical:
                for facet in record.get("facets", []):
                    for feature in facet.get("features", []):
                        if feature.get("$type") == "app.bsky.richtext.facet#link":
                            canonical = feature.get("uri")
                            break
                    if canonical:
                        break

            published = None
            created_at = record.get("createdAt")
            if created_at:
                with contextlib.suppress(ValueError, TypeError):
                    published = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )

            # Use first ~100 chars of text as title
            title = text[:100] + ("..." if len(text) > 100 else "")
            # Clean up newlines in title
            title = re.sub(r"\s+", " ", title)

            excerpt = text[:500] if len(text) > 500 else text
            wc = len(text.split())
            c_hash = content_hash(text)

            items.append(
                ContentItem(
                    id=item_id,
                    source_url=web_url,
                    canonical_url=canonical,
                    content_type=ContentType.ARTICLE,
                    source_name=f"Bluesky: @{handle}",
                    title=title,
                    body_text=text,
                    excerpt=excerpt,
                    author=handle,
                    published_at=published,
                    scraped_at=now,
                    word_count=wc,
                    content_hash=c_hash,
                    url_hash=url_hash(web_url),
                    extraction_method=ExtractionMethod.BLUESKY_API,
                    bluesky_uri=uri,
                    social_author_handle=handle,
                )
            )

        return items

    async def fetch(self) -> list[ContentItem]:
        all_items: list[ContentItem] = []
        async with make_http_client() as client:
            for handle in self.accounts:
                did = await self._resolve_did(client, handle)
                if not did:
                    continue
                items = await self._fetch_author_feed(client, did, handle)
                all_items.extend(items)
        return all_items
