"""Draft pipeline: compose stages into named strategies."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from astral_core import ContentItem

from .cluster import CategoryClusterer
from .draft import MarkdownDrafter
from .models import NewsletterDraft
from .rank import EngagementRanker
from .stages import Clusterer, Drafter, Ranker, Summarizer
from .summarize import ExcerptSummarizer, LLMSummarizer


@dataclass
class DraftPipeline:
    """Composes one of each stage into a named strategy."""

    name: str
    ranker: Ranker
    clusterer: Clusterer
    summarizer: Summarizer
    drafter: Drafter

    async def run(
        self,
        items: list[ContentItem],
        *,
        max_items: int = 50,
    ) -> NewsletterDraft:
        """Execute rank -> cluster -> summarize -> draft, with timing."""
        start = time.monotonic()

        # Build lookup dict for quick access by ID
        items_by_id: dict[str, ContentItem] = {item.id: item for item in items}

        # 1. Rank
        scored = await self.ranker.rank(items, max_items=max_items)

        # 2. Cluster
        sections = await self.clusterer.cluster(scored)

        # 3. Summarize each section
        summarized = []
        for section in sections:
            summarized.append(await self.summarizer.summarize(section, items_by_id))

        # 4. Draft
        newsletter = await self.drafter.draft(summarized, items_by_id)

        elapsed = time.monotonic() - start
        return newsletter.model_copy(
            update={
                "strategy_name": self.name,
                "generation_seconds": round(elapsed, 2),
            }
        )


def _build_baseline() -> DraftPipeline:
    return DraftPipeline(
        name="baseline",
        ranker=EngagementRanker(),
        clusterer=CategoryClusterer(),
        summarizer=LLMSummarizer(),
        drafter=MarkdownDrafter(),
    )


def _build_headlines_only() -> DraftPipeline:
    return DraftPipeline(
        name="headlines-only",
        ranker=EngagementRanker(),
        clusterer=CategoryClusterer(),
        summarizer=ExcerptSummarizer(),
        drafter=MarkdownDrafter(),
    )


# Registry of named strategies
STRATEGIES: dict[str, Callable[[], DraftPipeline]] = {
    "baseline": _build_baseline,
    "headlines-only": _build_headlines_only,
}


def build_strategy(name: str) -> DraftPipeline:
    """Instantiate a named strategy from the registry.

    Raises KeyError if the name is not registered.
    """
    factory = STRATEGIES[name]
    return factory()
