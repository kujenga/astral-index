"""Protocol definitions for the observability abstraction layer.

Each protocol represents one capability that can be backed by different
providers (Braintrust, Phoenix, or noop).
"""

from __future__ import annotations

from typing import Any, Protocol


class TracingBackend(Protocol):
    """Instrument LLM clients and log scores to the active trace."""

    def initialize(self, project: str) -> None: ...
    def instrument_anthropic(self, client: Any) -> Any: ...
    def log_scores(self, scores: dict[str, float]) -> None: ...
    def log_event(self, *, input: Any, scores: dict[str, float]) -> None: ...


class PromptBackend(Protocol):
    """Load and seed versioned prompts."""

    def load_prompt(
        self, *, project: str, slug: str, **template_vars: str
    ) -> str | None: ...

    def seed_prompts(
        self, prompts: list[dict[str, Any]], *, project: str
    ) -> list[str]: ...


class DatasetBackend(Protocol):
    """CRUD for evaluation datasets."""

    def init_dataset(self, *, project: str, name: str) -> Any: ...
    def insert_row(
        self, dataset: Any, *, input: Any, metadata: dict[str, Any]
    ) -> None: ...
    def flush_dataset(self, dataset: Any) -> None: ...
    def fetch_rows(self, dataset: Any) -> list[dict[str, Any]]: ...


class ExperimentBackend(Protocol):
    """Run tracked experiments."""

    async def run_experiment(
        self,
        *,
        project: str,
        experiment_name: str,
        data: Any,
        task: Any,
        scorers: list[Any],
    ) -> dict[str, Any]: ...

    def wrap_scorer(self, scorer: Any, *, name: str | None = None) -> Any: ...


class LLMProxyBackend(Protocol):
    """Route LLM judge calls through an AI proxy."""

    async def judge(
        self,
        *,
        name: str,
        system: str,
        user_content: str,
        model: str,
    ) -> str | None: ...
