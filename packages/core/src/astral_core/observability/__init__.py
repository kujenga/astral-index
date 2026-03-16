"""Observability abstraction layer.

Provides backend-agnostic access to tracing, prompts, datasets,
experiments, and LLM proxy capabilities. The active backend is
selected by ``ASTRAL_OBSERVABILITY_BACKEND`` env var (default: auto).
"""

from ._resolve import (
    get_backend_name,
    get_datasets,
    get_experiments,
    get_llm_proxy,
    get_prompts,
    get_tracing,
    reset,
)

__all__ = [
    "get_backend_name",
    "get_datasets",
    "get_experiments",
    "get_llm_proxy",
    "get_prompts",
    "get_tracing",
    "reset",
]
