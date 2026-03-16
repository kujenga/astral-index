"""Phoenix implementations — stubs for Phase 1, filled in across Phases 2-5."""

from __future__ import annotations

from ._noop import (
    NoopDatasets,
    NoopExperiments,
    NoopLLMProxy,
    NoopPrompts,
    NoopTracing,
)

# Phase 1: all capabilities are noop stubs.
# Phase 2 will fill in PhoenixTracing.
# Phase 3 will fill in PhoenixDatasets and PhoenixExperiments.
# Phase 4 will fill in PhoenixPrompts.
# Phase 5 will fill in PhoenixLLMProxy (direct OpenAI).


class PhoenixTracing(NoopTracing):
    pass


class PhoenixPrompts(NoopPrompts):
    pass


class PhoenixDatasets(NoopDatasets):
    pass


class PhoenixExperiments(NoopExperiments):
    pass


class PhoenixLLMProxy(NoopLLMProxy):
    pass
