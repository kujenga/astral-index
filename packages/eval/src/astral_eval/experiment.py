"""Experiment runner with fallback to the local eval runner.

Delegates to the active observability backend for experiment tracking,
while keeping the local ``run_quality_eval()`` path for environments
without a backend configured.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import click

from astral_author.pipeline import build_strategy
from astral_core import ContentItem
from astral_core.observability import get_backend_name, get_datasets, get_experiments

logger = logging.getLogger(__name__)


def _backend_available() -> bool:
    """Check if an observability backend is configured for experiments."""
    return get_backend_name() not in ("noop",)


async def run_experiment(
    strategy_name: str,
    items: list[ContentItem],
    *,
    experiment_name: str | None = None,
    max_items: int = 50,
    use_llm: bool = True,
    dataset_name: str | None = None,
) -> dict[str, Any]:
    """Run a tracked experiment, or fall back to local eval.

    Returns a dict with ``scores`` (dict[str, Score]) and ``experiment_name``.
    """
    if experiment_name is None:
        experiment_name = f"{strategy_name}-{date.today().isoformat()}"

    backend_name = get_backend_name()
    if backend_name == "noop":
        logger.warning(
            "No observability backend configured — running local eval only. "
            "Set BRAINTRUST_API_KEY or PHOENIX_COLLECTOR_ENDPOINT to enable "
            "experiment tracking."
        )
        local_items, expected = _resolve_local_dataset(items, dataset_name=dataset_name)
        return await _run_local(
            strategy_name,
            local_items,
            max_items=max_items,
            use_llm=use_llm,
            experiment_name=experiment_name,
            expected=expected,
        )

    return await _run_tracked(
        strategy_name,
        items,
        experiment_name=experiment_name,
        max_items=max_items,
        use_llm=use_llm,
        dataset_name=dataset_name,
    )


def _resolve_local_dataset(
    items: list[ContentItem],
    *,
    dataset_name: str | None,
    base_dir: str = "data",
) -> tuple[list[ContentItem], str | None]:
    """Resolve items and OI reference for a named dataset in local mode.

    When a standard dataset name is provided but Braintrust is unavailable,
    this loads items from the dataset's date windows and fetches OI reference
    text for windows that have matching Orbital Index issues.

    Returns (items, expected) where expected is concatenated OI text or None.
    """
    if not dataset_name:
        return items, None

    from .datasets import (
        _OI_WINDOWS,
        STANDARD_DATASETS,
        _list_items_by_date_dir,
        _window_to_datetimes,
    )

    if dataset_name not in STANDARD_DATASETS:
        # Not a standard dataset — can't resolve locally
        logger.warning(
            "Dataset '%s' is not a standard dataset — cannot load locally. "
            "Using provided items instead.",
            dataset_name,
        )
        return items, None

    window_keys = STANDARD_DATASETS[dataset_name]

    # Load items from all windows
    all_items: list[ContentItem] = []
    for key in window_keys:
        since, until = _window_to_datetimes(key)
        window_items = _list_items_by_date_dir(base_dir, since, until)
        all_items.extend(window_items)

    if not all_items:
        logger.warning(
            "No items found for dataset '%s' windows — using provided items",
            dataset_name,
        )
        all_items = items

    # Resolve OI reference for windows that have it
    oi_windows = [k for k in window_keys if k in _OI_WINDOWS]
    expected: str | None = None
    if oi_windows:
        from .oi_reference import get_oi_reference

        texts: list[str] = []
        for key in oi_windows:
            since, until = _window_to_datetimes(key)
            text = get_oi_reference(since.date(), until.date())
            if text:
                texts.append(text)
        if texts:
            expected = "\n\n---\n\n".join(texts)

    return all_items, expected


async def _run_local(
    strategy_name: str,
    items: list[ContentItem],
    *,
    max_items: int,
    use_llm: bool,
    experiment_name: str,
    expected: str | None = None,
) -> dict[str, Any]:
    """Fallback: run with the existing local eval runner."""
    from .runner import run_quality_eval

    pipeline = build_strategy(strategy_name)
    draft = await pipeline.run(items, max_items=max_items)
    scores = await run_quality_eval(draft, items, use_llm=use_llm, expected=expected)

    return {
        "experiment_name": experiment_name,
        "scores": scores,
        "draft": draft,
        "tracked": False,
    }


async def _run_tracked(
    strategy_name: str,
    items: list[ContentItem],
    *,
    experiment_name: str,
    max_items: int,
    use_llm: bool,
    dataset_name: str | None,
) -> dict[str, Any]:
    """Run experiment via the active observability backend."""
    from .braintrust_scorers import ALL_BT_SCORERS, HEURISTIC_BT_SCORERS

    scorers = ALL_BT_SCORERS if use_llm else HEURISTIC_BT_SCORERS

    # Load data — either from a backend dataset or local items.
    if dataset_name:
        datasets = get_datasets()
        data = datasets.init_dataset(project="astral-index", name=dataset_name)
        rows = datasets.fetch_rows(data)
        if not rows:
            raise click.ClickException(
                f"Dataset '{dataset_name}' is empty (0 rows). "
                "Upload data first with: "
                "astral-eval upload-dataset --since <date> "
                "--name <name>"
            )
        logger.info("Loaded dataset '%s' with %d row(s)", dataset_name, len(rows))
    else:
        input_data = [item.model_dump(mode="json") for item in items]
        data = [{"input": input_data}]

    async def task(input: Any, hooks: Any = None) -> dict[str, Any]:
        task_items = [ContentItem.model_validate(d) for d in input]
        pipeline = build_strategy(strategy_name)
        draft = await pipeline.run(task_items, max_items=max_items)
        return draft.model_dump(mode="json")

    experiments = get_experiments()
    return await experiments.run_experiment(
        project="astral-index",
        experiment_name=experiment_name,
        data=data,
        task=task,
        scorers=scorers,
    )
