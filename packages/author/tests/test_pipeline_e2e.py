"""End-to-end tests for the authoring pipeline.

These tests exercise the full pipeline (rank -> cluster -> summarize -> draft)
using the headlines-only strategy, which requires no LLM API key. They verify
that all stages integrate correctly and produce a valid NewsletterDraft.
"""

from __future__ import annotations

from datetime import date

import pytest

from astral_author.cluster import CategoryClusterer
from astral_author.draft import MarkdownDrafter
from astral_author.models import (
    NewsletterDraft,
    SectionType,
)
from astral_author.pipeline import (
    STRATEGIES,
    DraftPipeline,
    build_strategy,
)
from astral_author.rank import EngagementRanker
from astral_author.summarize import ExcerptSummarizer
from astral_core import ContentItem

# -- Full pipeline e2e --


@pytest.mark.asyncio
async def test_headlines_only_pipeline_produces_valid_draft(
    sample_items: list[ContentItem],
) -> None:
    """The headlines-only strategy produces a complete, valid draft."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(sample_items, max_items=50)

    assert isinstance(draft, NewsletterDraft)
    assert draft.strategy_name == "headlines-only"
    assert draft.generation_seconds >= 0
    assert draft.total_input_items == len(sample_items)
    assert draft.total_output_items > 0
    assert draft.word_count > 0
    assert draft.issue_date == date.today()


@pytest.mark.asyncio
async def test_pipeline_markdown_contains_expected_structure(
    sample_items: list[ContentItem],
) -> None:
    """The rendered markdown has the expected heading/section structure."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(sample_items, max_items=50)

    md = draft.markdown
    # Top-level heading
    assert md.startswith("# Astral Index")
    # At least one section heading
    assert "## " in md
    # Closing
    assert "clear skies and steady orbits" in md
    # Contains links
    assert "](http" in md
    # Horizontal rule before closing
    assert "---" in md


@pytest.mark.asyncio
async def test_pipeline_sections_have_items(
    sample_items: list[ContentItem],
) -> None:
    """Every section in the draft has at least one summarized item."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(sample_items, max_items=50)

    assert len(draft.sections) >= 2  # at least deep-dive + brief
    for section in draft.sections:
        assert len(section.items) > 0
        for item in section.items:
            assert item.title
            assert item.source_url
            assert item.summary


@pytest.mark.asyncio
async def test_pipeline_respects_max_items(
    sample_items: list[ContentItem],
) -> None:
    """Pipeline truncates to max_items."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(sample_items, max_items=3)

    assert draft.total_output_items <= 3


@pytest.mark.asyncio
async def test_pipeline_item_ids_trace_back_to_input(
    sample_items: list[ContentItem],
) -> None:
    """All item IDs in the draft exist in the original input."""
    input_ids = {item.id for item in sample_items}
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(sample_items, max_items=50)

    for section in draft.sections:
        for sid in section.source_items:
            assert sid in input_ids
        for item_summary in section.items:
            assert item_summary.item_id in input_ids


# -- Stage integration --


@pytest.mark.asyncio
async def test_rank_then_cluster_produces_sections(
    sample_items: list[ContentItem],
) -> None:
    """Ranker output feeds correctly into the clusterer."""
    ranker = EngagementRanker()
    clusterer = CategoryClusterer()

    scored = await ranker.rank(sample_items, max_items=50)
    sections = await clusterer.cluster(scored)

    assert len(sections) >= 1
    # Should have at least one deep-dive and one brief
    types = {s.section_type for s in sections}
    assert SectionType.DEEP_DIVE in types or SectionType.BRIEF in types

    # All source_items should reference valid item IDs
    input_ids = {item.id for item in sample_items}
    for section in sections:
        for sid in section.source_items:
            assert sid in input_ids


