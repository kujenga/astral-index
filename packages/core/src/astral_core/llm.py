"""Shared LLM client factory with optional tracing.

All LLM callsites should use ``get_llm_client()`` instead of creating
``AsyncAnthropic`` directly. This keeps tracing configuration DRY and
ensures initialization happens at most once per process.

Tracing activation is delegated to the observability backend — for
Braintrust, it's gated behind ``BRAINTRUST_TRACE=1``; for Phoenix,
it activates when ``PHOENIX_COLLECTOR_ENDPOINT`` is set.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_warned = False


def get_llm_client():
    """Return an ``AsyncAnthropic`` client, or ``None`` if unavailable.

    - Returns ``None`` when ``ANTHROPIC_API_KEY`` is not set or ``anthropic``
      is not installed.
    - Instruments the client via the active observability backend's tracing.
    - Logs a warning (once) when no observability backend is active.
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

    from .observability import get_tracing

    tracing = get_tracing()
    tracing.initialize("astral-index")
    client = tracing.instrument_anthropic(client)

    global _warned
    if not os.environ.get("BRAINTRUST_API_KEY") and not _warned:
        from .observability import get_backend_name

        if get_backend_name() == "noop":
            logger.warning(
                "No observability backend configured — tracing, experiments, "
                "and prompt versioning are disabled. Set BRAINTRUST_API_KEY "
                "or PHOENIX_COLLECTOR_ENDPOINT to enable."
            )
            _warned = True

    return client
