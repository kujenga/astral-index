"""Paywall heuristic: flag articles with suspiciously short extracted text."""

from __future__ import annotations

# Articles behind a paywall typically yield only a brief teaser
_MIN_WORDS = 150


def is_paywalled(text: str) -> bool:
    """Return True if extracted text looks like a paywall teaser (<150 words)."""
    return len(text.split()) < _MIN_WORDS
