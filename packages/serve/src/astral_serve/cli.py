"""CLI for newsletter delivery via Buttondown."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path

import click

from astral_author import NewsletterDraft
from astral_core import bootstrap

from .buttondown import ButtondownClient, ButtondownError
from .models import PublishRecord, PublishStatus
from .store import (
    NewsletterStore,
    load_staged_meta,
    save_staged_meta,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

STAGING_DIR = Path("issues")


def _resolve_draft(draft_ref: str) -> tuple[NewsletterDraft, str | None, Path | None]:
    """Resolve a draft reference to (NewsletterDraft, markdown_override, staging_dir).

    draft_ref can be:
      - A date string (YYYY-MM-DD) → reads from issues/{date}/
      - A file path → reads the JSON file directly (legacy behavior)

    When reading from staging, markdown comes from draft.md (human-edited),
    while metadata comes from draft.json (machine-generated).
    """
    if _DATE_RE.match(draft_ref):
        staging = STAGING_DIR / draft_ref
        json_path = staging / "draft.json"
        md_path = staging / "draft.md"

        if not json_path.exists():
            raise click.ClickException(f"No staged draft at {json_path}")

        newsletter = NewsletterDraft.model_validate_json(json_path.read_text())

        # Use the human-edited markdown if it exists
        markdown_override = None
        if md_path.exists():
            markdown_override = md_path.read_text()

        return newsletter, markdown_override, staging

    # Legacy: direct file path
    path = Path(draft_ref)
    if not path.exists():
        raise click.ClickException(f"File not found: {path}")
    return NewsletterDraft.model_validate_json(path.read_text()), None, None


@click.group()
def cli() -> None:
    """Astral Index — newsletter delivery."""
    bootstrap()


@cli.command()
@click.argument("draft_ref")
@click.option(
    "--dry-run", is_flag=True, help="Validate and preview without calling Buttondown."
)
def draft(draft_ref: str, dry_run: bool) -> None:
    """Create a Buttondown draft from a date (YYYY-MM-DD) or JSON file path."""
    newsletter, markdown_override, staging = _resolve_draft(draft_ref)
    body = markdown_override or newsletter.markdown

    click.echo(f"Title: {newsletter.title}")
    click.echo(f"Date: {newsletter.issue_date}")
    click.echo(f"Strategy: {newsletter.strategy_name}")
    click.echo(f"Sections: {len(newsletter.sections)}")
    click.echo(f"Words: {newsletter.word_count}")
    if markdown_override:
        click.echo("Body: reading from draft.md (human-edited)")

    if dry_run:
        click.echo(
            "\n[dry-run] Would create Buttondown draft and save to "
            f"data/newsletters/{newsletter.issue_date}/"
        )
        return

    asyncio.run(_create_draft(newsletter, body, staging))


async def _create_draft(
    newsletter: NewsletterDraft,
    body: str,
    staging: Path | None,
) -> None:
    client = ButtondownClient()
    store = NewsletterStore()

    try:
        result = client.create_draft(newsletter.title, body)
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
        store.save(record, markdown=body)
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
    store.save(record, markdown=body)
    click.echo(f"\nDraft created in Buttondown (id: {email_data['id']})")
    click.echo(f"Saved to data/newsletters/{newsletter.issue_date}/")

    # Write publish state to staging dir for the human-in-the-loop workflow
    if staging:
        date_str = str(newsletter.issue_date)
        meta = load_staged_meta(date_str) or {}
        meta.update(
            {
                "buttondown_email_id": email_data["id"],
                "status": "draft",
                "drafted_at": datetime.now(UTC).isoformat(),
            }
        )
        save_staged_meta(date_str, meta)
        click.echo(f"Staging meta updated: {staging / 'meta.json'}")


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

    # Fall back to staging meta if no Buttondown record exists
    if record is None:
        staged = load_staged_meta(issue_date)
        if staged and staged.get("buttondown_email_id"):
            click.echo(
                f"No record in data/newsletters/, but found staging meta "
                f"with Buttondown ID: {staged['buttondown_email_id']}"
            )
            click.echo("Run 'draft' first to create a full publish record.")
            raise SystemExit(1)
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

    asyncio.run(_send(store, record, issue_date))


async def _send(store: NewsletterStore, record: PublishRecord, issue_date: str) -> None:
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

    # Update staging meta
    staged = load_staged_meta(issue_date)
    if staged is not None:
        staged.update(
            {
                "status": "published",
                "published_at": datetime.now(UTC).isoformat(),
            }
        )
        save_staged_meta(issue_date, staged)
        click.echo(f"Staging meta updated: issues/{issue_date}/meta.json")


@cli.command()
@click.argument("issue_date", required=False)
def status(issue_date: str | None) -> None:
    """Show publishing status. Optionally filter by issue date."""
    store = NewsletterStore()

    if issue_date:
        record = store.load(issue_date)

        # Also check staging if no Buttondown record
        staged = load_staged_meta(issue_date)

        if record is None and staged is None:
            click.echo(f"No newsletter found for {issue_date}")
            raise SystemExit(1)

        if record:
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

        if staged:
            click.echo(f"\nStaging:    issues/{issue_date}/")
            click.echo(f"  Status:   {staged.get('status', 'staged')}")
            if staged.get("buttondown_email_id"):
                click.echo(f"  Email ID: {staged['buttondown_email_id']}")
            if staged.get("published_at"):
                click.echo(f"  Published: {staged['published_at']}")

            # Check for draft files
            staging_dir = STAGING_DIR / issue_date
            if (staging_dir / "draft.md").exists():
                click.echo("  draft.md: present")
            if (staging_dir / "draft.json").exists():
                click.echo("  draft.json: present")
        return

    records = store.list_issues()
    if not records:
        click.echo("No newsletters found.")
        return

    click.echo(f"{'Date':<12} {'Status':<8} {'Words':>6}  Title")
    click.echo("-" * 60)
    for r in records:
        click.echo(f"{r.issue_date!s:<12} {r.status:<8} {r.word_count:>6}  {r.title}")
