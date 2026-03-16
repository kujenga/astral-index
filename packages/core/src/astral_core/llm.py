"""Shared LLM client factory with optional Braintrust tracing.

All LLM callsites should use ``get_llm_client()`` instead of creating
``AsyncAnthropic`` directly. This keeps tracing configuration DRY and
ensures ``init_logger`` is called at most once per process.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_braintrust_initialized = False
_braintrust_warned = False


def get_llm_client():
    """Return an ``AsyncAnthropic`` client, or ``None`` if unavailable.

    - Returns ``None`` when ``ANTHROPIC_API_KEY`` is not set or ``anthropic``
      is not installed.
    - Wraps the client with ``braintrust.wrap_anthropic()`` when
      ``BRAINTRUST_API_KEY`` is set and the package is installed.
    - Calls ``init_logger(project="astral-index")`` at most once per process.
    - Logs a warning (once) when Braintrust is not activated.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed")
        return None

    try:
        client = anthropic.AsyncAnthropic()
    except Exception:
        logger.warning("Failed to create Anthropic client", exc_info=True)
        return None

    global _braintrust_warned

    if os.environ.get("BRAINTRUST_API_KEY"):
        try:
            from braintrust import init_logger, wrap_anthropic

            global _braintrust_initialized
            if not _braintrust_initialized:
                init_logger(project="astral-index")
                _braintrust_initialized = True

            client = wrap_anthropic(client)
        except ImportError:
            if not _braintrust_warned:
                logger.warning(
                    "BRAINTRUST_API_KEY is set but braintrust "
                    "package is not installed — tracing disabled. "
                    "Install with: uv sync --all-packages --extra braintrust"
                )
                _braintrust_warned = True
    elif not _braintrust_warned:
        logger.warning(
            "BRAINTRUST_API_KEY not set — Braintrust tracing, experiments, and "
            "prompt versioning are disabled. Set this env var to enable."
        )
        _braintrust_warned = True

    return client
