"""Heuristic newsletter quality scorers — pure computation, no external deps.

These scorers are used both in the eval pipeline (via astral-eval) and for
online production monitoring (via astral-author pipeline logging). They live
in astral-core to avoid circular dependencies.

Each scorer accepts ``output`` (a serialized NewsletterDraft dict) and an
optional ``input`` (list of serialized ContentItem dicts), returning a Score.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .text_utils import NON_JOURNALISM_RE, title_similarity


@dataclass
class Score:
    """A single evaluation score, decoupled from any eval framework."""

    name: str
    score: float  # 0.0-1.0
    metadata: dict = field(default_factory=dict)


def source_diversity(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score:
    """Shannon entropy -> Effective Number of Sources, scored against a target.

    ENS = e^H where H is Shannon entropy over source_name frequencies.
    Target is min(5, unique input sources) so weeks with fewer sources
    aren't penalized for a ceiling they can't reach.
    Score = min(1.0, ENS / target).
    """
    fixed_target = 5
    # Adapt target to available input diversity
    if input:
        input_sources = {
            item.get("source_name") for item in input if item.get("source_name")
        }
        target = min(fixed_target, len(input_sources))
    else:
        target = fixed_target
    target = max(target, 1)  # avoid division by zero

    sources: list[str] = []
    for section in output.get("sections", []):
        for item in section.get("items", []):
            name = item.get("source_name")
            if name:
                sources.append(name)

    if not sources:
        return Score(
            name="source_diversity", score=0.0, metadata={"ens": 0, "n_sources": 0}
        )

    counts = Counter(sources)
    total = sum(counts.values())
    # Shannon entropy
    h = -sum((c / total) * math.log(c / total) for c in counts.values())
    ens = math.exp(h)
    score = min(1.0, ens / target)

    return Score(
        name="source_diversity",
        score=round(score, 3),
        metadata={"ens": round(ens, 2), "n_sources": len(counts)},
    )


def category_coverage(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score:
    """Fraction of input categories represented in the output.

    Checks both section-level categories and item-level categories (by matching
    item_id from output sections against input items' categories). This ensures
    items in "In Brief" sections (which have category=None) still count as
    covered.
    """
    input_cats: set[str] = set()
    if input:
        for item in input:
            for cat in item.get("categories", []):
                if cat and cat != "off_topic":
                    input_cats.add(cat)

    if not input_cats:
        return Score(
            name="category_coverage",
            score=1.0,
            metadata={"input_cats": 0, "output_cats": 0},
        )

    # Build a map of item_id -> categories from input for item-level matching
    input_item_cats: dict[str, list[str]] = {}
    if input:
        for item in input:
            item_id = item.get("id")
            if item_id:
                input_item_cats[item_id] = [
                    c for c in item.get("categories", []) if c and c != "off_topic"
                ]

    output_cats: set[str] = set()

    for section in output.get("sections", []):
        # Section-level category
        cat = section.get("category")
        if cat:
            output_cats.add(cat)

        # Item-level: look up each output item's categories from the input
        for item in section.get("items", []):
            item_id = item.get("item_id")
            if item_id and item_id in input_item_cats:
                for c in input_item_cats[item_id]:
                    output_cats.add(c)

    coverage = len(output_cats & input_cats) / len(input_cats)

    return Score(
        name="category_coverage",
        score=round(coverage, 3),
        metadata={
            "input_cats": len(input_cats),
            "output_cats": len(output_cats),
            "covered": sorted(output_cats & input_cats),
            "missing": sorted(input_cats - output_cats),
        },
    )


def link_count(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score:
    """Counts markdown links in the rendered output, scored per output item.

    Score = min(1.0, link_count / total_output_items).
    """
    markdown = output.get("markdown", "")
    links = re.findall(r"\[.*?\]\(https?://.*?\)", markdown)
    count = len(links)

    total_items = output.get("total_output_items", 0)
    score = 1.0 if total_items == 0 else min(1.0, count / total_items)

    return Score(
        name="link_count",
        score=round(score, 3),
        metadata={
            "links": count,
            "total_items": total_items,
            "ratio": round(count / max(total_items, 1), 2),
        },
    )


def section_balance(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    max_section_items: int = 12,
    **kwargs: Any,
) -> Score:
    """Shannon entropy over section item counts, penalizing oversized sections.

    Combines two signals:
    1. Entropy score: normalized Shannon entropy (0 = all items in one section,
       1 = perfectly uniform distribution).
    2. Cap penalty: 0.2 deduction per section exceeding max_section_items.

    Final score = max(0, entropy_score - cap_penalty).
    """
    sections = output.get("sections", [])
    counts = [len(s.get("items", [])) for s in sections]
    counts = [c for c in counts if c > 0]

    if len(counts) <= 1:
        # 0 or 1 section — can't measure balance
        entropy_score = 1.0 if len(counts) == 0 else 0.5
        return Score(
            name="section_balance",
            score=entropy_score,
            metadata={"section_counts": counts, "entropy": 0.0, "oversized": []},
        )

    total = sum(counts)
    h = -sum((c / total) * math.log(c / total) for c in counts)
    max_h = math.log(len(counts))
    entropy_score = h / max_h if max_h > 0 else 1.0

    oversized = [c for c in counts if c > max_section_items]
    cap_penalty = 0.2 * len(oversized)

    final = max(0.0, entropy_score - cap_penalty)

    return Score(
        name="section_balance",
        score=round(final, 3),
        metadata={
            "section_counts": counts,
            "entropy": round(h, 3),
            "max_entropy": round(max_h, 3),
            "oversized": oversized,
        },
    )


def semantic_dedup(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    similarity_threshold: float = 0.5,
    **kwargs: Any,
) -> Score:
    """Pairwise title similarity across output items, penalizing near-duplicates.

    Compares all pairs of output item titles using combined Levenshtein + token
    Jaccard similarity. Threshold is 0.5 to catch both near-identical titles
    (high Levenshtein) and same-event titles with different wording (high Jaccard).
    Each duplicate pair deducts 0.2 from 1.0.
    """
    titles: list[str] = []
    for section in output.get("sections", []):
        for item in section.get("items", []):
            title = item.get("title")
            if title:
                titles.append(title)

    if len(titles) < 2:
        return Score(
            name="semantic_dedup",
            score=1.0,
            metadata={"n_items": len(titles), "duplicate_pairs": []},
        )

    duplicate_pairs: list[tuple[str, str, float]] = []
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            sim = title_similarity(titles[i], titles[j])
            if sim >= similarity_threshold:
                duplicate_pairs.append((titles[i][:60], titles[j][:60], round(sim, 3)))

    penalty = 0.2 * len(duplicate_pairs)
    final = max(0.0, 1.0 - penalty)

    return Score(
        name="semantic_dedup",
        score=round(final, 3),
        metadata={
            "n_items": len(titles),
            "duplicate_pairs": duplicate_pairs,
            "n_duplicates": len(duplicate_pairs),
        },
    )


def off_topic_leakage(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score:
    """Fraction of output items that have a space-related category.

    Matches output item_ids against input items' categories. Items with no
    categories (uncategorized) or with OFF_TOPIC count as off-topic.
    Score = 1.0 - (off_topic_count / total).
    """
    # Build input lookup: item_id -> categories
    input_item_cats: dict[str, list[str]] = {}
    if input:
        for item in input:
            item_id = item.get("id")
            if item_id:
                input_item_cats[item_id] = [c for c in item.get("categories", []) if c]

    total = 0
    off_topic_count = 0
    off_topic_titles: list[str] = []

    for section in output.get("sections", []):
        for item in section.get("items", []):
            total += 1
            item_id = item.get("item_id")
            cats = input_item_cats.get(item_id, []) if item_id else []
            title = item.get("title", "")
            if not cats or "off_topic" in cats or NON_JOURNALISM_RE.search(title):
                off_topic_count += 1
                off_topic_titles.append(item.get("title", "?")[:60])

    if total == 0:
        return Score(
            name="off_topic_leakage",
            score=1.0,
            metadata={"total": 0, "off_topic": 0},
        )

    final = 1.0 - (off_topic_count / total)

    return Score(
        name="off_topic_leakage",
        score=round(final, 3),
        metadata={
            "total": total,
            "off_topic": off_topic_count,
            "off_topic_titles": off_topic_titles,
        },
    )


def intro_quality(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score:
    """Heuristic intro quality scorer.

    Five weighted sub-scores: presence, template detection, specificity,
    substance, and engagement. Measures structural properties correlating
    with substantive introductions that provide tl;dr value.
    """
    introduction = output.get("introduction", "")
    if not introduction or not introduction.strip():
        return Score(name="intro_quality", score=0.0, metadata={"reason": "missing"})

    words = introduction.split()
    word_count = len(words)

    # --- Sub-scores ---

    # 1. Presence: exists and 30-120 words (targeting substantive intros)
    if 30 <= word_count <= 120:
        presence = 1.0
    elif word_count < 30:
        presence = word_count / 30.0
    else:
        # Over 120 words: gentle penalty
        presence = max(0.5, 1.0 - (word_count - 120) / 200.0)

    # 2. Not a known fallback template
    _TEMPLATES = [
        "here's your roundup",
        "this week in space:",
        "here is your roundup",
        "welcome to this week",
    ]
    intro_lower = introduction.lower()
    not_template = 0.0 if any(t in intro_lower for t in _TEMPLATES) else 1.0

    # 3. Specificity: named entities / content-specific terms appear in intro
    content_words: set[str] = set()
    for section in output.get("sections", []):
        for item in section.get("items", []):
            title = item.get("title", "")
            summary = item.get("summary", "")
            for w in (title + " " + summary).split():
                cleaned = re.sub(r"[^a-zA-Z0-9]", "", w)
                if len(cleaned) > 4:
                    content_words.add(cleaned.lower())

    intro_words_set = {
        re.sub(r"[^a-zA-Z0-9]", "", w).lower() for w in words if len(w) > 4
    }
    overlap_count = len(intro_words_set & content_words)
    specificity = min(1.0, overlap_count / 4.0) if content_words else 0.5

    # 4. Substance: intro references details from summaries NOT in titles
    title_words: set[str] = set()
    summary_words: set[str] = set()
    for section in output.get("sections", []):
        for item in section.get("items", []):
            for w in item.get("title", "").split():
                cleaned = re.sub(r"[^a-zA-Z0-9]", "", w)
                if len(cleaned) > 4:
                    title_words.add(cleaned.lower())
            for w in item.get("summary", "").split():
                cleaned = re.sub(r"[^a-zA-Z0-9]", "", w)
                if len(cleaned) > 4:
                    summary_words.add(cleaned.lower())

    # Words that are in summaries but NOT in titles = "added color"
    summary_only = summary_words - title_words
    summary_only_overlap = len(intro_words_set & summary_only)
    substance = min(1.0, summary_only_overlap / 3.0) if summary_only else 0.5

    # 5. Engagement: questions, numbers/data, contrast/significance words
    signals = 0
    if "?" in introduction:
        signals += 1
    if re.search(r"\d+", introduction):
        signals += 1
    _ENGAGEMENT_WORDS = {
        "first",
        "despite",
        "while",
        "breakthrough",
        "however",
        "unprecedented",
        "critical",
        "significant",
        "milestone",
        "historic",
    }
    if any(w in intro_lower for w in _ENGAGEMENT_WORDS):
        signals += 1
    engagement = min(1.0, signals / 2.0)

    # Weighted combination
    score = (
        0.20 * presence
        + 0.20 * not_template
        + 0.25 * specificity
        + 0.20 * substance
        + 0.15 * engagement
    )

    return Score(
        name="intro_quality",
        score=round(score, 3),
        metadata={
            "word_count": word_count,
            "presence": round(presence, 3),
            "not_template": round(not_template, 3),
            "specificity": round(specificity, 3),
            "substance": round(substance, 3),
            "engagement": round(engagement, 3),
            "specificity_overlap": overlap_count,
            "substance_overlap": summary_only_overlap,
            "engagement_signals": signals,
        },
    )


_REFUSAL_PATTERNS = re.compile(
    r"(?i)("
    r"I cannot provide a summary"
    r"|cannot summarize"
    r"|no body text"
    r"|not provided"
    r"|summary not available"
    r"|unable to summarize"
    r"|I don't have enough"
    r"|no (?:article |source )?(?:text|content) "
    r"(?:was |were )?(?:provided|included|available)"
    r")"
)


def summary_quality(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score:
    """Detect LLM refusals, empty summaries, and headline-only rewrites.

    Checks each output item's summary for:
    - Refusal phrases ("I cannot provide a summary", etc.)
    - Very short summaries (< 20 chars, likely just a title echo)
    - Empty/missing summaries
    Each bad summary deducts 1/total from 1.0.
    """
    total = 0
    bad_count = 0
    bad_items: list[str] = []

    for section in output.get("sections", []):
        for item in section.get("items", []):
            total += 1
            summary = item.get("summary", "")
            title = item.get("title", "")
            # Title-echo is only bad for short titles — a 50-char
            # title used as a summary is acceptable when no body exists
            is_short_echo = summary.strip() == title.strip() and len(summary) < 40
            if (
                not summary
                or len(summary) < 20
                or _REFUSAL_PATTERNS.search(summary)
                or is_short_echo
            ):
                bad_count += 1
                reason = (
                    "empty"
                    if not summary
                    else (
                        "refusal"
                        if _REFUSAL_PATTERNS.search(summary)
                        else "too_short"
                        if len(summary) < 20
                        else "title_echo"
                    )
                )
                bad_items.append(f"{title[:50]}... ({reason})")

    if total == 0:
        return Score(
            name="summary_quality",
            score=1.0,
            metadata={"total": 0, "bad": 0},
        )

    final = 1.0 - (bad_count / total)

    return Score(
        name="summary_quality",
        score=round(final, 3),
        metadata={
            "total": total,
            "bad": bad_count,
            "bad_items": bad_items,
        },
    )


_SOCIAL_SOURCES = re.compile(r"(?i)^(twitter:|bluesky:|reddit:)", flags=0)


def content_originality(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    target_ratio: float = 0.70,
    **kwargs: Any,
) -> Score:
    """Fraction of output items from original reporting vs social posts.

    Items whose source_name starts with "Twitter:", "Bluesky:", or
    "Reddit:" are counted as social. Score = min(1.0, original_ratio /
    target_ratio). A newsletter with 70%+ original content scores 1.0.
    """
    total = 0
    social = 0
    social_items: list[str] = []

    for section in output.get("sections", []):
        for item in section.get("items", []):
            total += 1
            source = item.get("source_name", "")
            if _SOCIAL_SOURCES.match(source):
                social += 1
                social_items.append(f"{item.get('title', '?')[:50]} ({source})")

    if total == 0:
        return Score(
            name="content_originality",
            score=1.0,
            metadata={"total": 0, "social": 0},
        )

    original_ratio = 1.0 - (social / total)
    final = min(1.0, original_ratio / target_ratio)

    return Score(
        name="content_originality",
        score=round(final, 3),
        metadata={
            "total": total,
            "social": social,
            "original_ratio": round(original_ratio, 3),
            "social_items": social_items,
        },
    )


HEURISTIC_SCORERS = [
    source_diversity,
    category_coverage,
    link_count,
    section_balance,
    semantic_dedup,
    off_topic_leakage,
    intro_quality,
    summary_quality,
    content_originality,
]
