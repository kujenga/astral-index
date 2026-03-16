"""Phoenix implementations for all observability protocols.

Uses Arize Phoenix (open-source, self-hostable) for tracing, datasets,
experiments, prompts, and LLM proxy (direct OpenAI).

Env vars:
  PHOENIX_COLLECTOR_ENDPOINT — OTLP trace ingest (e.g. http://localhost:6006/v1/traces)
  PHOENIX_API_URL            — REST API base (e.g. http://localhost:6006)
  PHOENIX_API_KEY            — auth token (optional for self-hosted)
  OPENAI_API_KEY             — direct OpenAI for cross-model judges
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _extract_content(content: Any) -> str:
    """Extract text from a Phoenix content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content:
        return content[0].get("text", "")
    return ""


def _api_url() -> str:
    return os.environ.get("PHOENIX_API_URL", "http://localhost:6006")


def _api_key() -> str | None:
    return os.environ.get("PHOENIX_API_KEY")


def _get_client() -> Any:
    """Create a Phoenix REST client."""
    from phoenix.client import Client

    kwargs: dict[str, Any] = {"base_url": _api_url()}
    key = _api_key()
    if key:
        kwargs["api_key"] = key
    return Client(**kwargs)


# ---------------------------------------------------------------------------
# Phase 2: Tracing
# ---------------------------------------------------------------------------


class PhoenixTracing:
    """Instrument Anthropic clients via OpenTelemetry → Phoenix."""

    def __init__(self) -> None:
        self._tracer_provider: Any = None

    def initialize(self, project: str) -> None:
        if self._tracer_provider is not None:
            return
        try:
            from phoenix.otel import register

            endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
            kwargs: dict[str, Any] = {"project_name": project, "batch": True}
            if endpoint:
                kwargs["endpoint"] = endpoint
            self._tracer_provider = register(**kwargs)
        except Exception:
            logger.warning("Failed to initialize Phoenix tracing", exc_info=True)

    def instrument_anthropic(self, client: Any) -> Any:
        if self._tracer_provider is None:
            return client
        try:
            from openinference.instrumentation.anthropic import (
                AnthropicInstrumentor,
            )

            AnthropicInstrumentor().instrument(tracer_provider=self._tracer_provider)
        except ImportError:
            logger.debug("openinference-instrumentation-anthropic not installed")
        except Exception:
            logger.warning("Failed to instrument Anthropic for Phoenix", exc_info=True)
        # Phoenix instruments globally via OTEL — return client unchanged
        return client

    def log_scores(self, scores: dict[str, float]) -> None:
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            for k, v in scores.items():
                span.set_attribute(f"eval.{k}", v)
        except Exception:
            pass

    def log_event(self, *, input: Any, scores: dict[str, float]) -> None:
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer("astral-index")
            with tracer.start_as_current_span("score_event") as span:
                span.set_attribute("input", str(input))
                for k, v in scores.items():
                    span.set_attribute(f"eval.{k}", v)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Phase 3: Datasets + Experiments
# ---------------------------------------------------------------------------


