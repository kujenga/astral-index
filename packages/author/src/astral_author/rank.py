"""Heuristic engagement-based ranker.

Weighted combination of four signals (all 0-1 normalized):
- Recency (0.3)   — exponential decay, ~48h half-life
- Engagement (0.35) — log-scaled social signals; articles get baseline 0.4
- Source tier (0.25) — lookup table by source name
- Content quality (0.1) — has body_text, has categories, word_count > 200
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from astral_core import NON_JOURNALISM_RE, ContentItem, SpaceCategory, title_similarity

# Source quality tiers (0-1). Unlisted sources get DEFAULT_TIER.
_SOURCE_TIERS: dict[str, float] = {
    "SpaceNews": 1.0,
    "Spaceflight Now": 0.95,
    "NASA Spaceflight": 0.9,
    "Ars Technica": 0.9,
    "The Planetary Society": 0.85,
    "NASA": 0.85,
    "ESA": 0.85,
    "Space.com": 0.8,
    "Universe Today": 0.8,
    "The Space Review": 0.75,
    "SNAPI Articles": 0.7,
    "SNAPI Blogs": 0.65,
}
_DEFAULT_TIER = 0.5

# Weights for the four signals
_W_RECENCY = 0.30
_W_ENGAGEMENT = 0.35
_W_SOURCE = 0.25
_W_QUALITY = 0.10

# Recency half-life in hours
_HALF_LIFE_HOURS = 48.0


def _recency_score(
    published_at: datetime | None,
    now: datetime,
    half_life_hours: float = _HALF_LIFE_HOURS,
) -> float:
    """Exponential decay from publication time. Recent = closer to 1."""
    if published_at is None:
        return 0.3  # unknown date gets a neutral-low score
    age_hours = (now - published_at).total_seconds() / 3600
    if age_hours < 0:
        return 1.0  # future-dated items (rare) get max
    return math.exp(-0.693 * age_hours / half_life_hours)


def _engagement_score(item: ContentItem) -> float:
    """Log-scaled social engagement. Articles without signals get a baseline."""
    if item.reddit_score is not None and item.reddit_score > 0:
        # reddit_score typically 50-5000+; log10(50)=1.7, log10(5000)=3.7
        return min(1.0, math.log10(max(item.reddit_score, 1)) / 4.0)
    if item.tweet_engagement is not None and item.tweet_engagement > 0:
        return min(1.0, math.log10(max(item.tweet_engagement, 1)) / 4.0)
    # Articles and press releases without social signals get a baseline
    return 0.4


def _source_tier(source_name: str) -> float:
    return _SOURCE_TIERS.get(source_name, _DEFAULT_TIER)


def _quality_score(item: ContentItem) -> float:
    """Simple quality heuristics: body text, categories, word count."""
    score = 0.0
    if item.body_text:
        score += 0.4
    if item.categories:
        score += 0.3
    if item.word_count and item.word_count > 200:
        score += 0.3
    return score


def score_item(item: ContentItem, now: datetime | None = None) -> float:
    """Compute a 0-1 relevance score for a single item."""
    if now is None:
        now = datetime.now(UTC)
    return (
        _W_RECENCY * _recency_score(item.published_at, now)
        + _W_ENGAGEMENT * _engagement_score(item)
        + _W_SOURCE * _source_tier(item.source_name)
        + _W_QUALITY * _quality_score(item)
    )


_DEDUP_SIMILARITY_THRESHOLD = 0.5


class EngagementRanker:
    """Ranks items by a weighted heuristic score. No LLM calls.

    Weights default to the module-level constants but can be overridden
    to create strategy variants (e.g. recency-biased ranking).
    """

    def __init__(
        self,
        *,
        w_recency: float = _W_RECENCY,
        w_engagement: float = _W_ENGAGEMENT,
        w_source: float = _W_SOURCE,
        w_quality: float = _W_QUALITY,
        half_life_hours: float = _HALF_LIFE_HOURS,
    ) -> None:
        self.w_recency = w_recency
        self.w_engagement = w_engagement
        self.w_source = w_source
        self.w_quality = w_quality
        self.half_life_hours = half_life_hours

    def _score_item(self, item: ContentItem, now: datetime) -> float:
        """Compute a 0-1 relevance score using instance weights."""
        return (
            self.w_recency
            * _recency_score(item.published_at, now, self.half_life_hours)
            + self.w_engagement * _engagement_score(item)
            + self.w_source * _source_tier(item.source_name)
            + self.w_quality * _quality_score(item)
        )

    async def rank(
        self,
        items: list[ContentItem],
        *,
        max_items: int = 50,
    ) -> list[tuple[ContentItem, float]]:
        now = datetime.now(UTC)
        on_topic = [
            i
            for i in items
            if SpaceCategory.OFF_TOPIC not in i.categories
            # Defense-in-depth: also filter uncategorized low-quality items
            and not (not i.categories and _quality_score(i) < 0.3)
            # Block non-journalism content (games, puzzles) that slipped past classifier
            and not NON_JOURNALISM_RE.search(i.title)
        ]
        scored = [(item, self._score_item(item, now)) for item in on_topic]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Semantic dedup: skip items too similar to an already-accepted item
        accepted: list[tuple[ContentItem, float]] = []
        for item, s in scored:
            if any(
                title_similarity(item.title, a.title) >= _DEDUP_SIMILARITY_THRESHOLD
                for a, _ in accepted
            ):
                continue
            accepted.append((item, s))
            if len(accepted) >= max_items:
                break

        # Category floor: ensure at least one item per category is represented.
        # Walk the remaining scored items and add the top-scoring item from any
        # category not yet present in the accepted list.
        accepted_ids = {item.id for item, _ in accepted}
        covered_cats: set[SpaceCategory] = set()
        for item, _ in accepted:
            for cat in item.categories:
                covered_cats.add(cat)

        for item, s in scored:
            if item.id in accepted_ids:
                continue
            item_cats = {c for c in item.categories if c != SpaceCategory.OFF_TOPIC}
            if item_cats and not item_cats.issubset(covered_cats):
                # Enforce dedup for category-floor items with a slightly
                # relaxed threshold to preserve category coverage
                if any(
                    title_similarity(item.title, a.title) >= 0.6 for a, _ in accepted
                ):
                    continue
                accepted.append((item, s))
                accepted_ids.add(item.id)
                covered_cats.update(item_cats)

        return accepted
