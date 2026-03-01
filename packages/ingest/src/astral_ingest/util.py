"""Shared utilities for astral-ingest."""

from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Strip HTML tags and unescape entities."""
    return html.unescape(_TAG_RE.sub("", text)).strip()


def extract_links(html_content: str) -> list[str]:
    """Pull href values out of HTML content."""
    return re.findall(r'href=["\']([^"\']+)["\']', html_content)
