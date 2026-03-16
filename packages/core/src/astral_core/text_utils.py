"""Shared text utilities for title normalization and similarity."""

from __future__ import annotations

import re
import unicodedata

# Matches non-journalism content (games, puzzles, quizzes) that shouldn't
# appear in a news digest, even if the classifier assigned a space category.
NON_JOURNALISM_RE = re.compile(
    r"\bword search\b|\bpuzzle\b|\bquiz\b|\bcrossword\b"
    r"|\bbest (?:ai |video ?)?games\b|\btop \d+ games\b"
    # Buying guides and product roundups
    r"|\bbest .{0,30} to buy\b|\bbuying guide\b|\bproduct review\b"
    r"|\btelescope.{0,20}(?:guide|review|buy|deal|price)\b"
    # Gaming content
    r"|\bgaming .{0,20}review\b|\bplaystation\b|\bxbox\b|\bnintendo\b"
    # Horoscopes/astrology (common "space" misclassification)
    r"|\bhoroscope\b|\bastrology\b|\bzodiac\b",
    re.IGNORECASE,
)

# Stopwords too common in space news titles to be discriminative
_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "in",
        "to",
        "for",
        "and",
        "on",
        "is",
        "at",
        "by",
        "from",
        "with",
        "as",
        "its",
        "it",
    }
)


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


def _token_jaccard(a: str, b: str) -> float:
    """Jaccard similarity on content-word tokens (stopwords removed)."""
    tokens_a = {w for w in normalize_title(a).split() if w not in _STOP}
    tokens_b = {w for w in normalize_title(b).split() if w not in _STOP}
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def title_similarity(a: str, b: str) -> float:
    """Combined Levenshtein + token Jaccard similarity.

    Returns Levenshtein similarity if >= 0.7 (clear near-duplicate).
    Otherwise, checks token Jaccard for same-event detection: titles about
    the same event often share key nouns (mission names, numbers, proper nouns)
    but differ in phrasing, so Levenshtein alone misses them. A Jaccard >= 0.5
    indicates significant content-word overlap — enough to flag as related.
    """
    na, nb = normalize_title(a), normalize_title(b)
    lev = levenshtein_ratio(na, nb)
    if lev >= 0.7:
        return lev
    jac = _token_jaccard(a, b)
    if jac >= 0.5:
        return max(lev, jac)
    return lev
