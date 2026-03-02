"""CLI for the newsletter quality evaluation pipeline."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import click

from astral_author.models import NewsletterDraft
from astral_author.pipeline import STRATEGIES, build_strategy
from astral_core import ContentStore, bootstrap

from .runner import run_quality_eval


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


@click.group()
def cli() -> None:
    """Astral Index — newsletter quality evaluation."""
    bootstrap()


@cli.command()
@click.option(
    "--since",
    default="7",
    type=str,
    callback=_parse_since,
    help="Days back (integer) or start date (YYYY-MM-DD).",
)
@click.option(
    "--strategy",
    "strategy_name",
    default="headlines-only",
    type=click.Choice(list(STRATEGIES.keys())),
    help="Pipeline strategy for draft generation.",
)
@click.option(
    "--max-items",
    default=50,
    type=int,
    help="Maximum items to include.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Skip LLM judge scorers (heuristic only).",
)
@click.option(
    "--draft-file",
    default=None,
    type=click.Path(exists=True),
    help="Load draft from JSON file instead of generating.",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    type=click.Path(),
    help="Write full results JSON to file.",
)
def quality(
    since: datetime,
    strategy_name: str,
    max_items: int,
    no_llm: bool,
    draft_file: str | None,
    output_path: str | None,
) -> None:
    """Evaluate newsletter quality across multiple dimensions."""
    asyncio.run(
        _quality(since, strategy_name, max_items, no_llm, draft_file, output_path)
    )


async def _quality(
    since: datetime,
    strategy_name: str,
    max_items: int,
    no_llm: bool,
    draft_file: str | None,
    output_path: str | None,
) -> None:
    store = ContentStore()
    items = store.list_items(since=since)

    if not items:
        click.echo("No items found.")
        return

    click.echo(f"Found {len(items)} items (since {since.strftime('%Y-%m-%d')})")

    # Load or generate the draft
    if draft_file:
        raw = Path(draft_file).read_text()
        draft = NewsletterDraft.model_validate_json(raw)
        click.echo(f"Loaded draft from {draft_file}")
    else:
        click.echo(f"Generating draft with strategy: {strategy_name}")
        pipeline = build_strategy(strategy_name)
        draft = await pipeline.run(items, max_items=max_items)

    click.echo(
        f"Draft: {draft.word_count} words, {len(draft.sections)} sections, "
        f"{draft.total_output_items} items\n"
    )

    # Run evaluation
    mode = "heuristic only" if no_llm else "heuristic + LLM judges"
    click.echo(f"Running quality eval ({mode})...")
    scores = await run_quality_eval(draft, items, use_llm=not no_llm)

    # Print results table
    click.echo(f"\n{'Scorer':<25} {'Score':>6}  {'Details'}")
    click.echo("-" * 65)
    for name, score in sorted(scores.items()):
        details = _format_metadata(score.metadata)
        click.echo(f"{name:<25} {score.score:>6.3f}  {details}")

    # Summary
    if scores:
        avg = sum(s.score for s in scores.values()) / len(scores)
        click.echo(f"\n{'Average':<25} {avg:>6.3f}")

    # Write full results if requested
    if output_path:
        out = {
            name: {"score": s.score, "metadata": s.metadata}
            for name, s in sorted(scores.items())
        }
        Path(output_path).write_text(json.dumps(out, indent=2))
        click.echo(f"\nResults written to {output_path}")


def _format_metadata(meta: dict) -> str:
    """Format metadata dict as a compact string for the results table."""
    if not meta:
        return ""
    parts = []
    for k, v in meta.items():
        if k == "raw":
            continue
        if isinstance(v, float):
            parts.append(f"{k}={v:.2f}")
        elif isinstance(v, list) and len(v) > 3:
            parts.append(f"{k}=[{len(v)} items]")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)
