from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import ContentItem


class ContentStore:
    """JSON file storage for ContentItem objects.

    Layout: {base_dir}/items/{YYYY-MM-DD}/{id}.json
    """

    def __init__(self, base_dir: str | Path = "data") -> None:
        self.base_dir = Path(base_dir)

    def _item_dir(self, date: datetime) -> Path:
        return self.base_dir / "items" / date.strftime("%Y-%m-%d")

    def _item_path(self, item: ContentItem) -> Path:
        date = item.published_at or item.scraped_at
        return self._item_dir(date) / f"{item.id}.json"

    def save(self, item: ContentItem) -> Path:
        path = self._item_path(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.model_dump_json(indent=2))
        return path

    def load(self, id: str, date: datetime) -> ContentItem:
        dir_ = self._item_dir(date)
        path = dir_ / f"{id}.json"
        return ContentItem.model_validate_json(path.read_text())

    def exists(self, id: str) -> bool:
        """Check if an item with this ID exists in any date directory."""
        items_dir = self.base_dir / "items"
        if not items_dir.exists():
            return False
        for date_dir in items_dir.iterdir():
            if date_dir.is_dir() and (date_dir / f"{id}.json").exists():
                return True
        return False

    @staticmethod
    def _item_date(item: ContentItem) -> datetime:
        """Editorial date: published_at if available, else scraped_at."""
        return item.published_at or item.scraped_at

    def list_items(
        self,
        *,
        since: datetime | None = None,
        before: datetime | None = None,
        source_name: str | None = None,
    ) -> list[ContentItem]:
        items_dir = self.base_dir / "items"
        if not items_dir.exists():
            return []

        # Use directory names (YYYY-MM-DD) to skip irrelevant date dirs early.
        # Items are filed by published_at, so this is a safe pre-filter.
        since_str = since.strftime("%Y-%m-%d") if since else None
        before_str = before.strftime("%Y-%m-%d") if before else None

        results: list[ContentItem] = []
        for date_dir in sorted(items_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            dir_name = date_dir.name
            # Skip directories clearly outside the date window
            if since_str and dir_name < since_str:
                continue
            if before_str and dir_name >= before_str:
                continue
            for path in date_dir.glob("*.json"):
                item = ContentItem.model_validate(json.loads(path.read_text()))
                item_dt = self._item_date(item)
                if since and item_dt < since:
                    continue
                if before and item_dt >= before:
                    continue
                if source_name and item.source_name != source_name:
                    continue
                results.append(item)

        return sorted(results, key=lambda i: self._item_date(i), reverse=True)
