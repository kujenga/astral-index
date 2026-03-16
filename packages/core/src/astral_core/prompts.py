"""Prompt loading with optional backend versioning.

``load_prompt()`` is the single entry point. When an observability backend
is active (Braintrust or Phoenix), it fetches the prompt from the backend
(enabling versioning and A/B testing). Otherwise it returns the ``fallback``
string unchanged.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PROJECT = "astral-index"


def load_prompt(slug: str, fallback: str, **template_vars: str) -> str:
    """Load a prompt from the active backend, falling back to the hardcoded string.

    Args:
        slug: Prompt slug (e.g. ``"item-summarizer"``).
        fallback: Hardcoded prompt string used when no backend is available.
        **template_vars: Template variables passed to the backend.

    Returns:
        The rendered prompt string.
    """
    from .observability import get_prompts

    result = get_prompts().load_prompt(project=_PROJECT, slug=slug, **template_vars)
    if result is not None:
        return result
    return fallback
