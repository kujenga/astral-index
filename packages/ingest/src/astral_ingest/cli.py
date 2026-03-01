from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from typing import Any

import click
import yaml
from astral_core import ContentStore

from .scrapers.reddit import RedditScraper
from .scrapers.rss import RSSFeedScraper
from .scrapers.snapi import SNAPIScraper


def _load_sources() -> dict[str, Any]:
    source_path = files("astral_ingest").joinpath("sources.yaml")
    return yaml.safe_load(source_path.read_text())


def _build_rss_scrapers(
    sources: dict[str, Any],
    source_filter: str | None = None,
) -> list[RSSFeedScraper]:
    scrapers = []
    for src in sources.get("rss_sources", []):
        if source_filter and src["name"].lower() != source_filter.lower():
            continue
        scrapers.append(RSSFeedScraper(src))
    return scrapers


def _build_snapi_scraper(
    sources: dict[str, Any],
    since: datetime | None = None,
) -> SNAPIScraper:
    snapi_cfg = sources.get("snapi", {})
    return SNAPIScraper(
        base_url=snapi_cfg.get("base_url", "https://api.spaceflightnewsapi.net/v4"),
        endpoints=snapi_cfg.get("endpoints", ["/articles/", "/blogs/"]),
        since=since,
    )


def _build_reddit_scraper(sources: dict[str, Any]) -> RedditScraper | None:
    reddit_cfg = sources.get("reddit")
    if not reddit_cfg:
        return None
    return RedditScraper(reddit_cfg)


@click.group()
def cli() -> None:
    """Astral Index — space news ingestion."""


@cli.command()
def sources() -> None:
    """List all configured sources."""
    cfg = _load_sources()
    click.echo("RSS Sources:")
    for src in cfg.get("rss_sources", []):
        paywalled = " [paywalled]" if src.get("is_paywalled") else ""
        cats = ", ".join(src.get("category_hints", []))
        click.echo(f"  {src['name']:<30} {src['content_type']:<10} {cats}{paywalled}")

    snapi = cfg.get("snapi", {})
    if snapi:
        endpoints = ", ".join(snapi.get("endpoints", []))
        click.echo(f"\nSpaceflight News API: {snapi.get('base_url', '')} ({endpoints})")

    reddit = cfg.get("reddit", {})
    if reddit:
        subs = ", ".join(f"r/{s}" for s in reddit.get("subreddits", []))
        click.echo(f"\nReddit: {subs} (score >= {reddit.get('score_threshold', 50)})")


@cli.command()
@click.option("--source", "source_name", default=None, help="Scrape a single source by name.")
@click.option("--dry-run", is_flag=True, help="Print items without saving.")
def scrape(source_name: str | None, dry_run: bool) -> None:
    """Scrape RSS feeds, Spaceflight News API, and Reddit."""
    asyncio.run(_scrape(source_name, dry_run))


async def _scrape(source_name: str | None, dry_run: bool) -> None:
    cfg = _load_sources()
    store = ContentStore()
    total_new = 0
    total_skipped = 0

    # RSS feeds
    scrapers = _build_rss_scrapers(cfg, source_name)
    for scraper in scrapers:
        click.echo(f"Fetching {scraper.name}... ", nl=False)
        try:
            items = await scraper.fetch()
        except Exception as e:
            click.echo(f"ERROR: {e}")
            continue

        new = 0
        skipped = 0
        for item in items:
            if not dry_run and store.exists(item.id):
                skipped += 1
                continue
            if dry_run:
                click.echo(f"\n  [{item.source_name}] {item.title}")
            else:
                store.save(item)
            new += 1

        click.echo(f"{new} new, {skipped} skipped")
        total_new += new
        total_skipped += skipped

    # SNAPI (skip if filtering to a specific RSS source)
    if not source_name:
        click.echo("Fetching Spaceflight News API... ", nl=False)
        try:
            snapi = _build_snapi_scraper(cfg)
            items = await snapi.fetch()
        except Exception as e:
            click.echo(f"ERROR: {e}")
        else:
            new = 0
            skipped = 0
            for item in items:
                if not dry_run and store.exists(item.id):
                    skipped += 1
                    continue
                if dry_run:
                    click.echo(f"\n  [{item.source_name}] {item.title}")
                else:
                    store.save(item)
                new += 1
            click.echo(f"{new} new, {skipped} skipped")
            total_new += new
            total_skipped += skipped

    # Reddit (skip if filtering to a specific RSS source)
    if not source_name:
        reddit = _build_reddit_scraper(cfg)
        if reddit:
            click.echo("Fetching Reddit... ", nl=False)
            try:
                items = await reddit.fetch()
            except Exception as e:
                click.echo(f"ERROR: {e}")
            else:
                new = 0
                skipped = 0
                for item in items:
                    if not dry_run and store.exists(item.id):
                        skipped += 1
                        continue
                    if dry_run:
                        score = f" [score:{item.reddit_score}]" if item.reddit_score else ""
                        click.echo(f"\n  [{item.source_name}] {item.title}{score}")
                    else:
                        store.save(item)
                    new += 1
                click.echo(f"{new} new, {skipped} skipped")
                total_new += new
                total_skipped += skipped

    click.echo(f"\nDone: {total_new} new items, {total_skipped} skipped")


