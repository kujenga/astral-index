"""Markdown newsletter drafter.

Assembles summarized sections into a complete newsletter draft with
an introduction, formatted sections, and closing.
"""

from __future__ import annotations

import logging
from datetime import date

from astral_core import ContentItem, get_llm_client, load_prompt

from .models import ItemSummary, NewsletterDraft, NewsletterSection

logger = logging.getLogger(__name__)

_INTRO_SYSTEM = """\
You are the editor of a space technology newsletter called "Astral Index". \
Write a compelling introduction (3-5 sentences) that:
- Leads with the week's most significant development and why it matters
- Adds context, specific details, or implications beyond the headline
- Briefly previews the other major themes covered in this issue
- Uses a conversational but informed editorial voice

Return ONLY the introduction text, no greetings or sign-offs."""


def _render_item(item: ItemSummary) -> str:
    link = f"**[{item.title}]({item.source_url})**"
    return f"- {link} ({item.source_name}) — {item.summary}"


def _render_section(section: NewsletterSection) -> str:
    lines = [f"## {section.heading}", ""]
    if section.prose:
        lines.append(section.prose)
        lines.append("")
    for item in section.items:
        lines.append(_render_item(item))
        lines.append("")
    return "\n".join(lines)


async def _generate_intro(sections: list[NewsletterSection]) -> str | None:
    """Generate an LLM introduction from section context. Returns None on failure."""
    client = get_llm_client()
    if client is None:
        return None

    # Build rich context: top stories with summaries
    top_stories: list[str] = []
    for section in sections:
        for item in section.items[:2]:
            summary_snippet = item.summary[:150] if item.summary else ""
            top_stories.append(f"- {item.title}: {summary_snippet}")
            if len(top_stories) >= 5:
                break
        if len(top_stories) >= 5:
            break

    # Section headings
    headings = [s.heading for s in sections]

    # Category breakdown
    from collections import Counter

    cat_counts: Counter[str] = Counter()
    for section in sections:
        if section.category:
            cat_counts[section.category] += len(section.items)

    parts = ["Top stories:"]
    parts.extend(top_stories[:5])
    if headings:
        parts.append(f"\nSection headings: {', '.join(headings)}")
    if cat_counts:
        cat_str = ", ".join(f"{k} ({v})" for k, v in cat_counts.most_common())
        parts.append(f"Categories covered: {cat_str}")

    user_message = "\n".join(parts)

    try:
        system = load_prompt("newsletter-intro", _INTRO_SYSTEM)
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text.strip()
    except Exception:
        logger.warning("LLM intro generation failed", exc_info=True)
        return None


class MarkdownDrafter:
    """Assembles summarized sections into a rendered newsletter draft."""

    async def draft(
        self,
        sections: list[NewsletterSection],
        items: dict[str, ContentItem],
    ) -> NewsletterDraft:
        today = date.today()
        title = f"Astral Index — {today.strftime('%B %d, %Y')}"

        # Try LLM introduction, fall back to a simple header
        intro = await _generate_intro(sections)
        if not intro:
            # Fallback: use top story summary if available for a richer template
            top_item = None
            for section in sections:
                if section.items:
                    top_item = section.items[0]
                    break
            if top_item and top_item.summary:
                intro = (
                    f"This week in space: {top_item.title}. "
                    f"{top_item.summary.split('.')[0]}. "
                    f"Plus {sum(len(s.items) for s in sections) - 1} more stories."
                )
            elif top_item:
                highlights = ", ".join(
                    item.title for s in sections for item in s.items[:2]
                )[:200]
                intro = f"This week in space: {highlights}, and more."
            else:
                intro = "Here's your roundup of the latest in space technology."

        closing = "Until next time — clear skies and steady orbits."

        # Render full markdown
        md_parts = [f"# {title}", "", intro, ""]
        for section in sections:
            md_parts.append(_render_section(section))
        md_parts.extend(["---", "", closing, ""])
        markdown = "\n".join(md_parts)

        total_output = sum(len(s.items) for s in sections)

        return NewsletterDraft(
            issue_date=today,
            title=title,
            introduction=intro,
            sections=sections,
            closing=closing,
            markdown=markdown,
            strategy_name="",  # filled by pipeline
            model_used=None,
            total_input_items=len(items),
            total_output_items=total_output,
            generation_seconds=0.0,  # filled by pipeline
            word_count=len(markdown.split()),
        )
