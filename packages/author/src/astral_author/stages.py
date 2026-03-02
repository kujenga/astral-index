"""Protocol definitions for the four pipeline stages.

Each stage is a Protocol (structural subtype) so implementations don't need
to inherit from anything — they just need to match the method signatures.
"""

from __future__ import annotations

from typing import Protocol

from astral_core import ContentItem

from .models import NewsletterDraft, NewsletterSection


class Ranker(Protocol):
    async def rank(
        self,
        items: list[ContentItem],
        *,
        max_items: int = 50,
    ) -> list[tuple[ContentItem, float]]:
        """Score and rank items by relevance. Returns (item, score) pairs."""
        ...


class Clusterer(Protocol):
    async def cluster(
        self,
        scored_items: list[tuple[ContentItem, float]],
    ) -> list[NewsletterSection]:
        """Group scored items into newsletter sections.

        Sections will have source_items populated but no summaries yet.
        """
        ...


class Summarizer(Protocol):
    async def summarize(
        self,
        section: NewsletterSection,
        items: dict[str, ContentItem],
    ) -> NewsletterSection:
        """Fill in prose and item summaries for a section."""
        ...


class Drafter(Protocol):
    async def draft(
        self,
        sections: list[NewsletterSection],
        items: dict[str, ContentItem],
    ) -> NewsletterDraft:
        """Assemble sections into a complete newsletter draft."""
        ...
