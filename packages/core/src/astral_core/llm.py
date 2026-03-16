"""Shared LLM client factory with optional Braintrust tracing.

All LLM callsites should use ``get_llm_client()`` instead of creating
``AsyncAnthropic`` directly. This keeps tracing configuration DRY and
ensures ``init_logger`` is called at most once per process.

Tracing (``init_logger`` + ``wrap_anthropic``) is gated behind
``BRAINTRUST_TRACE=1`` to avoid consuming free-tier span limits during
routine operational runs.  Other Braintrust features (prompts, datasets,
experiments) work with just ``BRAINTRUST_API_KEY``.
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
    - Wraps the client with ``braintrust.wrap_anthropic()`` when both
      ``BRAINTRUST_API_KEY`` and ``BRAINTRUST_TRACE`` are set.
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

    if os.environ.get("BRAINTRUST_API_KEY") and os.environ.get("BRAINTRUST_TRACE"):
        # Tracing is opt-in to avoid consuming free-tier span limits.
        # Experiments, prompts, and datasets work without tracing.
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
                    "BRAINTRUST_TRACE is set but braintrust "
                    "package is not installed — tracing disabled. "
                    "Install with: uv sync --all-packages --extra braintrust"
                )
                _braintrust_warned = True
    elif not os.environ.get("BRAINTRUST_API_KEY") and not _braintrust_warned:
        logger.warning(
            "BRAINTRUST_API_KEY not set — Braintrust tracing, experiments, and "
            "prompt versioning are disabled. Set this env var to enable."
        )
        _braintrust_warned = True

    return client
