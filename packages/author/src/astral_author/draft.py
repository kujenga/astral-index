"""Markdown newsletter drafter.

Assembles summarized sections into a complete newsletter draft with
an introduction, formatted sections, and closing.
"""

from __future__ import annotations

import logging
import os
from datetime import date

from astral_core import ContentItem

from .models import ItemSummary, NewsletterDraft, NewsletterSection

logger = logging.getLogger(__name__)

_INTRO_SYSTEM = """\
You are the editor of a space technology newsletter called "Astral Index". \
Given the top 2-3 story headlines from this issue, write a brief 2-3 sentence \
introduction that hooks the reader. Be conversational but informative. \
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


async def _generate_intro(top_titles: list[str]) -> str | None:
    """Generate an LLM introduction mentioning top stories. Returns None on failure."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        return None

    bullets = "\n".join(f"- {t}" for t in top_titles[:3])
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=_INTRO_SYSTEM,
            messages=[{"role": "user", "content": f"Top stories:\n{bullets}"}],
        )
        return resp.content[0].text.strip()  # type: ignore[union-attr]
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

        # Collect top story titles for the introduction
        top_titles: list[str] = []
        for section in sections:
            for item in section.items[:2]:
                top_titles.append(item.title)
                if len(top_titles) >= 3:
                    break
            if len(top_titles) >= 3:
                break

        # Try LLM introduction, fall back to a simple header
        intro = await _generate_intro(top_titles)
        if not intro:
            if top_titles:
                highlights = ", ".join(top_titles[:3])
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