class _PendingDataset:
    """Buffer for rows before flushing to Phoenix.

    Phoenix doesn't support empty datasets, so we accumulate rows
    in memory and create/update the dataset on flush.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []
        self.id: str | None = None


class PhoenixDatasets:
    def init_dataset(self, *, project: str, name: str) -> Any:
        return _PendingDataset(name)

    def insert_row(self, dataset: Any, *, input: Any, metadata: dict[str, Any]) -> None:
        # Phoenix requires input to be a dict. Our callers pass a list
        # of ContentItem dicts as input (one row = one week of items).
        # Wrap in {"items": ...} so Phoenix accepts it.
        if isinstance(input, list):
            input = {"items": input}
        dataset.rows.append({"input": input, "output": {}, "metadata": metadata})

    def flush_dataset(self, dataset: Any) -> None:
        if not dataset.rows:
            return
        client = _get_client()
        # Try to add to existing dataset
        try:
            existing = client.datasets.get_dataset(dataset=dataset.name)
            result = client.datasets.add_examples_to_dataset(
                dataset=existing, examples=dataset.rows
            )
            dataset.id = result.id
        except Exception:
            # Dataset doesn't exist yet — create with all rows
            result = client.datasets.create_dataset(
                name=dataset.name, examples=dataset.rows
            )
            dataset.id = result.id
        dataset.rows.clear()

    def fetch_rows(self, dataset: Any) -> list[dict[str, Any]]:
        client = _get_client()
        # dataset can be a _PendingDataset (by name) or a Phoenix Dataset
        name = dataset.name if hasattr(dataset, "name") else str(dataset)
        ds = client.datasets.get_dataset(dataset=name)
        rows = []
        for ex in ds.examples:
            input_data = ex["input"]
            # Unwrap the {"items": [...]} wrapper we added on insert
            if isinstance(input_data, dict) and "items" in input_data:
                input_data = input_data["items"]
            rows.append({"input": input_data, "metadata": ex.get("metadata", {})})
        return rows


class PhoenixExperiments:
    async def run_experiment(
        self,
        *,
        project: str,
        experiment_name: str,
        data: Any,
        task: Any,
        scorers: list[Any],
    ) -> dict[str, Any]:
        from phoenix.client.experiments import run_experiment

        client = _get_client()

        # Resolve _PendingDataset to a real Phoenix Dataset object
        if isinstance(data, _PendingDataset):
            data = client.datasets.get_dataset(dataset=data.name)

        # Phoenix passes a DatasetExample (dict-like with input/output/metadata)
        # to the task. Our task expects (input_list, hooks=None).
        # Also, Phoenix sync runner can't call async tasks, so we run
        # them in a thread with a new event loop.
        original_task = task
        is_async_task = inspect.iscoroutinefunction(task)

        def actual_task(example: Any) -> Any:
            # Extract input items from the example — unwrap our
            # {"items": [...]} wrapper if present
            input_data = example.get("input", example)
            if isinstance(input_data, dict) and "items" in input_data:
                input_data = input_data["items"]

            if is_async_task:
                import asyncio
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    future = pool.submit(asyncio.run, original_task(input_data))
                    return future.result()
            return original_task(input_data)

        result = run_experiment(
            dataset=data,
            task=actual_task,
            evaluators=scorers,
            experiment_name=experiment_name,
            client=client,
        )
        return {
            "experiment_name": experiment_name,
            "result": result,
            "tracked": True,
        }

    def wrap_scorer(self, scorer: Any, *, name: str | None = None) -> Any:
        """Adapt astral-eval scorer to Phoenix evaluator signature.

        Phoenix evaluators receive an Example object with .input and .output.
        Astral-eval scorers expect (*, output=dict, input=list[dict]).
        """
        scorer_name = name or getattr(scorer, "__name__", "unknown")
        is_async = inspect.iscoroutinefunction(scorer)

        def _phoenix_evaluator(output: Any, expected: Any = None) -> float:
            if output is None:
                return 0.0
            if is_async:
                import asyncio

                result = asyncio.get_event_loop().run_until_complete(
                    scorer(output=output, input=expected)
                )
            else:
                result = scorer(output=output, input=expected)
            if result is None:
                return 0.0
            return result.score

        _phoenix_evaluator.__name__ = scorer_name
        _phoenix_evaluator.__qualname__ = scorer_name
        return _phoenix_evaluator


# ---------------------------------------------------------------------------
# Phase 4: Prompts
# ---------------------------------------------------------------------------


class PhoenixPrompts:
    def load_prompt(
        self, *, project: str, slug: str, **template_vars: str
    ) -> str | None:
        try:
            client = _get_client()
            prompt = client.prompts.get(prompt_identifier=slug)

            # prompt.format() returns an AnthropicPrompt or similar
            # with kwargs['system'] for system messages
            formatted = prompt.format(variables=template_vars if template_vars else {})

            # AnthropicPrompt puts system content in kwargs['system']
            system = getattr(formatted, "kwargs", {}).get("system")
            if system:
                return system

            # Fallback: check messages list
            messages = getattr(formatted, "messages", [])
            for msg in messages:
                if isinstance(msg, dict) and msg.get("role") == "system":
                    return _extract_content(msg.get("content", ""))
            if messages and isinstance(messages[0], dict):
                return _extract_content(messages[0].get("content", ""))

        except Exception:
            logger.debug(
                "Failed to load prompt '%s' from Phoenix, using fallback",
                slug,
            )
        return None

    def seed_prompts(self, prompts: list[dict[str, Any]], *, project: str) -> list[str]:
        from phoenix.client.types import PromptVersion

        client = _get_client()
        seeded: list[str] = []
        for p in prompts:
            try:
                # PromptVersion takes messages as positional arg
                model = p.get("model", "")
                provider = "ANTHROPIC" if "claude" in model else "OPENAI"
                client.prompts.create(
                    name=p["slug"],
                    version=PromptVersion(
                        [{"role": "system", "content": p["prompt_text"]}],
                        model_name=model,
                        model_provider=provider,
                        description=p.get("description", ""),
                    ),
                )
                logger.info("Created prompt '%s' in Phoenix", p["slug"])
            except Exception:
                logger.warning(
                    "Failed to create prompt '%s' in Phoenix",
                    p["slug"],
                    exc_info=True,
                )
            seeded.append(p["slug"])
        return seeded


# ---------------------------------------------------------------------------
# Phase 5: LLM Proxy (direct OpenAI)
# ---------------------------------------------------------------------------


class PhoenixLLMProxy:
    """Direct OpenAI calls for cross-model judging.

    Phoenix has no AI proxy, so we call OpenAI directly when
    OPENAI_API_KEY is set. Falls through to Anthropic fallback otherwise.
    """

    async def judge(
        self,
        *,
        name: str,
        system: str,
        user_content: str,
        model: str,
    ) -> str | None:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return None

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None

        client = AsyncOpenAI(api_key=api_key)

        try:
            response = await client.chat.completions.create(
                model=model,
                max_tokens=128,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            )
        except Exception:
            logger.warning("OpenAI judge failed for %s", name, exc_info=True)
            return None

        return response.choices[0].message.content or "" if response.choices else ""
