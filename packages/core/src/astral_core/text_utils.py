"""Shared text utilities for title normalization and similarity."""

from __future__ import annotations

import re
import unicodedata


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation and extra whitespace for comparison."""
    text = unicodedata.normalize("NFKD", title).lower()
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split())


def levenshtein_ratio(a: str, b: str) -> float:
    """Levenshtein similarity ratio: 1.0 = identical, 0.0 = different."""
    if a == b:
        return 1.0
    len_a, len_b = len(a), len(b)
    if not len_a or not len_b:
        return 0.0

    # Standard DP matrix — fine for title-length strings
    prev = list(range(len_b + 1))
    for i in range(1, len_a + 1):
        curr = [i] + [0] * len_b
        for j in range(1, len_b + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr

    max_len = max(len_a, len_b)
    return 1.0 - prev[len_b] / max_len


def title_similarity(a: str, b: str) -> float:
    """Levenshtein similarity between two titles after normalization."""
    return levenshtein_ratio(normalize_title(a), normalize_title(b))
