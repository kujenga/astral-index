"""Tests for heuristic (non-LLM) scorers."""

from __future__ import annotations

import pytest

from astral_eval.scorers.heuristic import (
    category_coverage,
    off_topic_leakage,
    section_balance,
    semantic_dedup,
    source_diversity,
)
from astral_eval.scores import Score


def _items_section(items: list[dict], **kwargs) -> dict:
    """Build a minimal section dict with ItemSummary-like dicts."""
    return {"heading": "Test", "section_type": "brief", "items": items, **kwargs}


def _item(source_name: str, source_url: str = "https://example.com", **kwargs) -> dict:
    return {
        "item_id": "abc",
        "title": "Test",
        "source_url": source_url,
        "source_name": source_name,
        "summary": "Summary.",
        "relevance_score": 0.5,
        **kwargs,
    }


# -- source_diversity --


class TestSourceDiversity:
    def test_uniform_five_sources(self):
        """Five uniformly distributed sources -> score ~= 1.0."""
        items = [_item(f"Source{i}") for i in range(5)]
        output = {"sections": [_items_section(items)]}
        result = source_diversity(output=output)
        assert isinstance(result, Score)
        assert result.name == "source_diversity"
        assert result.score >= 0.99

    def test_single_source(self):
        """All items from one source -> low score."""
        items = [_item("SpaceNews") for _ in range(5)]
        output = {"sections": [_items_section(items)]}
        result = source_diversity(output=output)
        # ENS=1 for single source, score = 1/5 = 0.2
        assert result.score == pytest.approx(0.2, abs=0.01)

    def test_empty_output(self):
        """No items -> score 0.0."""
        output = {"sections": []}
        result = source_diversity(output=output)
        assert result.score == 0.0

    def test_two_sources_unequal(self):
        """Two sources with unequal distribution -> between 0.2 and 1.0."""
        items = [_item("SpaceNews")] * 4 + [_item("Ars Technica")]
        output = {"sections": [_items_section(items)]}
        result = source_diversity(output=output)
        assert 0.2 < result.score < 1.0
        assert result.metadata["n_sources"] == 2

    def test_metadata_contains_ens(self):
        """Metadata includes ENS and source count."""
        items = [_item(f"Source{i}") for i in range(3)]
        output = {"sections": [_items_section(items)]}
        result = source_diversity(output=output)
        assert "ens" in result.metadata
        assert "n_sources" in result.metadata
        assert result.metadata["n_sources"] == 3


# -- category_coverage --


class TestCategoryCoverage:
    def test_full_coverage(self):
        """All input categories represented in output -> 1.0."""
        input_items = [
            {"categories": ["launch_vehicles"]},
            {"categories": ["space_science"]},
        ]
        output = {
            "sections": [
                {"heading": "Launch", "category": "launch_vehicles", "items": []},
                {"heading": "Science", "category": "space_science", "items": []},
            ]
        }
        result = category_coverage(output=output, input=input_items)
        assert result.score == 1.0

    def test_half_coverage(self):
        """Half of input categories covered -> 0.5."""
        input_items = [
            {"categories": ["launch_vehicles"]},
            {"categories": ["space_science"]},
        ]
        output = {
            "sections": [
                {"heading": "Launch", "category": "launch_vehicles", "items": []},
            ]
        }
        result = category_coverage(output=output, input=input_items)
        assert result.score == 0.5

    def test_item_level_coverage(self):
        """Items in a null-category section still count via item-level lookup."""
        input_items = [
            {"id": "item1", "categories": ["launch_vehicles"]},
            {"id": "item2", "categories": ["space_science"]},
            {"id": "item3", "categories": ["lunar"]},
        ]
        output = {
            "sections": [
                # Deep-dive section covers launch_vehicles at section level
                {
                    "heading": "Launch",
                    "category": "launch_vehicles",
                    "items": [{"item_id": "item1"}],
                },
                # Brief section has no category but contains items from other cats
                {
                    "heading": "In Brief",
                    "category": None,
                    "items": [
                        {"item_id": "item2"},
                        {"item_id": "item3"},
                    ],
                },
            ]
        }
        result = category_coverage(output=output, input=input_items)
        # All 3 categories should be covered via item-level matching
        assert result.score == 1.0

    def test_no_input_categories(self):
        """No categories in input -> score 1.0 (nothing to cover)."""
        input_items = [{"categories": []}, {"categories": []}]
        output = {"sections": []}
        result = category_coverage(output=output, input=input_items)
        assert result.score == 1.0

    def test_no_input_at_all(self):
        """No input provided -> score 1.0."""
        output = {"sections": []}
        result = category_coverage(output=output, input=None)
        assert result.score == 1.0

    def test_off_topic_excluded_from_input(self):
        """off_topic excluded from input cats (filtered by pipeline)."""
        input_items = [
            {"id": "i1", "categories": ["launch_vehicles"]},
            {"id": "i2", "categories": ["off_topic"]},
        ]
        output = {
            "sections": [
                {
                    "heading": "Launch",
                    "category": "launch_vehicles",
                    "items": [{"item_id": "i1"}],
                },
            ]
        }
        result = category_coverage(output=output, input=input_items)
        assert result.score == 1.0
        assert result.metadata["input_cats"] == 1

    def test_metadata_tracks_coverage(self):
        """Metadata reports input/output cat counts and missing."""
        input_items = [
            {"id": "i1", "categories": ["launch_vehicles", "lunar"]},
            {"id": "i2", "categories": ["space_science"]},
        ]
        output = {
            "sections": [
                {
                    "heading": "Launch",
                    "category": "launch_vehicles",
                    "items": [{"item_id": "i1"}],
                },
            ]
        }
        result = category_coverage(output=output, input=input_items)
        # launch_vehicles covered (section) + lunar covered (item i1 has it)
        assert result.metadata["input_cats"] == 3
        assert "space_science" in result.metadata["missing"]
        assert "lunar" in result.metadata["covered"]


