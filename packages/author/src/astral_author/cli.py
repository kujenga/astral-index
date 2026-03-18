"""CLI for the newsletter authoring pipeline."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import click

from astral_core import ContentItem, ContentStore, bootstrap

from .pipeline import STRATEGIES, build_strategy


def _previous_weekday(d: date, weekday: int) -> date:
    """Return the most recent date with the given weekday (0=Mon, 2=Wed, etc.).

    If *d* is already on that weekday, returns *d* itself.
    """
    days_back = (d.weekday() - weekday) % 7
    return d - timedelta(days=days_back)


def _wednesday_window() -> tuple[datetime, datetime, date]:
    """Compute the default Wed-to-Wed content window.

    Returns (since, before, issue_date) where:
      - before = most recent Wednesday (inclusive of today if Wednesday)
      - since  = the Wednesday one week before *before*
      - issue_date = *before* (the Wednesday at the end of the window)
    """
    today = date.today()
    end_wed = _previous_weekday(today, 2)  # Wednesday = 2
    start_wed = end_wed - timedelta(days=7)
    since = datetime.combine(start_wed, datetime.min.time(), tzinfo=UTC)
    before = datetime.combine(end_wed, datetime.min.time(), tzinfo=UTC)
    return since, before, end_wed


def _parse_since(ctx: click.Context, param: click.Parameter, value: str) -> datetime:
    """Click callback: accept integer days-back or YYYY-MM-DD date string."""
    try:
        days = int(value)
        return datetime.now(UTC) - timedelta(days=days)
    except ValueError:
        pass
    try:
        return datetime.combine(
            date.fromisoformat(value), datetime.min.time(), tzinfo=UTC
        )
    except ValueError:
        raise click.BadParameter(
            f"expected integer or YYYY-MM-DD, got {value!r}"
        ) from None


def _parse_before(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> datetime | None:
    """Click callback: accept YYYY-MM-DD date string or None."""
    if value is None:
        return None
    try:
        return datetime.combine(
            date.fromisoformat(value), datetime.min.time(), tzinfo=UTC
        )
    except ValueError:
        raise click.BadParameter(f"expected YYYY-MM-DD, got {value!r}") from None


def _describe_range(since: datetime, before: datetime | None) -> str:
    """Human-readable description of the date window."""
    s = since.strftime("%Y-%m-%d")
    if before:
        return f"{s} to {before.strftime('%Y-%m-%d')}"
    return f"since {s}"


@click.group()
def cli() -> None:
    """Astral Index — newsletter authoring pipeline."""
    bootstrap()


@cli.command()
@click.option(
    "--since",
    default=None,
    type=str,
    help="Days back (integer) or start date (YYYY-MM-DD). Default: previous Wednesday.",
)
@click.option(
    "--before",
    default=None,
    type=str,
    help="Exclusive upper-bound date (YYYY-MM-DD). Default: most recent Wednesday.",
)
@click.option(
    "--issue-date",
    default=None,
    type=str,
    help="Issue date (YYYY-MM-DD). Default: ending Wednesday.",
)
@click.option(
    "--strategy",
    "strategy_name",
    default="baseline",
    type=click.Choice(list(STRATEGIES.keys())),
    help="Pipeline strategy to use.",
)
@click.option(
    "--max-items",
    default=50,
    type=int,
    help="Maximum items to include.",
)
@click.option("--dry-run", is_flag=True, help="Rank and cluster only.")
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(),
    help="Write markdown to file instead of a staging directory.",
)
def draft(
    since: str | None,
    before: str | None,
    issue_date: str | None,
    strategy_name: str,
    max_items: int,
    dry_run: bool,
    output_path: str | None,
) -> None:
    """Generate a newsletter draft from stored items.

    Default cadence is Wednesday-to-Wednesday. Without --since/--before, uses
    the most recent Wed-to-Wed window with the issue dated on the ending Wednesday.
    """
    # Resolve the content window and issue date
    if since is None and before is None:
        # Default: Wed-to-Wed window
        since_dt, before_dt, default_issue_date = _wednesday_window()
        resolved_issue_date = (
            date.fromisoformat(issue_date) if issue_date else default_issue_date
        )
    else:
        # Explicit dates — use the parse callbacks manually
        since_dt = _parse_since(None, None, since or "7")  # type: ignore[arg-type]
        before_dt = _parse_before(None, None, before)  # type: ignore[arg-type]
        if issue_date:
            resolved_issue_date = date.fromisoformat(issue_date)
        elif before_dt:
            resolved_issue_date = before_dt.date()
        else:
            resolved_issue_date = date.today()

    asyncio.run(
        _draft(
            since_dt,
            before_dt,
            resolved_issue_date,
            strategy_name,
            max_items,
            dry_run,
            output_path,
        )
    )


async def _draft(
    since: datetime,
    before: datetime | None,
    issue_date: date,
    strategy_name: str,
    max_items: int,
    dry_run: bool,
    output_path: str | None,
) -> None:
    store = ContentStore()
    items = store.list_items(since=since, before=before)

    if not items:
        click.echo("No items found.")
        return

    click.echo(f"Found {len(items)} items ({_describe_range(since, before)})")

    pipeline = build_strategy(strategy_name)

    if dry_run:
        # Run ranking + clustering only
        scored = await pipeline.ranker.rank(items, max_items=max_items)
        sections = await pipeline.clusterer.cluster(scored)

        click.echo(f"\nStrategy: {strategy_name}")
        click.echo(f"Ranked: {len(scored)} items (from {len(items)})")
        click.echo(f"Sections: {len(sections)}\n")

        for section in sections:
            n = len(section.source_items)
            click.echo(
                f"  [{section.section_type.value}] {section.heading} ({n} items)"
            )
        return

    start = time.monotonic()
    items_by_id: dict[str, ContentItem] = {item.id: item for item in items}

    click.echo(f"Strategy: {strategy_name}\n")

    # 1. Rank
    click.echo("Ranking items... ", nl=False)
    scored = await pipeline.ranker.rank(items, max_items=max_items)
    click.echo(f"{len(scored)} selected")

    # 2. Cluster
    click.echo("Clustering... ", nl=False)
    sections = await pipeline.clusterer.cluster(scored)
    click.echo(f"{len(sections)} sections")

    # 3. Summarize
    total_items = sum(len(s.source_items) for s in sections)
    summarized = []
    with click.progressbar(
        length=total_items, label="Summarizing", show_pos=True
    ) as bar:
        for section in sections:
            result = await pipeline.summarizer.summarize(section, items_by_id)
            bar.update(len(section.source_items))
            summarized.append(result)

    # 4. Draft
    click.echo("Drafting... ", nl=False)
    newsletter = await pipeline.drafter.draft(summarized, items_by_id)
    click.echo("done")

    elapsed = time.monotonic() - start
    # Override issue_date and re-render title to match the target date
    title = f"Astral Index — {issue_date.strftime('%B %d, %Y')}"
    newsletter = newsletter.model_copy(
        update={
            "issue_date": issue_date,
            "title": title,
            "markdown": newsletter.markdown.replace(newsletter.title, title, 1),
            "strategy_name": pipeline.name,
            "generation_seconds": round(elapsed, 2),
        }
    )

    if output_path:
        md_path = Path(output_path)
    else:
        # Default: stage in git-tracked issues/ directory
        issue_date_str = newsletter.issue_date.isoformat()
        md_path = Path("issues") / issue_date_str / "draft.md"

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(newsletter.markdown)
    click.echo(f"Draft written to {md_path}")

    json_path = md_path.with_suffix(".json")
    json_path.write_text(newsletter.model_dump_json(indent=2))
    click.echo(f"JSON written to {json_path}")

    click.echo("\n--- Pipeline stats ---")
    click.echo(f"Strategy: {newsletter.strategy_name}")
    click.echo(f"Items: {newsletter.total_output_items}")
    click.echo(f"Sections: {len(newsletter.sections)}")
    click.echo(f"Words: {newsletter.word_count}")
    click.echo(f"Time: {newsletter.generation_seconds}s")

    if not output_path:
        issue_dir = md_path.parent
        since_str = since.strftime("%Y-%m-%d")
        click.echo(f"\nStaged at {issue_dir}/")
        click.echo("Next steps:")
        click.echo(
            f"  1. Evaluate:  uv run --package astral-eval astral-eval"
            f" quality --since {since_str}"
            f" --draft-file {json_path}"
            f" --output {issue_dir}/eval.json"
        )
        click.echo(f"  2. Review:    edit {md_path}")
        click.echo(f"  3. Commit:    git add {issue_dir} && git commit")
        click.echo(
            f"  4. Publish:   uv run --package astral-serve"
            f" astral-serve draft {newsletter.issue_date}"
        )


@cli.command()
def strategies() -> None:
    """List registered pipeline strategies."""
    for name in STRATEGIES:
        click.echo(f"  {name}")


@cli.command()
@click.argument("strategy_names", nargs=-1, required=True)
@click.option(
    "--since",
    default="7",
    type=str,
    callback=_parse_since,
    help="Days back (integer) or start date (YYYY-MM-DD).",
)
@click.option(
    "--before",
    default=None,
    type=str,
    callback=_parse_before,
    help="Exclusive upper-bound date (YYYY-MM-DD).",
)
@click.option(
    "--max-items",
    default=50,
    type=int,
    help="Maximum items to include.",
)
@click.option(
    "--output-dir",
    default="data/drafts",
    type=click.Path(),
    help="Directory for draft output files.",
)
def compare(
    strategy_names: tuple[str, ...],
    since: datetime,
    before: datetime | None,
    max_items: int,
    output_dir: str,
) -> None:
    """Run multiple strategies on the same input and compare."""
    # Validate strategy names
    for name in strategy_names:
        if name not in STRATEGIES:
            raise click.BadParameter(
                f"Unknown strategy: {name}. Available: {', '.join(STRATEGIES.keys())}"
            )
    asyncio.run(_compare(strategy_names, since, before, max_items, output_dir))


async def _compare(
    strategy_names: tuple[str, ...],
    since: datetime,
    before: datetime | None,
    max_items: int,
    output_dir: str,
) -> None:
    store = ContentStore()
    items = store.list_items(since=since, before=before)

    if not items:
        click.echo("No items found.")
        return

    click.echo(f"Found {len(items)} items ({_describe_range(since, before)})")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    results = []
    for name in strategy_names:
        click.echo(f"\nRunning strategy: {name}...")
        pipeline = build_strategy(name)
        newsletter = await pipeline.run(items, max_items=max_items)

        # Write markdown and JSON sidecar
        md_path = out / f"{today}_{name}.md"
        md_path.write_text(newsletter.markdown)

        json_path = out / f"{today}_{name}.json"
        json_path.write_text(newsletter.model_dump_json(indent=2))

        click.echo(f"  -> {md_path} / {json_path.name}")

        results.append(newsletter)

    # Write comparison metadata
    meta = {
        "date": today,
        "input_items": len(items),
        "date_range": _describe_range(since, before),
        "max_items": max_items,
        "strategies": [
            {
                "name": r.strategy_name,
                "words": r.word_count,
                "sections": len(r.sections),
                "items": r.total_output_items,
                "seconds": r.generation_seconds,
                "model": r.model_used,
            }
            for r in results
        ],
    }
    meta_path = out / f"{today}_comparison.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    # Print comparison table
    click.echo("\n--- Comparison ---")
    click.echo(
        f"{'Strategy':<20} {'Words':>6} {'Sections':>8} {'Items':>6} {'Time':>7}"
    )
    click.echo("-" * 52)
    for r in results:
        click.echo(
            f"{r.strategy_name:<20} {r.word_count:>6} "
            f"{len(r.sections):>8} {r.total_output_items:>6} "
            f"{r.generation_seconds:>6.1f}s"
        )
