"""Global backend resolution with cached singletons.

One env var ``ASTRAL_OBSERVABILITY_BACKEND`` selects the backend:
``phoenix``, ``braintrust``, or ``auto`` (default). ``auto`` detects
from environment variables. Each capability getter lazily creates and
caches its singleton.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._types import (
        DatasetBackend,
        ExperimentBackend,
        LLMProxyBackend,
        PromptBackend,
        TracingBackend,
    )

logger = logging.getLogger(__name__)

_backend_name: str | None = None
_tracing: TracingBackend | None = None
_prompts: PromptBackend | None = None
_datasets: DatasetBackend | None = None
_experiments: ExperimentBackend | None = None
_llm_proxy: LLMProxyBackend | None = None


def get_backend_name() -> str:
    """Resolve which backend to use, caching the result."""
    global _backend_name
    if _backend_name is None:
        explicit = os.environ.get("ASTRAL_OBSERVABILITY_BACKEND", "auto")
        if explicit != "auto":
            _backend_name = explicit
        elif os.environ.get("PHOENIX_COLLECTOR_ENDPOINT") or os.environ.get(
            "PHOENIX_API_URL"
        ):
            _backend_name = "phoenix"
        elif os.environ.get("BRAINTRUST_API_KEY"):
            _backend_name = "braintrust"
        else:
            _backend_name = "noop"
    return _backend_name


def get_tracing() -> TracingBackend:
    global _tracing
    if _tracing is None:
        name = get_backend_name()
        if name == "braintrust":
            from ._braintrust import BraintrustTracing

            _tracing = BraintrustTracing()
        elif name == "phoenix":
            from ._phoenix import PhoenixTracing

            _tracing = PhoenixTracing()
        else:
            from ._noop import NoopTracing

            _tracing = NoopTracing()
    return _tracing


def get_prompts() -> PromptBackend:
    global _prompts
    if _prompts is None:
        name = get_backend_name()
        if name == "braintrust":
            from ._braintrust import BraintrustPrompts

            _prompts = BraintrustPrompts()
        elif name == "phoenix":
            from ._phoenix import PhoenixPrompts

            _prompts = PhoenixPrompts()
        else:
            from ._noop import NoopPrompts

            _prompts = NoopPrompts()
    return _prompts


def get_datasets() -> DatasetBackend:
    global _datasets
    if _datasets is None:
        name = get_backend_name()
        if name == "braintrust":
            from ._braintrust import BraintrustDatasets

            _datasets = BraintrustDatasets()
        elif name == "phoenix":
            from ._phoenix import PhoenixDatasets

            _datasets = PhoenixDatasets()
        else:
            from ._noop import NoopDatasets

            _datasets = NoopDatasets()
    return _datasets


def get_experiments() -> ExperimentBackend:
    global _experiments
    if _experiments is None:
        name = get_backend_name()
        if name == "braintrust":
            from ._braintrust import BraintrustExperiments

            _experiments = BraintrustExperiments()
        elif name == "phoenix":
            from ._phoenix import PhoenixExperiments

            _experiments = PhoenixExperiments()
        else:
            from ._noop import NoopExperiments

            _experiments = NoopExperiments()
    return _experiments


def get_llm_proxy() -> LLMProxyBackend:
    global _llm_proxy
    if _llm_proxy is None:
        name = get_backend_name()
        if name == "braintrust":
            from ._braintrust import BraintrustLLMProxy

            _llm_proxy = BraintrustLLMProxy()
        elif name == "phoenix":
            from ._phoenix import PhoenixLLMProxy

            _llm_proxy = PhoenixLLMProxy()
        else:
            from ._noop import NoopLLMProxy

            _llm_proxy = NoopLLMProxy()
    return _llm_proxy


def reset() -> None:
    """Reset all cached singletons. Used in tests."""
    global _backend_name, _tracing, _prompts, _datasets, _experiments, _llm_proxy
    _backend_name = None
    _tracing = None
    _prompts = None
    _datasets = None
    _experiments = None
    _llm_proxy = None
