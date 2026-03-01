"""Enhanced deduplication: URL normalization, content hash, and title similarity."""

from __future__ import annotations

import re
import unicodedata

from astral_core import ContentItem, normalize_url, url_hash


def normalized_id(url: str) -> str:
    """Hash a URL after stripping tracking params, for dedup comparisons."""
    return url_hash(normalize_url(url))


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation and extra whitespace for comparison."""
    text = unicodedata.normalize("NFKD", title).lower()
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split())


def _levenshtein_ratio(a: str, b: str) -> float:
    """Levenshtein distance as a 0–1 ratio (0 = identical, 1 = completely different)."""
    if a == b:
        return 0.0
    len_a, len_b = len(a), len(b)
    if not len_a or not len_b:
        return 1.0

    # Standard DP matrix — fine for title-length strings
    prev = list(range(len_b + 1))
    for i in range(1, len_a + 1):
        curr = [i] + [0] * len_b
        for j in range(1, len_b + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr

    max_len = max(len_a, len_b)
    return prev[len_b] / max_len


def is_duplicate(
    candidate: ContentItem,
    existing: list[ContentItem],
    *,
    title_threshold: float = 0.2,
) -> bool:
    """Three-level duplicate check.

    1. Normalized URL hash match (tracking-param-insensitive)
    2. Content hash match (same body text)
    3. Title similarity (Levenshtein ratio < threshold)
    """
    candidate_norm_id = normalized_id(candidate.source_url)
    candidate_title = _normalize_title(candidate.title)

    for item in existing:
        # Level 1: URL normalization
        if normalized_id(item.source_url) == candidate_norm_id:
            return True

        # Level 2: Content hash
        if (
            candidate.content_hash
            and item.content_hash
            and candidate.content_hash == item.content_hash
        ):
            return True

        # Level 3: Title distance
        item_title = _normalize_title(item.title)
        if _levenshtein_ratio(candidate_title, item_title) < title_threshold:
            return True

    return False
