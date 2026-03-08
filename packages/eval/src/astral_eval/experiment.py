"""Braintrust experiment runner with fallback to the local eval runner.

Wraps the existing scorer infrastructure into ``braintrust.Eval()`` for
experiment tracking, while keeping the local ``run_quality_eval()`` path
for environments without Braintrust.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from astral_author.pipeline import build_strategy
from astral_core import ContentItem

logger = logging.getLogger(__name__)


def _braintrust_available() -> bool:
    try:
        import braintrust  # noqa: F401

        return True
    except ImportError:
        return False


async def run_experiment(
    strategy_name: str,
    items: list[ContentItem],
    *,
    experiment_name: str | None = None,
    max_items: int = 50,
    use_llm: bool = True,
    dataset_name: str | None = None,
) -> dict[str, Any]:
    """Run a Braintrust-tracked experiment, or fall back to local eval.

    Returns a dict with ``scores`` (dict[str, Score]) and ``experiment_name``.
    """
    if experiment_name is None:
        experiment_name = f"{strategy_name}-{date.today().isoformat()}"

    if not _braintrust_available():
        logger.warning(
            "braintrust package not installed — running local eval only. "
            "Install with: uv sync --all-packages --extra braintrust"
        )
        return await _run_local(
            strategy_name,
            items,
            max_items=max_items,
            use_llm=use_llm,
            experiment_name=experiment_name,
        )

    import os

    if not os.environ.get("BRAINTRUST_API_KEY"):
        logger.warning(
            "BRAINTRUST_API_KEY not set — running local eval only. "
            "Set this environment variable to enable Braintrust experiment tracking."
        )
        return await _run_local(
            strategy_name,
            items,
            max_items=max_items,
            use_llm=use_llm,
            experiment_name=experiment_name,
        )

    return await _run_braintrust(
        strategy_name,
        items,
        experiment_name=experiment_name,
        max_items=max_items,
        use_llm=use_llm,
        dataset_name=dataset_name,
    )


async def _run_local(
    strategy_name: str,
    items: list[ContentItem],
    *,
    max_items: int,
    use_llm: bool,
    experiment_name: str,
) -> dict[str, Any]:
    """Fallback: run with the existing local eval runner."""
    from .runner import run_quality_eval

    pipeline = build_strategy(strategy_name)
    draft = await pipeline.run(items, max_items=max_items)
    scores = await run_quality_eval(draft, items, use_llm=use_llm)

    return {
        "experiment_name": experiment_name,
        "scores": scores,
        "draft": draft,
        "tracked": False,
    }


async def _run_braintrust(
    strategy_name: str,
    items: list[ContentItem],
    *,
    experiment_name: str,
    max_items: int,
    use_llm: bool,
    dataset_name: str | None,
) -> dict[str, Any]:
    """Run experiment via braintrust.Eval() with wrapped scorers."""
    import braintrust

    from .braintrust_scorers import ALL_BT_SCORERS, HEURISTIC_BT_SCORERS

    scorers = ALL_BT_SCORERS if use_llm else HEURISTIC_BT_SCORERS

    # Load data — either from a Braintrust dataset or local items.
    # Pass Dataset objects directly so EvalAsync links the experiment to the
    # dataset and handles iteration internally.
    if dataset_name:
        data = braintrust.init_dataset(project="astral-index", name=dataset_name)
    else:
        # Each test case is one full week → 1-row eval
        input_data = [item.model_dump(mode="json") for item in items]
        data = [{"input": input_data}]

    # The task function: run the authoring pipeline and return serialized draft
    async def task(input: Any, hooks: Any = None) -> dict[str, Any]:
        # input is a list of ContentItem dicts; reconstruct
        task_items = [ContentItem.model_validate(d) for d in input]
        pipeline = build_strategy(strategy_name)
        draft = await pipeline.run(task_items, max_items=max_items)
        return draft.model_dump(mode="json")

    result = await braintrust.EvalAsync(
        "astral-index",
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
