"""Golden-week dataset management for reproducible Braintrust experiments.

Upload frozen sets of ContentItems to Braintrust as named datasets, enabling
consistent regression testing across pipeline changes.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from astral_core import ContentItem, ContentStore

logger = logging.getLogger(__name__)


def upload_golden_week(
    *,
    since: datetime,
    until: datetime | None = None,
    dataset_name: str,
    base_dir: str = "data",
) -> dict[str, Any]:
    """Read items from ContentStore and upload to Braintrust as a dataset.

    Each row is one week's worth of items (input = full item list). This
    matches the 1-row-per-eval design in the experiment runner.

    Returns metadata about the uploaded dataset.
    """
    try:
        import braintrust
    except ImportError:
        logger.warning(
            "braintrust package not installed — cannot upload dataset. "
            "Install with: uv sync --all-packages --extra braintrust"
        )
        raise SystemExit(1) from None

    import os

    if not os.environ.get("BRAINTRUST_API_KEY"):
        logger.warning(
            "BRAINTRUST_API_KEY not set — cannot upload dataset. "
            "Set this environment variable to enable Braintrust dataset uploads."
        )
        raise SystemExit(1)

    store = ContentStore(base_dir=base_dir)
    items = store.list_items(since=since, before=until)

    if not items:
        logger.warning("No items found in date range")
        raise SystemExit(1)

    # Build category breakdown for metadata
    cat_counts: Counter[str] = Counter()
    for item in items:
        for cat in item.categories:
            cat_counts[cat] += 1

    date_range = _date_range(items)
    input_data = [item.model_dump(mode="json") for item in items]

    dataset = braintrust.init_dataset(project="astral-index", name=dataset_name)
    dataset.insert(
        input=input_data,
        metadata={
            "item_count": len(items),
            "date_range": date_range,
            "categories": dict(cat_counts),
        },
    )
    dataset.flush()

    return {
        "dataset_name": dataset_name,
        "item_count": len(items),
        "date_range": date_range,
        "categories": dict(cat_counts),
    }


def _week_ranges(
    since: datetime, until: datetime, period_days: int = 7
) -> list[tuple[datetime, datetime]]:
    """Split a date range into non-overlapping chunks of *period_days*."""
    chunks: list[tuple[datetime, datetime]] = []
    cursor = since
    while cursor < until:
        chunk_end = min(cursor + timedelta(days=period_days), until)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def upload_golden_set(
    *,
    weeks: list[tuple[datetime, datetime]],
    dataset_name: str,
    base_dir: str = "data",
) -> dict[str, Any]:
    """Upload multiple week-windows as separate rows in one Braintrust dataset.

    Each (since, until) pair becomes one dataset row whose ``input`` is
    the list of ContentItem dicts for that window. When ``EvalAsync`` runs
    against this dataset it evaluates each row independently; Braintrust
    averages scores across rows.
    """
    try:
        import braintrust
    except ImportError:
        logger.warning(
            "braintrust package not installed — cannot upload dataset. "
            "Install with: uv sync --all-packages --extra braintrust"
        )
        raise SystemExit(1) from None

    import os

    if not os.environ.get("BRAINTRUST_API_KEY"):
        logger.warning(
            "BRAINTRUST_API_KEY not set — cannot upload dataset. "
            "Set this environment variable to enable Braintrust dataset uploads."
        )
        raise SystemExit(1)

    store = ContentStore(base_dir=base_dir)
    dataset = braintrust.init_dataset(project="astral-index", name=dataset_name)
    total_items = 0
    row_summaries: list[dict[str, Any]] = []

    for week_start, week_end in weeks:
        items = store.list_items(since=week_start, before=week_end)
        if not items:
            continue

        cat_counts: Counter[str] = Counter()
        for item in items:
            for cat in item.categories:
                cat_counts[cat] += 1

        input_data = [item.model_dump(mode="json") for item in items]
        dataset.insert(
            input=input_data,
            metadata={
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "item_count": len(items),
                "categories": dict(cat_counts),
            },
        )
        total_items += len(items)
        row_summaries.append(
            {
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "item_count": len(items),
            }
        )

    if not row_summaries:
        logger.warning("No items found in any week range")
        raise SystemExit(1)

    dataset.flush()

    return {
        "dataset_name": dataset_name,
        "total_items": total_items,
        "rows": len(row_summaries),
        "weeks": row_summaries,
    }


def _date_range(items: list[ContentItem]) -> str:
    """Human-readable date range from a list of items."""
    dates = [
        (item.published_at or item.scraped_at).strftime("%Y-%m-%d") for item in items
    ]
    if not dates:
        return "empty"
    return f"{min(dates)} to {max(dates)}"