# -- section_balance --


class TestSectionBalance:
    def test_uniform_sections(self):
        """Equal-sized sections -> high score."""
        output = {
            "sections": [
                _items_section([_item("A")] * 5),
                _items_section([_item("B")] * 5),
                _items_section([_item("C")] * 5),
            ]
        }
        result = section_balance(output=output)
        assert result.score >= 0.95

    def test_imbalanced_sections(self):
        """Heavily imbalanced sections (27/7/10/4) -> low score."""
        output = {
            "sections": [
                _items_section([_item("A")] * 27),
                _items_section([_item("B")] * 7),
                _items_section([_item("C")] * 10),
                _items_section([_item("D")] * 4),
            ]
        }
        result = section_balance(output=output)
        # Should detect the oversized section and score low
        assert result.score < 0.7
        assert len(result.metadata["oversized"]) == 1
        assert 27 in result.metadata["oversized"]

    def test_single_section(self):
        """One section -> 0.5 (can't measure balance)."""
        output = {"sections": [_items_section([_item("A")] * 10)]}
        result = section_balance(output=output)
        assert result.score == 0.5

    def test_empty_sections(self):
        """No sections -> 1.0."""
        output = {"sections": []}
        result = section_balance(output=output)
        assert result.score == 1.0


# -- semantic_dedup --


class TestSemanticDedup:
    def test_no_duplicates(self):
        """All unique titles -> 1.0."""
        items = [
            _item("A", title="SpaceX launches Starship"),
            _item("B", title="NASA Artemis III delay announced"),
            _item("C", title="JWST discovers new exoplanet"),
        ]
        output = {"sections": [_items_section(items)]}
        result = semantic_dedup(output=output)
        assert result.score == 1.0

    def test_near_duplicate_titles(self):
        """Near-duplicate titles -> penalty applied."""
        items = [
            _item("A", title="Watch the Starlink launch live"),
            _item("B", title="Watch the Starlink launch!"),
            _item("C", title="JWST discovers new exoplanet"),
        ]
        output = {"sections": [_items_section(items)]}
        result = semantic_dedup(output=output)
        assert result.score < 1.0
        assert result.metadata["n_duplicates"] >= 1

    def test_identical_titles(self):
        """Identical titles -> clear duplicate."""
        items = [
            _item("A", title="Starlink deployment confirmed"),
            _item("B", title="Starlink deployment confirmed"),
        ]
        output = {"sections": [_items_section(items)]}
        result = semantic_dedup(output=output)
        assert result.score <= 0.8

    def test_single_item(self):
        """Single item -> 1.0 (nothing to compare)."""
        output = {"sections": [_items_section([_item("A", title="Solo article")])]}
        result = semantic_dedup(output=output)
        assert result.score == 1.0

    def test_same_event_different_wording(self):
        """Same event described differently -> flagged via token Jaccard."""
        items = [
            _item("A", title="Falcon 9 launches Starlink Group 12 mission"),
            _item("B", title="Starlink Group 12 deployment after Falcon 9 launch"),
            _item("C", title="JWST discovers new exoplanet"),
        ]
        output = {"sections": [_items_section(items)]}
        result = semantic_dedup(output=output)
        assert result.score < 1.0
        assert result.metadata["n_duplicates"] >= 1

    def test_different_stories_same_domain_not_flagged(self):
        """Different events sharing domain words -> NOT flagged."""
        items = [
            _item("A", title="SpaceX launches crew to ISS"),
            _item("B", title="SpaceX Starship completes orbital test"),
        ]
        output = {"sections": [_items_section(items)]}
        result = semantic_dedup(output=output)
        assert result.score == 1.0


