"""Tests for the quality evaluation runner."""

from __future__ import annotations

from astral_author.pipeline import build_strategy
from astral_core import ContentItem
from astral_eval.runner import HEURISTIC_SCORERS, run_quality_eval
from astral_eval.scores import Score


async def test_heuristic_only_returns_three_scores(
    sample_items: list[ContentItem],
) -> None:
    """run_quality_eval(use_llm=False) returns exactly the 3 heuristic scores."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(sample_items, max_items=50)

    scores = await run_quality_eval(draft, sample_items, use_llm=False)

    assert len(scores) == len(HEURISTIC_SCORERS)
    for score in scores.values():
        assert isinstance(score, Score)
        assert 0.0 <= score.score <= 1.0


async def test_heuristic_score_names_match(
    sample_items: list[ContentItem],
) -> None:
    """Score names match the expected heuristic scorer names."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(sample_items, max_items=50)

    scores = await run_quality_eval(draft, sample_items, use_llm=False)

    expected = {"source_diversity", "category_coverage", "link_count"}
    assert set(scores.keys()) == expected


async def test_llm_scorers_skipped_without_keys(
    sample_items: list[ContentItem],
) -> None:
    """With no API keys, use_llm=True still only returns heuristic scores."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(sample_items, max_items=50)

    scores = await run_quality_eval(draft, sample_items, use_llm=True)

    # LLM scorers return None without keys, so only heuristics present
    assert len(scores) == len(HEURISTIC_SCORERS)


async def test_empty_input_doesnt_crash() -> None:
    """Runner handles empty item list without errors."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run([], max_items=50)

    scores = await run_quality_eval(draft, [], use_llm=False)
    assert isinstance(scores, dict)
    assert len(scores) == len(HEURISTIC_SCORERS)
