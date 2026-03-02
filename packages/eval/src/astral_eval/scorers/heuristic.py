"""Heuristic (non-LLM) newsletter quality scorers.

Each scorer accepts ``output`` (a serialized NewsletterDraft dict) and an
optional ``input`` (list of serialized ContentItem dicts), returning a Score.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from astral_eval.scores import Score


def source_diversity(
    *,
    output: dict[str, Any],
    input: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Score:
    """Shannon entropy → Effective Number of Sources, scored against a target.

    ENS = e^H where H is Shannon entropy over source_name frequencies.
    Score = min(1.0, ENS / TARGET).
    """
    target = 5

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
    """Fraction of input categories represented in the output."""
    input_cats: set[str] = set()
    if input:
        for item in input:
            for cat in item.get("categories", []):
                if cat:
                    input_cats.add(cat)

    if not input_cats:
        return Score(
            name="category_coverage",
            score=1.0,
            metadata={"input_cats": 0, "output_cats": 0},
        )

    output_cats: set[str] = set()
    for section in output.get("sections", []):
        cat = section.get("category")
        if cat:
            output_cats.add(cat)
        # Items don't carry category directly, only sections do

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
