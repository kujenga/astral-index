"""Tests for the Orbital Index reference fetcher and cache."""

from __future__ import annotations

import json
from datetime import date

import pytest

from astral_eval.oi_reference import (
    _parse_archive_html,
    build_oi_index,
    fetch_oi_issue,
    find_oi_issues_for_window,
    get_oi_reference,
)


class TestParseArchiveHtml:
    """Test HTML parsing of the OI archive listing page."""

    def test_extracts_issues_from_typical_html(self):
        html = """
        <html><body>
        <a href="/archive/2025-01-07-Issue-350-foobar/">Issue 350</a>
        <a href="/archive/2024-12-17-Issue-349-stuff/">Issue 349</a>
        <a href="/archive/2024-11-05-Issue-344-blah/">Issue 344</a>
        </body></html>
        """
        entries = _parse_archive_html(html)
        assert len(entries) == 3
        assert entries[0]["date"] == "2024-11-05"
        assert entries[0]["issue_number"] == 344
        assert entries[2]["date"] == "2025-01-07"
        assert entries[2]["issue_number"] == 350

    def test_deduplicates_urls(self):
        html = """
        <a href="/archive/2025-01-07-Issue-350-foobar/">Issue 350</a>
        <a href="/archive/2025-01-07-Issue-350-foobar/">Issue 350 again</a>
        """
        entries = _parse_archive_html(html)
        assert len(entries) == 1

    def test_handles_absolute_urls(self):
        html = """
        <a href="https://orbitalindex.com/archive/2025-01-07-Issue-350-x/">350</a>
        """
        entries = _parse_archive_html(html)
        assert len(entries) == 1
        assert entries[0]["url"].startswith("https://orbitalindex.com")

    def test_returns_empty_for_no_matches(self):
        html = "<html><body><p>No links here</p></body></html>"
        entries = _parse_archive_html(html)
        assert entries == []

    def test_handles_missing_issue_number(self):
        html = '<a href="/archive/2025-01-07-Some-Post/">Post</a>'
        entries = _parse_archive_html(html)
        assert len(entries) == 1
        assert entries[0]["issue_number"] is None


class TestFindOiIssuesForWindow:
    """Test date window filtering."""

    @pytest.fixture
    def sample_index(self) -> list[dict]:
        return [
            {"date": "2025-09-09", "issue_number": 335, "url": "https://oi/335"},
            {"date": "2025-09-16", "issue_number": 336, "url": "https://oi/336"},
            {"date": "2025-11-11", "issue_number": 344, "url": "https://oi/344"},
            {"date": "2025-11-18", "issue_number": 345, "url": "https://oi/345"},
            {"date": "2025-12-15", "issue_number": 348, "url": "https://oi/348"},
        ]

    def test_finds_issues_within_window(self, sample_index):
        # Window: Sep 8-22 should match issues on Sep 9 and Sep 16
        matches = find_oi_issues_for_window(
            date(2025, 9, 8), date(2025, 9, 22), sample_index
        )
        assert len(matches) == 2
        assert matches[0]["issue_number"] == 335
        assert matches[1]["issue_number"] == 336

    def test_fuzz_extends_window(self, sample_index):
        # Window: Sep 10-15 is narrow, but 3-day fuzz should catch Sep 9 and Sep 16
        matches = find_oi_issues_for_window(
            date(2025, 9, 10), date(2025, 9, 15), sample_index
        )
        assert len(matches) == 2

    def test_no_matches_returns_empty(self, sample_index):
        matches = find_oi_issues_for_window(
            date(2025, 6, 1), date(2025, 6, 14), sample_index
        )
        assert matches == []

    def test_custom_fuzz_days(self, sample_index):
        # Zero fuzz — only exact window match
        matches = find_oi_issues_for_window(
            date(2025, 9, 9), date(2025, 9, 9), sample_index, fuzz_days=0
        )
        assert len(matches) == 1
        assert matches[0]["issue_number"] == 335


class TestBuildOiIndex:
    """Test index building with caching."""

    def test_reads_from_cache(self, tmp_path):
        cache_dir = str(tmp_path)
        index_file = tmp_path / "_index.json"
        cached_data = [
            {"date": "2025-01-07", "issue_number": 350, "url": "https://oi/350"}
        ]
        index_file.write_text(json.dumps(cached_data))

        result = build_oi_index(cache_dir=cache_dir)
        assert result == cached_data


class TestFetchOiIssue:
    """Test issue fetching with caching."""

    def test_reads_from_cache(self, tmp_path):
        cache_dir = str(tmp_path)
        cached_file = tmp_path / "2025-01-07-Issue-350.md"
        cached_file.write_text("# Issue 350\n\nSome content here.")

        result = fetch_oi_issue(
            "https://orbitalindex.com/archive/2025-01-07-Issue-350/",
            cache_dir=cache_dir,
        )
        assert result == "# Issue 350\n\nSome content here."

    def test_returns_none_for_empty_cache(self, tmp_path):
        cache_dir = str(tmp_path)
        cached_file = tmp_path / "2025-01-07-Issue-350.md"
        cached_file.write_text("")

        result = fetch_oi_issue(
            "https://orbitalindex.com/archive/2025-01-07-Issue-350/",
            cache_dir=cache_dir,
        )
        assert result is None


class TestGetOiReference:
    """Test the top-level orchestration function."""

    def test_returns_none_when_no_index(self, tmp_path, monkeypatch):
        """Returns None when the index is empty."""
        cache_dir = str(tmp_path)
        # Write empty index
        (tmp_path / "_index.json").write_text("[]")

        result = get_oi_reference(
            date(2025, 9, 8), date(2025, 9, 22), cache_dir=cache_dir
        )
        assert result is None

    def test_concatenates_multiple_issues(self, tmp_path):
        """Concatenates text from multiple matching issues."""
        cache_dir = str(tmp_path)

        # Set up index
        index = [
            {
                "date": "2025-09-09",
                "issue_number": 335,
                "url": "https://orbitalindex.com/archive/2025-09-09-Issue-335/",
            },
            {
                "date": "2025-09-16",
                "issue_number": 336,
                "url": "https://orbitalindex.com/archive/2025-09-16-Issue-336/",
            },
        ]
        (tmp_path / "_index.json").write_text(json.dumps(index))

        # Cache issue text (filename = last URL path segment + .md)
        (tmp_path / "2025-09-09-Issue-335.md").write_text("Content of issue 335.")
        (tmp_path / "2025-09-16-Issue-336.md").write_text("Content of issue 336.")

        result = get_oi_reference(
            date(2025, 9, 8), date(2025, 9, 22), cache_dir=cache_dir
        )
        assert result is not None
        assert "335" in result
        assert "336" in result
        assert "---" in result  # separator between issues

    def test_returns_none_when_no_matching_issues(self, tmp_path):
        """Returns None when index has issues but none match the window."""
        cache_dir = str(tmp_path)
        index = [
            {
                "date": "2025-01-07",
                "issue_number": 350,
                "url": "https://orbitalindex.com/archive/2025-01-07-Issue-350/",
            },
        ]
        (tmp_path / "_index.json").write_text(json.dumps(index))

        result = get_oi_reference(
            date(2025, 6, 1), date(2025, 6, 14), cache_dir=cache_dir
        )
        assert result is None
