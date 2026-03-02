"""Output data models for the newsletter authoring pipeline."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

from astral_core import SpaceCategory


class SectionType(StrEnum):
    DEEP_DIVE = "deep_dive"
    BRIEF = "brief"
    LINKS = "links"


class ItemSummary(BaseModel):
    """Denormalized view of one item as it appears in the newsletter."""

    item_id: str
    title: str
    source_url: str
    source_name: str
    summary: str = Field(description="1-3 sentence summary")
    relevance_score: float = Field(ge=0, le=1)


class NewsletterSection(BaseModel):
    """One thematic section of the newsletter."""

    heading: str
    category: SpaceCategory | None = None
    section_type: SectionType
    prose: str | None = Field(
        default=None, description="Editorial text for deep-dive sections"
    )
    items: list[ItemSummary] = []
    source_items: list[str] = Field(
        default_factory=list, description="ContentItem IDs feeding this section"
    )


class NewsletterDraft(BaseModel):
    """Complete newsletter draft with pipeline metadata."""

    issue_date: date
    title: str
    introduction: str
    sections: list[NewsletterSection]
    closing: str
    markdown: str = Field(description="Fully rendered markdown")

    # Pipeline metadata (for eval comparisons)
    strategy_name: str
    model_used: str | None = None
    total_input_items: int
    total_output_items: int
    generation_seconds: float
    word_count: int
