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


class PhoenixDatasets:
    def init_dataset(self, *, project: str, name: str) -> Any:
        client = _get_client()
        # Try to fetch existing dataset first
        try:
            return client.datasets.get_dataset(name=name)
        except Exception:
            pass
        # Create new
        return client.datasets.create_dataset(name=name, examples=[])

    def insert_row(self, dataset: Any, *, input: Any, metadata: dict[str, Any]) -> None:
        # Phoenix datasets use examples with input/output/metadata dicts
        client = _get_client()
        client.datasets.add_examples_to_dataset(
            dataset_id=dataset.id,
            examples=[
                {"input": input, "metadata": metadata},
            ],
        )

    def flush_dataset(self, dataset: Any) -> None:
        # Phoenix REST API commits immediately — no flush needed
        pass

    def fetch_rows(self, dataset: Any) -> list[dict[str, Any]]:
        client = _get_client()
        ds = client.datasets.get_dataset(dataset_id=dataset.id)
        examples = client.datasets.get_examples(dataset_id=ds.id)
        return [{"input": ex.input, "metadata": ex.metadata} for ex in examples]


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

        # Phoenix run_experiment expects a dataset object and evaluator fns
        # with signature (output, expected) -> float
        result = run_experiment(
            dataset=data,
            task=task,
            evaluators=scorers,
            experiment_name=experiment_name,
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
            # output is the task return value (dict)
            # For sync scorers
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
            if template_vars:
                formatted = prompt.format(variables=template_vars)
                # formatted is a dict with "messages" key
                messages = formatted.get("messages", [])
                for msg in messages:
                    if msg.get("role") == "system":
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            # Handle structured content blocks
                            return content[0].get("text", "")
                        return content
                if messages:
                    content = messages[0].get("content", "")
                    if isinstance(content, list):
                        return content[0].get("text", "")
                    return content
            else:
                # Access template messages directly
                template = getattr(prompt, "_template", None) or {}
                messages = template.get("messages", [])
                for msg in messages:
                    content = msg.get("content", "")
                    if msg.get("role") == "system":
                        if isinstance(content, list):
                            return content[0].get("text", "")
                        return content
                if messages:
                    content = messages[0].get("content", "")
                    if isinstance(content, list):
                        return content[0].get("text", "")
                    return content
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
                client.prompts.create(
                    name=p["slug"],
                    version=PromptVersion(
                        messages=[{"role": "system", "content": p["prompt_text"]}],
                        model_name=p.get("model", ""),
                    ),
                    prompt_description=p.get("description", ""),
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
