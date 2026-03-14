"""Enhanced deduplication: URL normalization, content hash, and title similarity."""

from __future__ import annotations

from astral_core import ContentItem, normalize_url, url_hash
from astral_core.text_utils import levenshtein_ratio, normalize_title


def normalized_id(url: str) -> str:
    """Hash a URL after stripping tracking params, for dedup comparisons."""
    return url_hash(normalize_url(url))


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
    candidate_title = normalize_title(candidate.title)

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

        # Level 3: Title similarity (high similarity = duplicate)
        item_title = normalize_title(item.title)
        if levenshtein_ratio(candidate_title, item_title) > (1.0 - title_threshold):
            return True

    return False
