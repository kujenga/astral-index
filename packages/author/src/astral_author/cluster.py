"""Category-based clustering.

Groups items by their primary SpaceCategory, then splits into
deep-dive sections (top groups by total relevance) and a catch-all
"In Brief" section for small groups and uncategorized items.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from astral_core import ContentItem, SpaceCategory

from .models import NewsletterSection, SectionType

# Human-friendly section headings per category
_HEADINGS: dict[SpaceCategory, str] = {
    SpaceCategory.LAUNCH_VEHICLES: "Launch & Propulsion",
    SpaceCategory.SPACE_SCIENCE: "Space Science",
    SpaceCategory.COMMERCIAL_SPACE: "Commercial Space",
    SpaceCategory.LUNAR: "Lunar Exploration",
    SpaceCategory.MARS: "Mars & Beyond",
    SpaceCategory.EARTH_OBSERVATION: "Earth Observation",
    SpaceCategory.POLICY: "Space Policy",
    SpaceCategory.INTERNATIONAL: "International Programs",
    SpaceCategory.ISS_STATIONS: "Space Stations",
    SpaceCategory.DEFENSE_SPACE: "Defense & Security",
    SpaceCategory.SATELLITE_COMMS: "Satellite Communications",
    SpaceCategory.DEEP_SPACE: "Deep Space Exploration",
}


class CategoryClusterer:
    """Groups items by primary SpaceCategory into newsletter sections."""

    def __init__(
        self,
        *,
        max_deep_dives: int = 3,
        min_group_size: int = 2,
        max_items_per_section: int = 12,
    ) -> None:
        self.max_deep_dives = max_deep_dives
        self.min_group_size = min_group_size
        self.max_items_per_section = max_items_per_section

    async def cluster(
        self,
        scored_items: list[tuple[ContentItem, float]],
    ) -> list[NewsletterSection]:
        # Group by primary category (first in categories list)
        groups: dict[SpaceCategory | None, list[tuple[ContentItem, float]]] = (
            defaultdict(list)
        )
        for item, score in scored_items:
            cat = item.categories[0] if item.categories else None
            groups[cat].append((item, score))

        # Sort groups by total relevance score (descending)
        categorized = [
            (cat, members) for cat, members in groups.items() if cat is not None
        ]
        categorized.sort(key=lambda g: sum(s for _, s in g[1]), reverse=True)

        sections: list[NewsletterSection] = []
        brief_items: list[tuple[ContentItem, float]] = []

        # Top N groups become deep-dive sections; overflow excess items to brief
        for i, (cat, members) in enumerate(categorized):
            if i < self.max_deep_dives and len(members) >= self.min_group_size:
                # Sort members by score descending so overflow drops lowest-scored
                members.sort(key=lambda x: x[1], reverse=True)
                # Cap any single source at 2 items per section for diversity
                keep: list[tuple[ContentItem, float]] = []
                overflow: list[tuple[ContentItem, float]] = []
                src_counts: Counter[str] = Counter()
                for item, score in members:
                    if (
                        len(keep) < self.max_items_per_section
                        and src_counts[item.source_name] < 2
                    ):
                        keep.append((item, score))
                        src_counts[item.source_name] += 1
                    else:
                        overflow.append((item, score))
                sections.append(
                    NewsletterSection(
                        heading=_HEADINGS.get(cat, cat.value.replace("_", " ").title()),
                        category=cat,
                        section_type=SectionType.DEEP_DIVE,
                        source_items=[item.id for item, _ in keep],
                    )
                )
                brief_items.extend(overflow)
            else:
                brief_items.extend(members)

        # Uncategorized items go to brief
        brief_items.extend(groups.get(None, []))

        # Sort brief items by score descending and cap size while preserving
        # category diversity — keep at least one item per category.
        brief_items.sort(key=lambda x: x[1], reverse=True)
        if len(brief_items) > self.max_items_per_section:
            kept: list[tuple[ContentItem, float]] = []
            seen_cats: set[SpaceCategory] = set()
            # First pass: guarantee one item per unseen category
            for item, score in brief_items:
                item_cats = set(item.categories) - seen_cats
                if item_cats:
                    kept.append((item, score))
                    seen_cats.update(item.categories)
            # Second pass: fill remaining slots by score
            kept_ids = {item.id for item, _ in kept}
            for item, score in brief_items:
                if len(kept) >= self.max_items_per_section:
                    break
                if item.id not in kept_ids:
                    kept.append((item, score))
            brief_items = kept

        if brief_items:
            sections.append(
                NewsletterSection(
                    heading="In Brief",
                    category=None,
                    section_type=SectionType.BRIEF,
                    source_items=[item.id for item, _ in brief_items],
                )
            )

        return sections
