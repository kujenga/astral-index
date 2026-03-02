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

        results: list[ContentItem] = []
        for date_dir in sorted(items_dir.iterdir()):
            if not date_dir.is_dir():
                continue
            for path in date_dir.glob("*.json"):
                item = ContentItem.model_validate(json.loads(path.read_text()))
                if since and item.scraped_at < since:
                    continue
                if before and item.scraped_at >= before:
                    continue
                if source_name and item.source_name != source_name:
                    continue
                results.append(item)

        return sorted(results, key=lambda i: i.scraped_at, reverse=True)
