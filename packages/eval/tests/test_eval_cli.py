"""Tests for the astral-eval CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from click.testing import CliRunner

from astral_eval.cli import cli


def test_quality_help() -> None:
    """quality --help works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["quality", "--help"])
    assert result.exit_code == 0
    assert "Evaluate newsletter quality" in result.output


def test_quality_no_items(tmp_path, monkeypatch) -> None:
    """quality command handles missing data gracefully."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["quality", "--since", "1", "--no-llm"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "No items found" in result.output


def test_quality_no_llm_with_items(tmp_path, monkeypatch, make_item) -> None:
    """quality --no-llm succeeds with seeded store."""
    from astral_core import ContentStore, SpaceCategory

    monkeypatch.chdir(tmp_path)

    store = ContentStore(base_dir=tmp_path / "data")
    now = datetime.now(UTC)
    for i in range(5):
        item = make_item(
            title=f"Article {i}",
            source_url=f"https://example.com/{i}",
            source_name=f"Source{i % 3}",
            categories=[SpaceCategory.LAUNCH_VEHICLES]
            if i % 2 == 0
            else [SpaceCategory.SPACE_SCIENCE],
            published_at=now - timedelta(hours=i),
        )
        store.save(item)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["quality", "--since", "7", "--no-llm", "--strategy", "headlines-only"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "source_diversity" in result.output
    assert "category_coverage" in result.output
    assert "link_count" in result.output
    assert "Average" in result.output


def test_quality_output_file(tmp_path, monkeypatch, make_item) -> None:
    """quality --output writes results JSON."""
    from astral_core import ContentStore

    monkeypatch.chdir(tmp_path)

    store = ContentStore(base_dir=tmp_path / "data")
    item = make_item(
        title="Test Article",
        source_url="https://example.com/test",
        published_at=datetime.now(UTC) - timedelta(hours=1),
    )
    store.save(item)

    out = tmp_path / "results.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["quality", "--since", "7", "--no-llm", "--output", str(out)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert out.exists()

    import json

    data = json.loads(out.read_text())
    assert "source_diversity" in data