@pytest.mark.asyncio
async def test_summarize_then_draft_produces_markdown(
    sample_items: list[ContentItem],
) -> None:
    """Summarizer fills in items, drafter renders them to markdown."""
    ranker = EngagementRanker()
    clusterer = CategoryClusterer()
    summarizer = ExcerptSummarizer()
    drafter = MarkdownDrafter()

    items_by_id = {item.id: item for item in sample_items}
    scored = await ranker.rank(sample_items, max_items=50)
    sections = await clusterer.cluster(scored)

    # Sections should have source_items but no item summaries yet
    for section in sections:
        assert len(section.source_items) > 0
        assert len(section.items) == 0

    # After summarization, items should be filled in
    summarized = []
    for section in sections:
        summarized.append(await summarizer.summarize(section, items_by_id))

    for section in summarized:
        assert len(section.items) > 0

    newsletter = await drafter.draft(summarized, items_by_id)
    assert newsletter.markdown
    assert newsletter.word_count > 0


# -- Strategy registry --


def test_strategy_registry_contains_expected_strategies() -> None:
    assert "baseline" in STRATEGIES
    assert "headlines-only" in STRATEGIES


def test_build_strategy_returns_pipeline() -> None:
    pipeline = build_strategy("headlines-only")
    assert isinstance(pipeline, DraftPipeline)
    assert pipeline.name == "headlines-only"


def test_build_strategy_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        build_strategy("nonexistent-strategy")


# -- Edge cases --


@pytest.mark.asyncio
async def test_pipeline_with_empty_input() -> None:
    """Pipeline handles empty input without crashing."""
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run([], max_items=50)

    assert isinstance(draft, NewsletterDraft)
    assert draft.total_output_items == 0
    assert len(draft.sections) == 0
    assert draft.word_count > 0  # still has title/intro/closing


@pytest.mark.asyncio
async def test_pipeline_with_single_item(make_item) -> None:
    """Pipeline handles a single item gracefully."""
    item = make_item(
        title="Solo article about Mars",
        source_url="https://example.com/solo",
        categories=[],
    )
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run([item], max_items=50)

    assert draft.total_output_items == 1
    assert len(draft.sections) >= 1


@pytest.mark.asyncio
async def test_pipeline_with_all_uncategorized(make_item) -> None:
    """When no items have categories, everything goes to In Brief."""
    items = [
        make_item(
            title=f"Article {i}",
            source_url=f"https://example.com/{i}",
            categories=[],
        )
        for i in range(5)
    ]
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(items, max_items=50)

    # All items should be in a single "In Brief" section
    assert len(draft.sections) == 1
    assert draft.sections[0].heading == "In Brief"
    assert draft.sections[0].section_type == SectionType.BRIEF
    assert draft.total_output_items == 5


@pytest.mark.asyncio
async def test_pipeline_deep_dive_threshold(make_item) -> None:
    """Categories with fewer than min_group_size items go to brief."""
    from astral_core import SpaceCategory

    items = [
        # 3 launch items -> deep-dive
        make_item(
            title=f"Launch {i}",
            source_url=f"https://example.com/launch-{i}",
            categories=[SpaceCategory.LAUNCH_VEHICLES],
        )
        for i in range(3)
    ] + [
        # 1 lunar item -> brief (below min_group_size=2)
        make_item(
            title="Lunar news",
            source_url="https://example.com/lunar",
            categories=[SpaceCategory.LUNAR],
        ),
    ]
    pipeline = build_strategy("headlines-only")
    draft = await pipeline.run(items, max_items=50)

    deep_dives = [s for s in draft.sections if s.section_type == SectionType.DEEP_DIVE]
    briefs = [s for s in draft.sections if s.section_type == SectionType.BRIEF]
    assert len(deep_dives) == 1
    assert deep_dives[0].category == SpaceCategory.LAUNCH_VEHICLES
    assert len(briefs) == 1
    assert len(briefs[0].items) == 1


# -- CLI --


def test_cli_strategies_command() -> None:
    """The strategies CLI command lists registered strategies."""
    from click.testing import CliRunner

    from astral_author.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["strategies"])
    assert result.exit_code == 0
    assert "baseline" in result.output
    assert "headlines-only" in result.output


def test_cli_draft_no_items(tmp_path, monkeypatch) -> None:
    """Draft command handles missing data directory gracefully."""
    from click.testing import CliRunner

    from astral_author.cli import cli

    # ContentStore defaults to CWD/data/, so chdir to an empty tmp dir
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["draft", "--since", "1", "--strategy", "headlines-only"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "No items found" in result.output
