"""Tests for ContentStore, focusing on the before parameter."""

from __future__ import annotations

from datetime import UTC, datetime

from astral_core import ContentItem, ContentStore, ContentType
from astral_core.models import url_hash


def _make_item(source_url: str, scraped_at: datetime) -> ContentItem:
    return ContentItem(
        id=url_hash(source_url),
        source_url=source_url,
        content_type=ContentType.ARTICLE,
        source_name="TestSource",
        title=f"Article {source_url}",
        scraped_at=scraped_at,
        published_at=scraped_at,
        url_hash=url_hash(source_url),
    )


class TestListItemsBefore:
    """Half-open interval: [since, before) on scraped_at."""

    def test_before_excludes_items_at_boundary(self, tmp_path):
        store = ContentStore(base_dir=tmp_path / "data")
        t1 = datetime(2026, 2, 20, tzinfo=UTC)
        t2 = datetime(2026, 2, 25, tzinfo=UTC)
        t3 = datetime(2026, 3, 1, tzinfo=UTC)

        store.save(_make_item("https://example.com/1", t1))
        store.save(_make_item("https://example.com/2", t2))
        store.save(_make_item("https://example.com/3", t3))

        # before=t3 should exclude the item scraped exactly at t3
        items = store.list_items(before=t3)
        urls = {i.source_url for i in items}
        assert "https://example.com/1" in urls
        assert "https://example.com/2" in urls
        assert "https://example.com/3" not in urls

    def test_since_and_before_half_open(self, tmp_path):
        store = ContentStore(base_dir=tmp_path / "data")
        t1 = datetime(2026, 2, 20, tzinfo=UTC)
        t2 = datetime(2026, 2, 25, tzinfo=UTC)
        t3 = datetime(2026, 3, 1, tzinfo=UTC)

        store.save(_make_item("https://example.com/a", t1))
        store.save(_make_item("https://example.com/b", t2))
        store.save(_make_item("https://example.com/c", t3))

        # [t2, t3) should include only the t2 item
        items = store.list_items(since=t2, before=t3)
        assert len(items) == 1
        assert items[0].source_url == "https://example.com/b"

    def test_before_none_returns_all(self, tmp_path):
        store = ContentStore(base_dir=tmp_path / "data")
        t1 = datetime(2026, 2, 20, tzinfo=UTC)
        t2 = datetime(2026, 3, 1, tzinfo=UTC)

        store.save(_make_item("https://example.com/x", t1))
        store.save(_make_item("https://example.com/y", t2))

        items = store.list_items(before=None)
        assert len(items) == 2

    def test_empty_window_returns_nothing(self, tmp_path):
        store = ContentStore(base_dir=tmp_path / "data")
        t = datetime(2026, 2, 25, tzinfo=UTC)
        store.save(_make_item("https://example.com/z", t))

        # Window that excludes everything
        items = store.list_items(
            since=datetime(2026, 3, 1, tzinfo=UTC),
            before=datetime(2026, 3, 2, tzinfo=UTC),
        )
        assert items == []
