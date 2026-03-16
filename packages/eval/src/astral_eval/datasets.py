"""Golden dataset management for reproducible experiments.

Upload frozen sets of ContentItems to the active observability backend
as named datasets, enabling consistent regression testing across pipeline
changes.

Standard dataset tiers:
  - golden-smoke    (1 row)  — fast sanity check (~5s)
  - golden-standard (4 rows) — default for /iterate and /autoiterate
  - golden-full     (8 rows) — comprehensive regression testing, CI
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from astral_core import ContentItem, ContentStore
from astral_core.observability import get_backend_name, get_datasets

logger = logging.getLogger(__name__)

# Curated date windows for standard datasets.
# 2025 data is sparse (~5 items/date) → 14-day windows.
# 2026 data is dense (~50 items/day) → 7-day windows.
_WINDOWS: dict[str, tuple[str, str]] = {
    "2025-Q1": ("2025-02-03", "2025-02-17"),
    "2025-Q2": ("2025-05-05", "2025-05-19"),
    "2025-Q3": ("2025-09-08", "2025-09-22"),
    "2025-Q4": ("2025-11-10", "2025-11-24"),
    "2026-Jan": ("2026-01-19", "2026-01-26"),
    "2026-Feb-early": ("2026-02-09", "2026-02-16"),
    "2026-Feb-late": ("2026-02-23", "2026-03-02"),
    "2026-Mar": ("2026-03-02", "2026-03-09"),
}

# Windows with matching OI issues (OI ended Jan 7, 2026)
_OI_WINDOWS = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]

STANDARD_DATASETS: dict[str, list[str]] = {
    "golden-smoke": ["2025-Q4"],
    "golden-standard": ["2025-Q3", "2025-Q4", "2026-Feb-early", "2026-Feb-late"],
    "golden-full": list(_WINDOWS.keys()),
    "golden-oi": _OI_WINDOWS,
}


def _window_to_datetimes(key: str) -> tuple[datetime, datetime]:
    """Convert a window key to (since, until) UTC datetimes."""
    start_str, end_str = _WINDOWS[key]
    since = datetime.fromisoformat(start_str).replace(tzinfo=UTC)
    until = datetime.fromisoformat(end_str).replace(tzinfo=UTC)
    return since, until


def _list_items_by_date_dir(
    base_dir: str, since: datetime, until: datetime
) -> list[ContentItem]:
    """Load items whose directory date falls within [since, until).

    Unlike ``ContentStore.list_items`` (which filters on ``scraped_at``),
    this filters on the directory name — matching ``published_at`` — so it
    works for historical data scraped after the fact.
    """
    import json
    from pathlib import Path

    items_dir = Path(base_dir) / "items"
    if not items_dir.exists():
        return []

    since_str = since.strftime("%Y-%m-%d")
    until_str = until.strftime("%Y-%m-%d")
    results: list[ContentItem] = []

    for date_dir in sorted(items_dir.iterdir()):
        if not date_dir.is_dir():
            continue
        dir_date = date_dir.name
        if dir_date < since_str or dir_date >= until_str:
            continue
        for path in date_dir.glob("*.json"):
            item = ContentItem.model_validate(json.loads(path.read_text()))
            results.append(item)

    return results


def _check_backend() -> None:
    """Raise SystemExit if no observability backend is configured."""
    if get_backend_name() == "noop":
        logger.warning(
            "No observability backend configured — cannot upload datasets. "
            "Set BRAINTRUST_API_KEY or PHOENIX_COLLECTOR_ENDPOINT to enable."
        )
        raise SystemExit(1)


def setup_standard_datasets(
    *, dry_run: bool = False, base_dir: str = "data"
) -> list[str]:
    """Create all standard dataset tiers in the active backend.

    Uses directory-date filtering (published_at) rather than scraped_at,
    so historical data scraped retroactively is included correctly.

    Returns the list of dataset names that were uploaded.
    """
    if not dry_run:
        _check_backend()

    datasets = get_datasets()
    uploaded: list[str] = []
    for name, window_keys in STANDARD_DATASETS.items():
        weeks = [_window_to_datetimes(k) for k in window_keys]
        if dry_run:
            logger.info(
                "Would upload %s: %d rows from windows %s",
                name,
                len(weeks),
                ", ".join(window_keys),
            )
            uploaded.append(name)
            continue

        dataset = datasets.init_dataset(project="astral-index", name=name)
        total_items = 0
        rows = 0

        # Resolve OI references for windows in this dataset
        oi_cache_dir = str(Path(base_dir) / "oi_reference")
        populate_oi = any(wk in _OI_WINDOWS for wk in window_keys)
        if populate_oi:
            from .oi_reference import get_oi_reference

        for window_key, (week_start, week_end) in zip(window_keys, weeks, strict=True):
            items = _list_items_by_date_dir(base_dir, week_start, week_end)
            if not items:
                logger.warning(
                    "No items for window %s → %s, skipping",
                    week_start.strftime("%Y-%m-%d"),
                    week_end.strftime("%Y-%m-%d"),
                )
                continue

            cat_counts: Counter[str] = Counter()
            for item in items:
                for cat in item.categories:
                    cat_counts[cat] += 1

            # Fetch OI reference text for 2025 windows
            oi_text: str | None = None
            oi_issues: list[str] = []
            if populate_oi and window_key in _OI_WINDOWS:
                oi_text = get_oi_reference(
                    week_start.date(), week_end.date(), cache_dir=oi_cache_dir
                )
                if oi_text:
                    from .oi_reference import build_oi_index, find_oi_issues_for_window

                    idx = build_oi_index(cache_dir=oi_cache_dir)
                    matching = find_oi_issues_for_window(
                        week_start.date(), week_end.date(), idx
                    )
                    oi_issues = [e["url"] for e in matching]

            input_data = [item.model_dump(mode="json") for item in items]
            metadata = {
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "item_count": len(items),
                "categories": dict(cat_counts),
                "has_oi_reference": oi_text is not None,
                "oi_issues": oi_issues,
            }
            if oi_text is not None:
                metadata["expected"] = oi_text

            datasets.insert_row(dataset, input=input_data, metadata=metadata)
            total_items += len(items)
            rows += 1

        if rows == 0:
            logger.warning("No items found for dataset %s — skipping", name)
            continue

        datasets.flush_dataset(dataset)
        logger.info("Uploaded %s: %d rows, %d total items", name, rows, total_items)
        uploaded.append(name)

    return uploaded


def upload_golden_week(
    *,
    since: datetime,
    until: datetime | None = None,
    dataset_name: str,
    base_dir: str = "data",
) -> dict[str, Any]:
    """Read items from ContentStore and upload to the active backend as a dataset.

    Each row is one week's worth of items (input = full item list). This
    matches the 1-row-per-eval design in the experiment runner.

    Returns metadata about the uploaded dataset.
    """
    _check_backend()

    store = ContentStore(base_dir=base_dir)
    items = store.list_items(since=since, before=until)

    if not items:
        logger.warning("No items found in date range")
        raise SystemExit(1)

    cat_counts: Counter[str] = Counter()
    for item in items:
        for cat in item.categories:
            cat_counts[cat] += 1

    date_range = _date_range(items)
    input_data = [item.model_dump(mode="json") for item in items]

    datasets = get_datasets()
    dataset = datasets.init_dataset(project="astral-index", name=dataset_name)
    datasets.insert_row(
        dataset,
        input=input_data,
        metadata={
            "item_count": len(items),
            "date_range": date_range,
            "categories": dict(cat_counts),
        },
    )
    datasets.flush_dataset(dataset)

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
    """Upload multiple week-windows as separate rows in one dataset.

    Each (since, until) pair becomes one dataset row whose ``input`` is
    the list of ContentItem dicts for that window.
    """
    _check_backend()

    store = ContentStore(base_dir=base_dir)
    datasets = get_datasets()
    dataset = datasets.init_dataset(project="astral-index", name=dataset_name)
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
        datasets.insert_row(
            dataset,
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

    datasets.flush_dataset(dataset)

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
