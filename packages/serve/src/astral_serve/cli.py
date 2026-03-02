"""CLI for newsletter delivery via Buttondown."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import click
from dotenv import load_dotenv

from astral_author import NewsletterDraft

from .buttondown import ButtondownClient, ButtondownError
from .models import PublishRecord, PublishStatus
from .store import NewsletterStore


@click.group()
def cli() -> None:
    """Astral Index — newsletter delivery."""
    load_dotenv()


@cli.command()
@click.argument("draft_path", type=click.Path(exists=True))
@click.option(
    "--dry-run", is_flag=True, help="Validate and preview without calling Buttondown."
)
def draft(draft_path: str, dry_run: bool) -> None:
    """Create a Buttondown draft from a NewsletterDraft JSON file."""
    raw = Path(draft_path).read_text()
    newsletter = NewsletterDraft.model_validate_json(raw)

    click.echo(f"Title: {newsletter.title}")
    click.echo(f"Date: {newsletter.issue_date}")
    click.echo(f"Strategy: {newsletter.strategy_name}")
    click.echo(f"Sections: {len(newsletter.sections)}")
    click.echo(f"Words: {newsletter.word_count}")

    if dry_run:
        click.echo(
            "\n[dry-run] Would create Buttondown draft and save to "
            f"data/newsletters/{newsletter.issue_date}/"
        )
        return

    asyncio.run(_create_draft(newsletter))


async def _create_draft(newsletter: NewsletterDraft) -> None:
    client = ButtondownClient()
    store = NewsletterStore()

    try:
        result = client.create_draft(newsletter.title, newsletter.markdown)
        email_data = await result
    except ButtondownError as e:
        record = PublishRecord(
            issue_date=newsletter.issue_date,
            title=newsletter.title,
            status=PublishStatus.FAILED,
            created_at=datetime.now(UTC),
            strategy_name=newsletter.strategy_name,
            model_used=newsletter.model_used,
            word_count=newsletter.word_count,
            error_message=str(e),
        )
        store.save(record, markdown=newsletter.markdown)
        click.echo(f"Failed: {e}")
        raise SystemExit(1) from None

    record = PublishRecord(
        issue_date=newsletter.issue_date,
        title=newsletter.title,
        status=PublishStatus.DRAFT,
        buttondown_email_id=email_data["id"],
        created_at=datetime.now(UTC),
        strategy_name=newsletter.strategy_name,
        model_used=newsletter.model_used,
        word_count=newsletter.word_count,
    )
    store.save(record, markdown=newsletter.markdown)
    click.echo(f"\nDraft created in Buttondown (id: {email_data['id']})")
    click.echo(f"Saved to data/newsletters/{newsletter.issue_date}/")


@cli.command("send")
@click.argument("issue_date")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be sent without calling Buttondown.",
)
def send_cmd(issue_date: str, dry_run: bool) -> None:
    """Send a previously drafted newsletter by issue date (YYYY-MM-DD)."""
    store = NewsletterStore()
    record = store.load(issue_date)

    if record is None:
        click.echo(f"No newsletter found for {issue_date}")
        raise SystemExit(1)

    if record.status == PublishStatus.SENT:
        click.echo(f"Already sent on {record.sent_at}")
        return

    if not record.buttondown_email_id:
        click.echo(
            "No Buttondown email ID — draft may have failed. Re-run 'draft' first."
        )
        raise SystemExit(1)

    click.echo(f"Title: {record.title}")
    click.echo(f"Buttondown ID: {record.buttondown_email_id}")

    if dry_run:
        click.echo("\n[dry-run] Would send this newsletter via Buttondown.")
        return

    asyncio.run(_send(store, record))


async def _send(store: NewsletterStore, record: PublishRecord) -> None:
    client = ButtondownClient()

    try:
        await client.send_email(record.buttondown_email_id)  # type: ignore[arg-type]
    except ButtondownError as e:
        record.status = PublishStatus.FAILED
        record.error_message = str(e)
        store.save(record)
        click.echo(f"Failed: {e}")
        raise SystemExit(1) from None

    record.status = PublishStatus.SENT
    record.sent_at = datetime.now(UTC)
    store.save(record)
    click.echo("Sent successfully.")


@cli.command()
@click.argument("issue_date", required=False)
def status(issue_date: str | None) -> None:
    """Show publishing status. Optionally filter by issue date."""
    store = NewsletterStore()

    if issue_date:
        record = store.load(issue_date)
        if record is None:
            click.echo(f"No newsletter found for {issue_date}")
            raise SystemExit(1)

        click.echo(f"Date:       {record.issue_date}")
        click.echo(f"Title:      {record.title}")
        click.echo(f"Status:     {record.status}")
        click.echo(f"Strategy:   {record.strategy_name}")
        click.echo(f"Model:      {record.model_used or '(none)'}")
        click.echo(f"Words:      {record.word_count}")
        click.echo(f"Created:    {record.created_at}")
        if record.sent_at:
            click.echo(f"Sent:       {record.sent_at}")
        if record.buttondown_email_id:
            click.echo(f"Email ID:   {record.buttondown_email_id}")
        if record.error_message:
            click.echo(f"Error:      {record.error_message}")
        return

    records = store.list_issues()
    if not records:
        click.echo("No newsletters found.")
        return

    click.echo(f"{'Date':<12} {'Status':<8} {'Words':>6}  Title")
    click.echo("-" * 60)
    for r in records:
        click.echo(f"{r.issue_date!s:<12} {r.status:<8} {r.word_count:>6}  {r.title}")
