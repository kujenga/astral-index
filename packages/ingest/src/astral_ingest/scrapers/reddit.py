"""Reddit scraper using asyncpraw for space subreddits."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import asyncpraw

from astral_core import (
    ContentItem,
    ContentType,
    ExtractionMethod,
    SpaceCategory,
    content_hash,
    url_hash,
)

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Bots whose comments we skip
_BOT_NAMES = frozenset(
    {
        "AutoModerator",
        "RemindMeBot",
        "sneakpeekbot",
        "GifReversingBot",
        "WikiSummarizerBot",
        "SaveVideo",
        "vredditdownloader",
    }
)


class RedditScraper(BaseScraper):
    def __init__(self, reddit_config: dict[str, Any]) -> None:
        self.subreddits: list[str] = reddit_config.get("subreddits", [])
        self.score_threshold: int = reddit_config.get("score_threshold", 50)
        self.limit: int = reddit_config.get("limit", 50)
        self.category_map: dict[str, list[str]] = reddit_config.get("category_map", {})

    def _categories_for_subreddit(self, subreddit: str) -> list[SpaceCategory]:
        hints = self.category_map.get(subreddit.lower(), [])
        return [
            SpaceCategory(c) for c in hints if c in SpaceCategory.__members__.values()
        ]

    async def fetch(self) -> list[ContentItem]:
        client_id = os.environ.get("REDDIT_CLIENT_ID")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        user_agent = os.environ.get(
            "REDDIT_USER_AGENT",
            "AstralIndex/0.1 (space newsletter aggregator)",
        )

        if not client_id or not client_secret:
            logger.warning(
                "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set, skipping Reddit"
            )
            return []

        reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

        items: list[ContentItem] = []
        try:
            multi = "+".join(self.subreddits)
            subreddit = await reddit.subreddit(multi)

            async for submission in subreddit.hot(limit=self.limit):
                if submission.stickied:
                    continue
                if submission.score < self.score_threshold:
                    continue

                item = await self._submission_to_item(submission)
                if item:
                    items.append(item)
        finally:
            await reddit.close()

        return items

    async def _submission_to_item(self, submission: Any) -> ContentItem | None:
        now = datetime.now(UTC)
        permalink = f"https://reddit.com{submission.permalink}"
        item_id = url_hash(permalink)

        # Determine subreddit name for category lookup
        sub_name = str(submission.subreddit).lower()
        categories = self._categories_for_subreddit(sub_name)

        published = datetime.fromtimestamp(submission.created_utc, tz=UTC)

        # Self post vs link post
        if submission.is_self:
            body = submission.selftext or ""
            extraction_method = ExtractionMethod.REDDIT_SELF
            canonical = permalink
        else:
            body = None
            extraction_method = ExtractionMethod.REDDIT_LINK
            canonical = submission.url

        excerpt = body[:500] if body and len(body) > 500 else body
        wc = len(body.split()) if body else None
        c_hash = content_hash(body) if body else None

        # Top non-bot comment
        top_comment = await self._top_comment(submission)

        return ContentItem(
            id=item_id,
            source_url=permalink,
            canonical_url=canonical,
            content_type=ContentType.REDDIT_POST,
            source_name=f"r/{submission.subreddit}",
            title=submission.title,
            body_text=body or None,
            excerpt=excerpt,
            author=str(submission.author) if submission.author else None,
            published_at=published,
            scraped_at=now,
            word_count=wc,
            categories=categories,
            content_hash=c_hash,
            url_hash=url_hash(permalink),
            extraction_method=extraction_method,
            reddit_score=submission.score,
            top_comment=top_comment,
        )

    async def _top_comment(self, submission: Any) -> str | None:
        """Extract the top-voted non-bot comment, capped at 1000 chars."""
        try:
            submission.comment_sort = "best"
            # Replace MoreComments with a shallow fetch
            await submission.comments.replace_more(limit=0)
            for comment in submission.comments:
                if not hasattr(comment, "body"):
                    continue
                author = str(comment.author) if comment.author else ""
                if author in _BOT_NAMES:
                    continue
                body = comment.body.strip()
                if body:
                    return body[:1000]
        except Exception:
            logger.debug("Failed to fetch comments for %s", submission.permalink)
        return None
