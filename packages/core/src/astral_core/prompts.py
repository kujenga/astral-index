"""Prompt loading with optional Braintrust versioning.

``load_prompt()`` is the single entry point. When ``BRAINTRUST_API_KEY``
is set and the ``braintrust`` package is installed, it fetches the prompt
from Braintrust (enabling versioning and A/B testing). Otherwise it
returns the ``fallback`` string unchanged.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def load_prompt(slug: str, fallback: str, **template_vars: str) -> str:
    """Load a prompt from Braintrust, falling back to the hardcoded string.

    Args:
        slug: Braintrust prompt slug (e.g. ``"item-summarizer"``).
        fallback: Hardcoded prompt string used when Braintrust is unavailable.
        **template_vars: Template variables passed to ``prompt.build()``.

    Returns:
        The rendered prompt string.
    """
    if not os.environ.get("BRAINTRUST_API_KEY"):
        return fallback

    try:
        import braintrust

        prompt = braintrust.load_prompt(project="astral-index", slug=slug)
        rendered = prompt.build(**template_vars)
        # build() returns a dict with "messages" or a string depending on
        # the prompt type; we need the system message content
        if isinstance(rendered, dict):
            messages = rendered.get("messages", [])
            for msg in messages:
                if msg.get("role") == "system":
                    return msg["content"]
            # If no system message, return the first message content
            if messages:
                return messages[0].get("content", fallback)
        elif isinstance(rendered, str):
            return rendered
    except Exception:
        logger.debug("Failed to load prompt '%s' from Braintrust, using fallback", slug)

    return fallback
