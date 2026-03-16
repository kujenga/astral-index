"""Push hardcoded prompts to the active observability backend.

Run via: astral-eval seed-prompts
"""

from __future__ import annotations

import logging
from typing import Any

from astral_core.observability import get_backend_name, get_prompts

logger = logging.getLogger(__name__)

_PROJECT = "astral-index"


def _collect_prompts() -> list[dict[str, Any]]:
    """Collect prompt definitions from their source modules."""
    from astral_author.draft import _INTRO_SYSTEM
    from astral_author.summarize import _ITEM_SYSTEM, _PROSE_SYSTEM
    from astral_ingest.classify.llm import _SYSTEM_PROMPT

    return [
        {
            "slug": "item-summarizer",
            "prompt_text": _ITEM_SYSTEM,
            "model": "claude-sonnet-4-20250514",
            "description": "Per-item summary prompt for the LLMSummarizer",
        },
        {
            "slug": "prose-generator",
            "prompt_text": _PROSE_SYSTEM,
            "model": "claude-sonnet-4-20250514",
            "description": "Editorial prose generation for deep-dive sections",
        },
        {
            "slug": "newsletter-intro",
            "prompt_text": _INTRO_SYSTEM,
            "model": "claude-sonnet-4-20250514",
            "description": "Newsletter introduction hook from top headlines",
        },
        {
            "slug": "category-classifier",
            "prompt_text": _SYSTEM_PROMPT,
            "model": "claude-haiku-4-5-20251001",
            "description": "Space news category classifier (LLM fallback pass)",
        },
    ]


def seed_prompts(*, dry_run: bool = False) -> list[str]:
    """Push current hardcoded prompts to the active backend.

    Returns list of slugs that were seeded.
    """
    if get_backend_name() == "noop":
        logger.warning(
            "No observability backend configured — cannot seed prompts. "
            "Set BRAINTRUST_API_KEY or PHOENIX_COLLECTOR_ENDPOINT to enable."
        )
        raise SystemExit(1)

    prompts = _collect_prompts()

    if dry_run:
        return [p["slug"] for p in prompts]

    return get_prompts().seed_prompts(prompts, project=_PROJECT)