# -- off_topic_leakage --


class TestOffTopicLeakage:
    def test_all_categorized(self):
        """All items have categories -> 1.0."""
        input_items = [
            {"id": "a1", "categories": ["launch_vehicles"]},
            {"id": "a2", "categories": ["space_science"]},
        ]
        items = [
            _item("A", item_id="a1"),
            _item("B", item_id="a2"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 1.0

    def test_some_uncategorized(self):
        """Mix of categorized and uncategorized -> proportional score."""
        input_items = [
            {"id": "a1", "categories": ["launch_vehicles"]},
            {"id": "a2", "categories": []},
        ]
        items = [
            _item("A", item_id="a1"),
            _item("B", item_id="a2"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 0.5

    def test_off_topic_items(self):
        """Items with off_topic category count as off-topic."""
        input_items = [
            {"id": "a1", "categories": ["launch_vehicles"]},
            {"id": "a2", "categories": ["off_topic"]},
        ]
        items = [
            _item("A", item_id="a1"),
            _item("B", item_id="a2"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 0.5

    def test_empty_output(self):
        """No output items -> 1.0."""
        output = {"sections": []}
        result = off_topic_leakage(output=output)
        assert result.score == 1.0

    def test_non_journalism_title_flagged(self):
        """Item has categories but title matches non-journalism pattern -> off-topic."""
        input_items = [
            {"id": "a1", "categories": ["launch_vehicles"]},
            {"id": "a2", "categories": ["space_science"]},
        ]
        items = [
            _item("A", item_id="a1", title="SpaceX launches Starship"),
            _item("B", item_id="a2", title="Best AI games to play this weekend"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 0.5
        assert result.metadata["off_topic"] == 1

    def test_normal_title_not_flagged(self):
        """Normal space news title with categories -> not flagged."""
        input_items = [
            {"id": "a1", "categories": ["launch_vehicles"]},
        ]
        items = [
            _item("A", item_id="a1", title="SpaceX launches Starship"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 1.0

    def test_buying_guide_flagged(self):
        """Buying guide title -> flagged as off-topic."""
        input_items = [
            {"id": "a1", "categories": ["space_science"]},
        ]
        items = [
            _item("A", item_id="a1", title="Best telescopes to buy in 2026"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 0.0
        assert result.metadata["off_topic"] == 1

    def test_horoscope_flagged(self):
        """Horoscope title -> flagged as off-topic."""
        input_items = [
            {"id": "a1", "categories": ["space_science"]},
        ]
        items = [
            _item("A", item_id="a1", title="Your Zodiac horoscope for March"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 0.0

    def test_space_review_not_flagged(self):
        """Space program review -> NOT flagged (no gaming prefix)."""
        input_items = [
            {"id": "a1", "categories": ["space_policy"]},
        ]
        items = [
            _item("A", item_id="a1", title="NASA Artemis program review"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 1.0

    def test_entertainment_title_flagged(self):
        """Item with entertainment title -> flagged as off-topic."""
        input_items = [
            {"id": "a1", "categories": ["space_science"]},
        ]
        items = [
            _item("A", item_id="a1", title="Stunning image of Jupiter from Hubble"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 0.0
        assert result.metadata["off_topic"] == 1
        assert result.metadata["entertainment"] == 1

    def test_stargazing_guide_flagged(self):
        """Stargazing guide -> flagged as entertainment."""
        input_items = [
            {"id": "a1", "categories": ["space_science"]},
        ]
        items = [
            _item(
                "A", item_id="a1", title="March stargazing guide: planets and meteors"
            ),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 0.0
        assert result.metadata["entertainment"] == 1

    def test_scifi_review_flagged(self):
        """Sci-fi review -> flagged as entertainment."""
        input_items = [
            {"id": "a1", "categories": ["space_science"]},
        ]
        items = [
            _item("A", item_id="a1", title="New sci-fi movie review: Gravity 2"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        assert result.score == 0.0
        assert result.metadata["entertainment"] == 1

    def test_entertainment_metadata_tracked_separately(self):
        """Entertainment items tracked in separate metadata field."""
        input_items = [
            {"id": "a1", "categories": ["launch_vehicles"]},
            {"id": "a2", "categories": ["space_science"]},
            {"id": "a3", "categories": ["space_science"]},
        ]
        items = [
            _item("A", item_id="a1", title="SpaceX launches Starship"),
            _item("B", item_id="a2", title="Photo of the Day: Nebula"),
            _item("C", item_id="a3", title="Best AI games to play"),
        ]
        output = {"sections": [_items_section(items)]}
        result = off_topic_leakage(output=output, input=input_items)
        # 2 out of 3 are off-topic
        assert result.metadata["off_topic"] == 2
        # Only 1 is entertainment (photo), the other is non-journalism (games)
        assert result.metadata["entertainment"] == 1
