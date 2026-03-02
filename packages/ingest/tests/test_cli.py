"""CLI integration tests using Click's CliRunner.

All tests monkeypatch scraper fetch methods and use chdir(tmp_path)
so ContentStore() uses a temp "data/" directory.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from click.testing import CliRunner

from astral_core import ContentStore
from astral_ingest.cli import cli

from .conftest import _make_item

runner = CliRunner()


def _seed_store(tmp_path, items):
    """Save items into a ContentStore at tmp_path/data."""
    store = ContentStore(base_dir=tmp_path / "data")
    for item in items:
        store.save(item)
    return store


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------


class TestSourcesCommand:
    def test_lists_known_sources(self):
        result = runner.invoke(cli, ["sources"])
        assert result.exit_code == 0
        assert "RSS Sources:" in result.output


# ---------------------------------------------------------------------------
# scrape
# ---------------------------------------------------------------------------


class TestScrapeCommand:
    def test_dry_run_prints_items(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        items = [
            _make_item(
                title="Test Scrape Item",
                source_url="https://example.com/scrape-1",
                source_name="TestSource",
            ),
        ]

        async def _mock_fetch(self):
            return items

        monkeypatch.setattr(
            "astral_ingest.scrapers.rss.RSSFeedScraper.fetch",
            _mock_fetch,
        )

        result = runner.invoke(
            cli,
            ["scrape", "--source", "SpaceNews", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "Test Scrape Item" in result.output

    def test_source_filter(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        calls: list[str] = []

        async def _mock_fetch(self):
            calls.append(self.name)
            return []

        monkeypatch.setattr(
            "astral_ingest.scrapers.rss.RSSFeedScraper.fetch",
            _mock_fetch,
        )

        result = runner.invoke(cli, ["scrape", "--source", "SpaceNews"])
        assert result.exit_code == 0
        assert all("SpaceNews" in c for c in calls)

    def test_scraper_error_does_not_crash(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        async def _mock_fetch(self):
            raise RuntimeError("Network error")

        monkeypatch.setattr(
            "astral_ingest.scrapers.rss.RSSFeedScraper.fetch",
            _mock_fetch,
        )

        result = runner.invoke(cli, ["scrape", "--source", "SpaceNews"])
        assert result.exit_code == 0
        assert "ERROR" in result.output


# ---------------------------------------------------------------------------
# expand
# ---------------------------------------------------------------------------


class TestExpandCommand:
    def test_empty_store_message(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["expand", "--since", "7"])
        assert result.exit_code == 0
        assert "No items need expansion" in result.output

    def test_dry_run_lists_candidates(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        item = _make_item(
            title="Needs Expansion",
            source_url="https://example.com/expand-1",
            body_text=None,
            excerpt="Just an excerpt",
            published_at=datetime.now(UTC) - timedelta(hours=1),
        )
        _seed_store(tmp_path, [item])

        result = runner.invoke(cli, ["expand", "--since", "7", "--dry-run"])
        assert result.exit_code == 0
        assert "Needs Expansion" in result.output
        assert "would be expanded" in result.output


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


class TestClassifyCommand:
    def test_empty_store_message(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["classify", "--since", "7"])
        assert result.exit_code == 0
        assert "No uncategorized items found" in result.output

    def test_keyword_pass_classifies(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        item = _make_item(
            title="SpaceX Falcon 9 rocket launch today",
            source_url="https://example.com/classify-1",
            categories=[],
            published_at=datetime.now(UTC) - timedelta(hours=1),
        )
        _seed_store(tmp_path, [item])

        result = runner.invoke(
            cli,
            ["classify", "--since", "7", "--no-llm", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "keywords" in result.output
        assert "launch_vehicles" in result.output

    def test_dry_run_does_not_save(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        item = _make_item(
            title="SpaceX Falcon 9 rocket launch",
            source_url="https://example.com/classify-2",
            categories=[],
            published_at=datetime.now(UTC) - timedelta(hours=1),
        )
        _seed_store(tmp_path, [item])

        runner.invoke(
            cli,
            ["classify", "--since", "7", "--no-llm", "--dry-run"],
        )

        # Reload from store — categories should still be empty
        store = ContentStore(base_dir=tmp_path / "data")
        reloaded = store.list_items()
        assert reloaded[0].categories == []


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


class TestExportCommand:
    def test_markdown_output(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        item = _make_item(
            title="Export Test Article",
            source_url="https://example.com/export-1",
            published_at=datetime.now(UTC) - timedelta(hours=1),
        )
        _seed_store(tmp_path, [item])

        result = runner.invoke(
            cli,
            ["export", "--since", "7", "--format", "markdown"],
        )
        assert result.exit_code == 0
        assert "# Space News Digest" in result.output
        assert "Export Test Article" in result.output

    def test_json_output_is_valid(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        item = _make_item(
            title="JSON Export Item",
            source_url="https://example.com/export-2",
            published_at=datetime.now(UTC) - timedelta(hours=1),
        )
        _seed_store(tmp_path, [item])

        result = runner.invoke(
            cli,
            ["export", "--since", "7", "--format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "JSON Export Item"

    def test_empty_store_message(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["export", "--since", "7"])
        assert result.exit_code == 0
        assert "No items found" in result.output
