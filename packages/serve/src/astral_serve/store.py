"""Filesystem storage for newsletter publishing state.

Layout: {base_dir}/newsletters/{YYYY-MM-DD}/meta.json + draft.md
"""

from __future__ import annotations

from pathlib import Path

from .models import PublishRecord


class NewsletterStore:
    """JSON file storage for newsletter publish records."""

    def __init__(self, base_dir: str | Path = "data") -> None:
        self.base_dir = Path(base_dir) / "newsletters"

    def _issue_dir(self, issue_date_str: str) -> Path:
        return self.base_dir / issue_date_str

    def save(self, record: PublishRecord, markdown: str | None = None) -> Path:
        dir_ = self._issue_dir(str(record.issue_date))
        dir_.mkdir(parents=True, exist_ok=True)

        meta_path = dir_ / "meta.json"
        meta_path.write_text(record.model_dump_json(indent=2))

        if markdown is not None:
            (dir_ / "draft.md").write_text(markdown)

        return meta_path

    def load(self, issue_date_str: str) -> PublishRecord | None:
        meta_path = self._issue_dir(issue_date_str) / "meta.json"
        if not meta_path.exists():
            return None
        return PublishRecord.model_validate_json(meta_path.read_text())

    def list_issues(self) -> list[PublishRecord]:
        if not self.base_dir.exists():
            return []

        records: list[PublishRecord] = []
        for dir_ in sorted(self.base_dir.iterdir()):
            if not dir_.is_dir():
                continue
            meta_path = dir_ / "meta.json"
            if meta_path.exists():
                records.append(PublishRecord.model_validate_json(meta_path.read_text()))
        return records
