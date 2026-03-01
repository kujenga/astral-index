"""Twitter/X scraper using the SocialData.tools REST API."""

from __future__ import annotations

import contextlib
import logging
import os
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

SOCIALDATA_BASE = "https://api.socialdata.tools"


class TwitterScraper(BaseScraper):
    def __init__(self, twitter_config: dict[str, Any]) -> None:
        self.accounts: list[str] = twitter_config.get("accounts", [])
        self.limit: int = twitter_config.get("limit", 20)
        self.min_likes: int = twitter_config.get("min_likes", 5)

    async def _fetch_user_tweets(
        self, client: Any, username: str, api_key: str
    ) -> list[ContentItem]:
        """Fetch recent tweets from a user via SocialData API."""
        try:
            resp = await client.get(
                f"{SOCIALDATA_BASE}/twitter/user/{username}/tweets",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
        except Exception:
            logger.warning("Failed to fetch tweets for @%s", username)
            return []

        items: list[ContentItem] = []
        now = datetime.now(UTC)

        tweets = resp.json().get("tweets", [])
        for tweet in tweets[: self.limit]:
            # Skip retweets and replies
            if tweet.get("retweeted_tweet"):
                continue
            if tweet.get("in_reply_to_status_id"):
                continue

            text = tweet.get("full_text", "") or tweet.get("text", "")
            text = text.strip()
            if not text:
                continue

            likes = tweet.get("favorite_count", 0) or 0
            retweets = tweet.get("retweet_count", 0) or 0
            engagement = likes + retweets

            if likes < self.min_likes:
                continue

            tid = str(tweet.get("id_str", ""))
            web_url = f"https://x.com/{username}/status/{tid}"
            item_id = url_hash(web_url)

            # Extract shared URLs from entities
            canonical = None
            entities = tweet.get("entities", {})
            for url_entity in entities.get("urls", []):
                expanded = url_entity.get("expanded_url", "")
                # Skip twitter/x.com self-links
                is_self = re.match(r"https?://(twitter\.com|x\.com)/", expanded)
                if expanded and not is_self:
                    canonical = expanded
                    break

            published = None
            created_at = tweet.get("tweet_created_at") or tweet.get("created_at")
            if created_at:
                with contextlib.suppress(ValueError, TypeError):
                    published = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )

            title = text[:100] + ("..." if len(text) > 100 else "")
            title = re.sub(r"\s+", " ", title)

            excerpt = text[:500] if len(text) > 500 else text
            wc = len(text.split())
            c_hash = content_hash(text)

            items.append(
                ContentItem(
                    id=item_id,
                    source_url=web_url,
                    canonical_url=canonical,
                    content_type=ContentType.TWEET,
                    source_name=f"Twitter: @{username}",
                    title=title,
                    body_text=text,
                    excerpt=excerpt,
                    author=username,
                    published_at=published,
                    scraped_at=now,
                    word_count=wc,
                    content_hash=c_hash,
                    url_hash=url_hash(web_url),
                    extraction_method=ExtractionMethod.SOCIALDATA_API,
                    tweet_id=tid,
                    tweet_engagement=engagement,
                    social_author_handle=username,
                )
            )

        return items

    async def fetch(self) -> list[ContentItem]:
        api_key = os.environ.get("SOCIALDATA_API_KEY")
        if not api_key:
            logger.warning("SOCIALDATA_API_KEY not set, skipping Twitter/X")
            return []

        all_items: list[ContentItem] = []
        async with make_http_client() as client:
            for username in self.accounts:
                items = await self._fetch_user_tweets(client, username, api_key)
                all_items.extend(items)
        return all_items
