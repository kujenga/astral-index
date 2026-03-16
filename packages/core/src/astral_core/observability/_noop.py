"""No-op implementations for all observability protocols.

Used when no backend is configured, or as stubs for capabilities
a backend hasn't implemented yet (e.g. Phoenix prompts in Phase 2).
"""

from __future__ import annotations

from typing import Any


class NoopTracing:
    def initialize(self, project: str) -> None:
        pass

    def instrument_anthropic(self, client: Any) -> Any:
        return client

    def log_scores(self, scores: dict[str, float]) -> None:
        pass

    def log_event(self, *, input: Any, scores: dict[str, float]) -> None:
        pass


class NoopPrompts:
    def load_prompt(
        self, *, project: str, slug: str, **template_vars: str
    ) -> str | None:
        return None

    def seed_prompts(self, prompts: list[dict[str, Any]], *, project: str) -> list[str]:
        return []


class NoopDatasets:
    def init_dataset(self, *, project: str, name: str) -> Any:
        return None

    def insert_row(self, dataset: Any, *, input: Any, metadata: dict[str, Any]) -> None:
        pass

    def flush_dataset(self, dataset: Any) -> None:
        pass

    def fetch_rows(self, dataset: Any) -> list[dict[str, Any]]:
        return []


class NoopExperiments:
    async def run_experiment(
        self,
        *,
        project: str,
        experiment_name: str,
        data: Any,
        task: Any,
        scorers: list[Any],
    ) -> dict[str, Any]:
        return {"experiment_name": experiment_name, "tracked": False}

    def wrap_scorer(self, scorer: Any, *, name: str | None = None) -> Any:
        return scorer


class NoopLLMProxy:
    async def judge(
        self,
        *,
        name: str,
        system: str,
        user_content: str,
        model: str,
    ) -> str | None:
        return None
