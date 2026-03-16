"""Braintrust implementations for all observability protocols.

Extracted from the original scattered ``import braintrust`` callsites
into a single module. Each class checks for ``BRAINTRUST_API_KEY`` and
the ``braintrust`` package, degrading gracefully when unavailable.
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT = "astral-index"
_BRAINTRUST_API = "https://api.braintrust.dev/v1"


class BraintrustTracing:
    """Wraps Anthropic clients with Braintrust tracing.

    Tracing is gated behind ``BRAINTRUST_TRACE=1`` to avoid consuming
    free-tier span limits during routine operational runs.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._warned = False

    def initialize(self, project: str) -> None:
        if self._initialized:
            return
        if not os.environ.get("BRAINTRUST_TRACE"):
            return
        try:
            from braintrust import init_logger

            init_logger(project=project)
            self._initialized = True
        except ImportError:
            if not self._warned:
                logger.warning(
                    "BRAINTRUST_TRACE is set but braintrust "
                    "package is not installed — tracing disabled. "
                    "Install with: uv sync --all-packages --extra braintrust"
                )
                self._warned = True

    def instrument_anthropic(self, client: Any) -> Any:
        if not os.environ.get("BRAINTRUST_TRACE"):
            return client
        try:
            from braintrust import wrap_anthropic

            return wrap_anthropic(client)
        except ImportError:
            return client

    def log_scores(self, scores: dict[str, float]) -> None:
        try:
            import braintrust

            span = braintrust.current_span()
            span.log(scores=scores)
        except Exception:
            pass

    def log_event(self, *, input: Any, scores: dict[str, float]) -> None:
        try:
            import braintrust

            if os.environ.get("BRAINTRUST_API_KEY"):
                bt_logger = braintrust.init_logger(project=_PROJECT)
                bt_logger.log(input=input, scores=scores)
        except Exception:
            pass


class BraintrustPrompts:
    def load_prompt(
        self, *, project: str, slug: str, **template_vars: str
    ) -> str | None:
        if not os.environ.get("BRAINTRUST_API_KEY"):
            return None
        try:
            import braintrust

            prompt = braintrust.load_prompt(project=project, slug=slug)
            rendered = prompt.build(**template_vars)
            if isinstance(rendered, dict):
                messages = rendered.get("messages", [])
                for msg in messages:
                    if msg.get("role") == "system":
                        return msg["content"]
                if messages:
                    return messages[0].get("content")
            elif isinstance(rendered, str):
                return rendered
        except Exception:
            logger.debug(
                "Failed to load prompt '%s' from Braintrust, using fallback",
                slug,
            )
        return None

    def seed_prompts(self, prompts: list[dict[str, Any]], *, project: str) -> list[str]:
        import httpx

        api_key = os.environ.get("BRAINTRUST_API_KEY")
        if not api_key:
            logger.warning("BRAINTRUST_API_KEY not set — cannot seed prompts.")
            raise SystemExit(1)

        client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )

        try:
            project_id = _get_or_create_project(client)

            seeded: list[str] = []
            for p in prompts:
                body = {
                    "name": p["slug"],
                    "slug": p["slug"],
                    "project_id": project_id,
                    "description": p["description"],
                    "prompt_data": {
                        "prompt": {
                            "type": "chat",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": p["prompt_text"],
                                }
                            ],
                        },
                        "options": {"model": p["model"]},
                    },
                }

                resp = client.post(f"{_BRAINTRUST_API}/prompt", json=body)
                if resp.status_code == 409:
                    logger.info("Prompt '%s' already exists, skipping", p["slug"])
                elif resp.is_success:
                    logger.info("Created prompt '%s'", p["slug"])
                else:
                    logger.warning(
                        "Failed to create prompt '%s': %s %s",
                        p["slug"],
                        resp.status_code,
                        resp.text[:200],
                    )

                seeded.append(p["slug"])

            return seeded
        finally:
            client.close()


def _get_or_create_project(client: Any) -> str:
    """Get the project ID, creating the project if needed."""
    resp = client.get(f"{_BRAINTRUST_API}/project", params={"project_name": _PROJECT})
    if resp.status_code == 200:
        data = resp.json()
        objects = data.get("objects", [])
        if objects:
            return objects[0]["id"]

    resp = client.post(f"{_BRAINTRUST_API}/project", json={"name": _PROJECT})
    resp.raise_for_status()
    return resp.json()["id"]


class BraintrustDatasets:
    def init_dataset(self, *, project: str, name: str) -> Any:
        import braintrust

        return braintrust.init_dataset(project=project, name=name)

    def insert_row(self, dataset: Any, *, input: Any, metadata: dict[str, Any]) -> None:
        dataset.insert(input=input, metadata=metadata)

    def flush_dataset(self, dataset: Any) -> None:
        dataset.flush()

    def fetch_rows(self, dataset: Any) -> list[dict[str, Any]]:
        return list(dataset.fetch())


class BraintrustExperiments:
    async def run_experiment(
        self,
        *,
        project: str,
        experiment_name: str,
        data: Any,
        task: Any,
        scorers: list[Any],
    ) -> dict[str, Any]:
        import braintrust

        result = await braintrust.EvalAsync(
            project,
            experiment_name=experiment_name,
            data=data,
            task=task,
            scores=scorers,
        )
        return {
            "experiment_name": experiment_name,
            "result": result,
            "tracked": True,
        }

    def wrap_scorer(self, scorer: Any, *, name: str | None = None) -> Any:
        scorer_name = name or getattr(scorer, "__name__", "unknown")
        is_async = inspect.iscoroutinefunction(scorer)

        from astral_eval.scores import Score

        async def _bt_scorer(
            input: Any,
            output: Any,
            expected: Any = None,
            **kwargs: Any,
        ) -> dict[str, Any] | None:
            if is_async:
                result: Score | None = await scorer(output=output, input=input)
            else:
                result = scorer(output=output, input=input)

            if result is None:
                return None

            return {
                "name": result.name,
                "score": result.score,
                "metadata": result.metadata,
            }

        _bt_scorer.__name__ = f"bt_{scorer_name}"
        _bt_scorer.__qualname__ = f"bt_{scorer_name}"
        return _bt_scorer


class BraintrustLLMProxy:
    """Route LLM judge calls through Braintrust AI Proxy (OpenAI SDK)."""

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

        api_key = os.environ.get("BRAINTRUST_API_KEY")
        if not api_key:
            return None

        client = AsyncOpenAI(
            base_url="https://api.braintrust.dev/v1/proxy",
            api_key=api_key,
        )

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
            logger.warning("Braintrust proxy judge failed for %s", name, exc_info=True)
            return None

        return response.choices[0].message.content or "" if response.choices else ""
