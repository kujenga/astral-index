"""CLI for the newsletter quality evaluation pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import click

from astral_author.models import NewsletterDraft
from astral_author.pipeline import STRATEGIES, build_strategy
from astral_core import ContentStore, bootstrap

from .runner import run_quality_eval

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# experiment command
# ---------------------------------------------------------------------------


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
    "--experiment-name",
    default=None,
    type=str,
    help="Braintrust experiment name (default: {strategy}-{date}).",
)
@click.option(
    "--dataset",
    "dataset_name",
    default=None,
    type=str,
    help="Braintrust dataset name to use as input.",
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
def experiment(
    since: datetime,
    strategy_name: str,
    experiment_name: str | None,
    dataset_name: str | None,
    max_items: int,
    no_llm: bool,
) -> None:
    """Run a Braintrust-tracked eval experiment."""
    asyncio.run(
        _experiment(
            since,
            strategy_name,
            experiment_name,
            dataset_name,
            max_items,
            no_llm,
        )
    )


async def _experiment(
    since: datetime,
    strategy_name: str,
    experiment_name: str | None,
    dataset_name: str | None,
    max_items: int,
    no_llm: bool,
) -> None:
    from .experiment import run_experiment

    # Load local items (needed even with dataset, for item count display)
    items: list = []
    if not dataset_name:
        store = ContentStore()
        items = store.list_items(since=since)
        if not items:
            click.echo("No items found.")
            return
        click.echo(f"Found {len(items)} items (since {since.strftime('%Y-%m-%d')})")

    result = await run_experiment(
        strategy_name,
        items,
        experiment_name=experiment_name,
        max_items=max_items,
        use_llm=not no_llm,
        dataset_name=dataset_name,
    )

    if result.get("tracked"):
        click.echo(f"Experiment '{result['experiment_name']}' logged to Braintrust")
    else:
        exp = result["experiment_name"]
        click.secho(
            f"WARNING: Braintrust not active — experiment "
            f"'{exp}' running locally only. Set "
            "BRAINTRUST_API_KEY and install braintrust "
            "to enable experiment tracking.",
            fg="yellow",
            err=True,
        )
        scores = result.get("scores", {})
        if scores:
            click.echo(f"\n{'Scorer':<25} {'Score':>6}  {'Details'}")
            click.echo("-" * 65)
            for name, score in sorted(scores.items()):
                details = _format_metadata(score.metadata)
                click.echo(f"{name:<25} {score.score:>6.3f}  {details}")
            avg = sum(s.score for s in scores.values()) / len(scores)
            click.echo(f"\n{'Average':<25} {avg:>6.3f}")


# ---------------------------------------------------------------------------
# compare command
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--since",
    default="7",
    type=str,
    callback=_parse_since,
    help="Days back (integer) or start date (YYYY-MM-DD).",
)
@click.option(
    "--dataset",
    "dataset_name",
    default=None,
    type=str,
    help="Braintrust dataset name to use as input.",
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
@click.argument("strategies", nargs=-1, required=True)
def compare(
    since: datetime,
    dataset_name: str | None,
    max_items: int,
    no_llm: bool,
    strategies: tuple[str, ...],
) -> None:
    """Run multiple strategies as separate experiments for comparison.

    Pass strategy names as arguments, e.g.: astral-eval compare baseline headlines-only
    """
    asyncio.run(_compare(since, dataset_name, max_items, no_llm, strategies))


async def _compare(
    since: datetime,
    dataset_name: str | None,
    max_items: int,
    no_llm: bool,
    strategies: tuple[str, ...],
) -> None:
    from .experiment import run_experiment

    store = ContentStore()
    items = store.list_items(since=since) if not dataset_name else []

    if not dataset_name and not items:
        click.echo("No items found.")
        return

    if not dataset_name:
        click.echo(f"Found {len(items)} items (since {since.strftime('%Y-%m-%d')})")

    # One-time warning if Braintrust is not available
    import os

    from .experiment import _braintrust_available

    if not _braintrust_available() or not os.environ.get("BRAINTRUST_API_KEY"):
        click.secho(
            "WARNING: Braintrust not active — comparisons "
            "will run locally only. Set BRAINTRUST_API_KEY "
            "and install braintrust to enable dashboard "
            "comparison.",
            fg="yellow",
            err=True,
        )

    for strategy_name in strategies:
        if strategy_name not in STRATEGIES:
            click.echo(f"Unknown strategy: {strategy_name}", err=True)
            continue

        click.echo(f"\n--- {strategy_name} ---")
        result = await run_experiment(
            strategy_name,
            items,
            max_items=max_items,
            use_llm=not no_llm,
            dataset_name=dataset_name,
        )

        if result.get("tracked"):
            click.echo(f"Logged to Braintrust as '{result['experiment_name']}'")
        else:
            scores = result.get("scores", {})
            if scores:
                for name, score in sorted(scores.items()):
                    click.echo(f"  {name:<23} {score.score:.3f}")
                avg = sum(s.score for s in scores.values()) / len(scores)
                click.echo(f"  {'Average':<23} {avg:.3f}")


# ---------------------------------------------------------------------------
# upload-dataset command
# ---------------------------------------------------------------------------


@cli.command("upload-dataset")
@click.option(
    "--since",
    required=True,
    type=str,
    callback=_parse_since,
    help="Start date (YYYY-MM-DD) or days back (integer).",
)
@click.option(
    "--until",
    default=None,
    type=str,
    callback=_parse_since,
    is_eager=False,
    help="End date (YYYY-MM-DD) or days back (integer).",
)
@click.option(
    "--name",
    "dataset_name",
    required=True,
    type=str,
    help="Braintrust dataset name.",
)
def upload_dataset(
    since: datetime,
    until: datetime | None,
    dataset_name: str,
) -> None:
    """Upload a golden-week dataset to Braintrust for reproducible evals."""
    from .datasets import upload_golden_week

    result = upload_golden_week(
        since=since,
        until=until,
        dataset_name=dataset_name,
    )

    click.echo(f"Uploaded dataset '{result['dataset_name']}'")
    click.echo(f"  Items: {result['item_count']}")
    click.echo(f"  Date range: {result['date_range']}")
    click.echo(f"  Categories: {result['categories']}")


# ---------------------------------------------------------------------------
# seed-prompts command
# ---------------------------------------------------------------------------


@cli.command("seed-prompts")
@click.option("--dry-run", is_flag=True, help="Show prompts without pushing.")
def seed_prompts_cmd(dry_run: bool) -> None:
    """Push hardcoded prompts to Braintrust as initial versions."""
    from .seed_prompts import seed_prompts

    seeded = seed_prompts(dry_run=dry_run)

    if dry_run:
        click.echo("Dry run — would seed:")
    else:
        click.echo("Seeded prompts:")
    for slug in seeded:
        click.echo(f"  {slug}")


# ---------------------------------------------------------------------------
# score command
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("draft_file", type=click.Path(exists=True))
@click.option(
    "--since",
    default="7",
    type=str,
    callback=_parse_since,
    help="Days back (integer) or start date (YYYY-MM-DD) for input items.",
)
def score(draft_file: str, since: datetime) -> None:
    """Score an existing draft JSON file with heuristic scorers.

    Results are printed and optionally logged to Braintrust.
    """
    from astral_core.scoring import HEURISTIC_SCORERS

    raw = Path(draft_file).read_text()
    draft = NewsletterDraft.model_validate_json(raw)
    click.echo(f"Loaded draft from {draft_file}")

    store = ContentStore()
    items = store.list_items(since=since)
    click.echo(f"Found {len(items)} input items")

    output = draft.model_dump(mode="json")
    input_data = [item.model_dump(mode="json") for item in items]

    click.echo(f"\n{'Scorer':<25} {'Score':>6}  {'Details'}")
    click.echo("-" * 65)

    bt_scores: dict[str, float] = {}
    for scorer in HEURISTIC_SCORERS:
        result = scorer(output=output, input=input_data)
        if result is not None:
            details = _format_metadata(result.metadata)
            click.echo(f"{result.name:<25} {result.score:>6.3f}  {details}")
            bt_scores[result.name] = result.score

    if bt_scores:
        avg = sum(bt_scores.values()) / len(bt_scores)
        click.echo(f"\n{'Average':<25} {avg:>6.3f}")

    # Log to Braintrust if available
    try:
        import os

        import braintrust

        if os.environ.get("BRAINTRUST_API_KEY"):
            bt_logger = braintrust.init_logger(project="astral-index")
            bt_logger.log(
                input={"draft_file": draft_file, "since": since.isoformat()},
                scores=bt_scores,
            )
            click.echo("\nScores logged to Braintrust")
    except Exception:
        pass
