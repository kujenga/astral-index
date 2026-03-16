"""Fetch and cache Orbital Index newsletter issues for reference-based evaluation.

The Orbital Index published ~350 weekly issues from 2019 to Jan 7, 2026.
This module scrapes the archive listing, builds a date→URL index, and
fetches/caches individual issue text for use as `expected` in reference judges.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

import httpx
import trafilatura

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = "data/oi_reference"
_ARCHIVE_URL = "https://orbitalindex.com/archive/"


def build_oi_index(*, cache_dir: str = _DEFAULT_CACHE_DIR) -> list[dict]:
    """Scrape the OI archive listing page to build a date→issue-URL index.

    Each entry: ``{"date": "YYYY-MM-DD", "issue_number": N, "url": "..."}``.
    Caches the index to ``{cache_dir}/_index.json`` so subsequent calls skip
    the network.
    """
    cache_path = Path(cache_dir) / "_index.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    logger.info("Fetching OI archive listing from %s", _ARCHIVE_URL)
    resp = httpx.get(_ARCHIVE_URL, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    index = _parse_archive_html(resp.text)
    if not index:
        logger.warning("No issues found in OI archive page")
        return []

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(index, indent=2))
    logger.info("Cached OI index with %d issues", len(index))
    return index


def _parse_archive_html(html: str) -> list[dict]:
    """Extract issue entries from the OI archive HTML.

    The archive page lists issues as links. We look for patterns like:
    - URL path: /archive/YYYY-MM-DD-Issue-NNN/ or similar
    - Link text containing issue numbers and dates
    """
    entries: list[dict] = []
    seen_urls: set[str] = set()

    # Match href patterns for OI issue pages
    # Pattern: /archive/YYYY-MM-DD-... or full URLs to orbitalindex.com
    href_pattern = re.compile(
        r'href="((?:https?://orbitalindex\.com)?/archive/'
        r'(\d{4}-\d{2}-\d{2})-[^"]*)"'
    )

    for match in href_pattern.finditer(html):
        url = match.group(1)
        date_str = match.group(2)

        # Normalize to absolute URL
        if url.startswith("/"):
            url = f"https://orbitalindex.com{url}"

        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Extract issue number from URL if present
        issue_match = re.search(r"Issue-(\d+)", url, re.IGNORECASE)
        issue_number = int(issue_match.group(1)) if issue_match else None

        entries.append(
            {
                "date": date_str,
                "issue_number": issue_number,
                "url": url,
            }
        )

    # Sort by date
    entries.sort(key=lambda e: e["date"])
    return entries


def find_oi_issues_for_window(
    start: date,
    end: date,
    index: list[dict],
    *,
    fuzz_days: int = 3,
) -> list[dict]:
    """Filter the index for issues whose date falls within [start - fuzz, end + fuzz].

    The fuzz accounts for weekly alignment mismatches between our date
    windows and OI's publication schedule.
    """
    fuzz = timedelta(days=fuzz_days)
    window_start = (start - fuzz).isoformat()
    window_end = (end + fuzz).isoformat()

    return [entry for entry in index if window_start <= entry["date"] <= window_end]


def fetch_oi_issue(url: str, *, cache_dir: str = _DEFAULT_CACHE_DIR) -> str | None:
    """HTTP GET an OI issue page and extract body text via trafilatura.

    Caches to ``{cache_dir}/{YYYY-MM-DD}-Issue-{NNN}.md``. Returns cached
    content on subsequent calls.
    """
    # Derive cache filename from URL
    path_part = url.rstrip("/").split("/")[-1]
    cache_path = Path(cache_dir) / f"{path_part}.md"

    if cache_path.exists():
        text = cache_path.read_text()
        return text if text.strip() else None

    logger.info("Fetching OI issue: %s", url)
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Failed to fetch OI issue: %s", url, exc_info=True)
        return None

    text = trafilatura.extract(resp.text, include_links=True, include_formatting=True)
    if not text:
        logger.warning("trafilatura extracted no text from %s", url)
        return None

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text)
    logger.info("Cached OI issue text (%d chars): %s", len(text), cache_path.name)
    return text


def get_oi_reference(
    start: date,
    end: date,
    *,
    cache_dir: str = _DEFAULT_CACHE_DIR,
) -> str | None:
    """Top-level: build/load index, find matching issues, fetch, concatenate.

    Returns the concatenated text of all OI issues that fall within the
    given date window, or None if no matching issues are found.
    """
    index = build_oi_index(cache_dir=cache_dir)
    if not index:
        return None

    matching = find_oi_issues_for_window(start, end, index)
    if not matching:
        logger.info(
            "No OI issues found for window %s to %s",
            start.isoformat(),
            end.isoformat(),
        )
        return None

    texts: list[str] = []
    for entry in matching:
        text = fetch_oi_issue(entry["url"], cache_dir=cache_dir)
        if text:
            issue_num = entry.get("issue_number", "?")
            header = f"# Orbital Index Issue #{issue_num} ({entry['date']})"
            texts.append(f"{header}\n\n{text}")

    return "\n\n---\n\n".join(texts) if texts else None