@cli.command()
@click.option("--since", "since_days", default=7, type=int, help="Days to look back.")
@click.option("--js", is_flag=True, help="Enable Playwright JS rendering fallback.")
@click.option("--concurrency", default=5, type=int, help="Max concurrent requests.")
@click.option("--dry-run", is_flag=True, help="Print candidates without expanding.")
def expand(since_days: int, js: bool, concurrency: int, dry_run: bool) -> None:
    """Expand excerpt-only items by fetching full article text."""
    asyncio.run(_expand(since_days, js, concurrency, dry_run))


async def _expand(since_days: int, use_js: bool, concurrency: int, dry_run: bool) -> None:
    from .expand import expand_items

    store = ContentStore()
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    all_items = store.list_items(since=since)

    # Find items that need expansion: no body_text and never expanded
    candidates = [
        item for item in all_items
        if item.body_text is None and item.expanded_at is None
    ]

    if not candidates:
        click.echo("No items need expansion.")
        return

    click.echo(f"Found {len(candidates)} items to expand")

    if dry_run:
        for item in candidates:
            url = item.canonical_url or item.source_url
            click.echo(f"  [{item.source_name}] {item.title}")
            click.echo(f"    {url}")
        click.echo(f"\n{len(candidates)} items would be expanded (dry run)")
        return

    expanded = await expand_items(
        candidates, store, concurrency=concurrency, use_js=use_js,
    )

    click.echo(f"\nExpanded {len(expanded)}/{len(candidates)} items")
    for item in expanded:
        method = item.extraction_method or "unknown"
        pw = " [paywalled]" if item.is_paywalled else ""
        click.echo(f"  [{method}] {item.title} ({item.word_count}w){pw}")


@cli.command()
@click.option("--since", "since_days", default=7, type=int, help="Days to look back.")
@click.option("--source", "source_name", default=None, help="Filter by source name.")
@click.option(
    "--format",
    "fmt",
    default="markdown",
    type=click.Choice(["markdown", "json"]),
    help="Output format.",
)
def export(since_days: int, source_name: str | None, fmt: str) -> None:
    """Export stored items as markdown or JSON."""
    store = ContentStore()
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    items = store.list_items(since=since, source_name=source_name)

    if not items:
        click.echo("No items found.")
        return

    if fmt == "json":
        click.echo("[")
        for i, item in enumerate(items):
            comma = "," if i < len(items) - 1 else ""
            click.echo(f"  {item.model_dump_json()}{comma}")
        click.echo("]")
    else:
        click.echo(f"# Space News Digest ({since_days}d)\n")
        current_source = None
        for item in sorted(items, key=lambda i: (i.source_name, i.published_at or i.scraped_at)):
            if item.source_name != current_source:
                current_source = item.source_name
                click.echo(f"\n## {current_source}\n")
            date_str = ""
            if item.published_at:
                date_str = item.published_at.strftime("%Y-%m-%d")
            click.echo(f"- **{item.title}** ({date_str})")
            click.echo(f"  {item.source_url}")
            if item.excerpt:
                short = item.excerpt[:200] + "..." if len(item.excerpt) > 200 else item.excerpt
                click.echo(f"  > {short}")
            click.echo()
