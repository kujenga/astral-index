"""Tests for heuristic (non-LLM) scorers."""

from __future__ import annotations

from astral_eval.scorers.heuristic import (
    category_coverage,
    link_count,
    source_diversity,
)
from astral_eval.scores import Score


def _items_section(items: list[dict]) -> dict:
    """Build a minimal section dict with ItemSummary-like dicts."""
    return {"heading": "Test", "section_type": "brief", "items": items}


def _item(source_name: str, source_url: str = "https://example.com") -> dict:
    return {
        "item_id": "abc",
        "title": "Test",
        "source_url": source_url,
        "source_name": source_name,
        "summary": "Summary.",
        "relevance_score": 0.5,
    }


# -- source_diversity --


class TestSourceDiversity:
    def test_uniform_five_sources(self):
        """Five uniformly distributed sources → score ≈ 1.0."""
        items = [_item(f"Source{i}") for i in range(5)]
        output = {"sections": [_items_section(items)]}
        result = source_diversity(output=output)
        assert isinstance(result, Score)
        assert result.name == "source_diversity"
        assert result.score >= 0.99

    def test_single_source(self):
        """All items from one source → low score."""
        items = [_item("SpaceNews") for _ in range(5)]
        output = {"sections": [_items_section(items)]}
        result = source_diversity(output=output)
        # ENS=1 for single source, score = 1/5 = 0.2
        assert result.score == pytest.approx(0.2, abs=0.01)

    def test_empty_output(self):
        """No items → score 0.0."""
        output = {"sections": []}
        result = source_diversity(output=output)
        assert result.score == 0.0

    def test_two_sources_unequal(self):
        """Two sources with unequal distribution → between 0.2 and 1.0."""
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
        """All input categories represented in output → 1.0."""
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
        """Half of input categories covered → 0.5."""
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

    def test_no_input_categories(self):
        """No categories in input → score 1.0 (nothing to cover)."""
        input_items = [{"categories": []}, {"categories": []}]
        output = {"sections": []}
        result = category_coverage(output=output, input=input_items)
        assert result.score == 1.0

    def test_no_input_at_all(self):
        """No input provided → score 1.0."""
        output = {"sections": []}
        result = category_coverage(output=output, input=None)
        assert result.score == 1.0

    def test_metadata_tracks_coverage(self):
        """Metadata reports input/output cat counts and missing."""
        input_items = [
            {"categories": ["launch_vehicles", "lunar"]},
            {"categories": ["space_science"]},
        ]
        output = {
            "sections": [
                {"heading": "Launch", "category": "launch_vehicles", "items": []},
            ]
        }
        result = category_coverage(output=output, input=input_items)
        assert result.metadata["input_cats"] == 3
        assert result.metadata["output_cats"] == 1
        assert "lunar" in result.metadata["missing"]
        assert "space_science" in result.metadata["missing"]


# -- link_count --


class TestLinkCount:
    def test_links_per_item_above_one(self):
        """More links than items → 1.0."""
        md = (
            "- [Article 1](https://example.com/1)\n"
            "- [Article 2](https://example.com/2)\n"
            "- [Article 3](https://example.com/3)\n"
        )
        output = {"markdown": md, "total_output_items": 2}
        result = link_count(output=output)
        assert result.score == 1.0
        assert result.metadata["links"] == 3

    def test_links_less_than_items(self):
        """Fewer links than items → proportional score."""
        md = "- [Article 1](https://example.com/1)\n"
        output = {"markdown": md, "total_output_items": 4}
        result = link_count(output=output)
        assert result.score == pytest.approx(0.25, abs=0.01)

    def test_no_items_still_scores(self):
        """Zero total items → 1.0 (sanity: nothing to link)."""
        output = {"markdown": "", "total_output_items": 0}
        result = link_count(output=output)
        assert result.score == 1.0

    def test_non_http_links_ignored(self):
        """Only http/https links count."""
        md = "[Local](file:///tmp/x) [Web](https://example.com/x)"
        output = {"markdown": md, "total_output_items": 2}
        result = link_count(output=output)
        assert result.metadata["links"] == 1

    def test_metadata_has_ratio(self):
        """Metadata includes raw count and per-item ratio."""
        md = "[A](https://a.com) [B](https://b.com)"
        output = {"markdown": md, "total_output_items": 4}
        result = link_count(output=output)
        assert result.metadata["ratio"] == 0.5


import pytest  # noqa: E402 (used in approx assertions above)
