"""Summarizer implementations: LLM-powered and excerpt-only fallback."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from astral_core import ContentItem, get_llm_client, load_prompt

from .models import ItemSummary, NewsletterSection, SectionType

logger = logging.getLogger(__name__)

_ITEM_SYSTEM = """\
You are a space news editor writing concise summaries for a weekly newsletter. \
Given an article title and body text, write a 1-2 sentence summary that captures \
the key news. Be factual and specific. Do not editorialize. \
Do not infer dates, statistics, or claims not explicitly stated in the source text. \
If the source text is very short, paraphrase it concisely rather than elaborating. \
Return ONLY the summary text, no labels or prefixes."""

_PROSE_SYSTEM = """\
You are the editor of a space technology newsletter. Given several article \
summaries from the same topic area, write 2-3 editorial paragraphs that tie \
the stories together, highlight trends, and give readers context. Be engaging \
but factual. Keep prose under 150 words per section. \
Avoid cliché phrases like "remarkable convergence", "reshaping how we", \
"unprecedented era", "golden age", "paradigm shift". Be specific and concrete. \
Return ONLY the prose paragraphs, no headings or labels."""


_REFUSAL_RE = re.compile(
    r"(?i)("
    r"I cannot provide a summary"
    r"|cannot summarize"
    r"|no body text"
    r"|summary not available"
    r"|unable to summarize"
    r"|I don't have enough"
    r"|no (?:article |source )?(?:text|content) "
    r"(?:was |were )?(?:provided|included|available)"
    r")"
)


def _truncate(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _excerpt_summary(item: ContentItem) -> str:
    """Best-effort summary from existing content, no LLM needed."""
    if item.excerpt and len(item.excerpt) >= 20:
        return item.excerpt
    if item.body_text and len(item.body_text) >= 20:
        return _truncate(item.body_text, 300)
    # Short or missing excerpt — prefer longer text
    best = item.title
    for text in (item.excerpt or "", item.body_text or ""):
        if len(text) > len(best):
            best = text
    return _truncate(best, 300)


class ExcerptSummarizer:
    """Zero-LLM summarizer using existing excerpts and titles.

    Essential for testing the full pipeline without an API key,
    and as a baseline for eval comparisons.
    """

    async def summarize(
        self,
        section: NewsletterSection,
        items: dict[str, ContentItem],
    ) -> NewsletterSection:
        summaries = []
        for item_id in section.source_items:
            item = items.get(item_id)
            if not item:
                continue
            summaries.append(
                ItemSummary(
                    item_id=item.id,
                    title=item.title,
                    source_url=item.source_url,
                    source_name=item.source_name,
                    summary=_excerpt_summary(item),
                    relevance_score=0.5,
                )
            )

        return section.model_copy(update={"items": summaries})


class LLMSummarizer:
    """Claude Sonnet summarizer with concurrent API calls.

    Falls back to excerpt summaries when ANTHROPIC_API_KEY is not set
    or on any API error, so the pipeline never hard-fails.
    """

    MODEL = "claude-sonnet-4-20250514"
    MAX_CONCURRENT = 5

    def __init__(self) -> None:
        self._fallback = ExcerptSummarizer()

    async def summarize(
        self,
        section: NewsletterSection,
        items: dict[str, ContentItem],
    ) -> NewsletterSection:
        client = get_llm_client()
        if client is None:
            logger.info("No LLM client available, falling back to excerpts")
            return await self._fallback.summarize(section, items)

        sem = asyncio.Semaphore(self.MAX_CONCURRENT)

        # Summarize each item concurrently
        section_items = [items[iid] for iid in section.source_items if iid in items]

        async def _summarize_one(item: ContentItem) -> ItemSummary:
            body = item.body_text or item.excerpt or item.title
            # Very short sources (tweets) — title only to avoid hallucination
            if len(body) < 100:
                user_msg = f"Title: {item.title}"
            else:
                user_msg = f"Title: {item.title}\n\nBody:\n{_truncate(body)}"
            if item.published_at:
                user_msg += f"\n\nPublished: {item.published_at.strftime('%Y-%m-%d')}"
            async with sem:
                try:
                    system = load_prompt("item-summarizer", _ITEM_SYSTEM)
                    resp = await client.messages.create(
                        model=self.MODEL,
                        max_tokens=200,
                        system=system,
                        messages=[{"role": "user", "content": user_msg}],
                    )
                    summary = resp.content[0].text.strip()
                    # Fall back to excerpt if LLM refused or
                    # produced an empty/useless response
                    if not summary or _REFUSAL_RE.search(summary):
                        logger.warning(
                            "LLM returned refusal for %s, using excerpt",
                            item.title[:60],
                        )
                        summary = _excerpt_summary(item)
                except Exception:
                    logger.warning(
                        "LLM summary failed for %s, using excerpt",
                        item.title[:60],
                        exc_info=True,
                    )
                    summary = _excerpt_summary(item)

            return ItemSummary(
                item_id=item.id,
                title=item.title,
                source_url=item.source_url,
                source_name=item.source_name,
                summary=summary,
                relevance_score=0.5,
            )

        summaries = list(
            await asyncio.gather(*[_summarize_one(item) for item in section_items])
        )

        # Generate editorial prose for deep-dive sections
        prose = None
        if section.section_type == SectionType.DEEP_DIVE and summaries:
            prose = await self._generate_prose(client, sem, section.heading, summaries)

        return section.model_copy(update={"items": summaries, "prose": prose})

    async def _generate_prose(
        self,
        client: Any,
        sem: asyncio.Semaphore,
        heading: str,
        summaries: list[ItemSummary],
    ) -> str | None:
        bullet_list = "\n".join(f"- {s.title}: {s.summary}" for s in summaries)
        user_msg = f"Section: {heading}\n\nArticles:\n{bullet_list}"

        async with sem:
            try:
                system = load_prompt("prose-generator", _PROSE_SYSTEM)
                resp = await client.messages.create(
                    model=self.MODEL,
                    max_tokens=800,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                )
                return resp.content[0].text.strip()
            except Exception:
                logger.warning(
                    "LLM prose generation failed for %s", heading, exc_info=True
                )
                return None
