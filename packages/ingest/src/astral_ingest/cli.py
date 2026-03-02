from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from importlib.resources import files
from typing import Any

import click
import yaml
from dotenv import load_dotenv

from astral_core import ContentItem, ContentStore

from .scrapers.arxiv import ArxivScraper
from .scrapers.bluesky import BlueskyScraper
from .scrapers.reddit import RedditScraper
from .scrapers.rss import RSSFeedScraper
from .scrapers.snapi import SNAPIScraper
from .scrapers.twitter import TwitterScraper


def _load_sources() -> dict[str, Any]:
    source_path = files("astral_ingest").joinpath("sources.yaml")
    return yaml.safe_load(source_path.read_text())


def _save_items(
    items: list[ContentItem],
    store: ContentStore,
    dry_run: bool,
    label_fn: Callable[[ContentItem], str] | None = None,
) -> tuple[int, int]:
    """Save items to store, returning (new, skipped) counts."""
    new = 0
    skipped = 0
    for item in items:
        if not dry_run and store.exists(item.id):
            skipped += 1
            continue
        if dry_run:
            label = label_fn(item) if label_fn else ""
            click.echo(f"\n  [{item.source_name}] {item.title}{label}")
        else:
            store.save(item)
        new += 1
    return new, skipped


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


def _build_arxiv_scrapers(sources: dict[str, Any]) -> list[ArxivScraper]:
    arxiv_cfg = sources.get("arxiv")
    if not arxiv_cfg:
        return []
    return [ArxivScraper(feed, arxiv_cfg) for feed in arxiv_cfg.get("feeds", [])]


def _build_bluesky_scraper(sources: dict[str, Any]) -> BlueskyScraper | None:
    bluesky_cfg = sources.get("bluesky")
    if not bluesky_cfg:
        return None
    return BlueskyScraper(bluesky_cfg)


def _build_twitter_scraper(sources: dict[str, Any]) -> TwitterScraper | None:
    twitter_cfg = sources.get("twitter")
    if not twitter_cfg:
        return None
    return TwitterScraper(twitter_cfg)


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
    """Astral Index — space news ingestion."""
    load_dotenv()


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

    arxiv = cfg.get("arxiv", {})
    if arxiv:
        feeds = ", ".join(f["name"] for f in arxiv.get("feeds", []))
        kw = arxiv.get("keyword_filter", False)
        click.echo(f"\narXiv: {feeds} (keyword_filter={kw})")

    bluesky = cfg.get("bluesky", {})
    if bluesky:
        accounts = ", ".join(f"@{a}" for a in bluesky.get("accounts", []))
        click.echo(f"\nBluesky: {accounts}")

    twitter = cfg.get("twitter", {})
    if twitter:
        accounts = ", ".join(f"@{a}" for a in twitter.get("accounts", []))
        click.echo(f"\nTwitter/X: {accounts} (min_likes={twitter.get('min_likes', 5)})")


@cli.command()
@click.option(
    "--source",
    "source_name",
    default=None,
    help=(
        "Scrape a single source by name. Accepts RSS source names (e.g. "
        '"SpaceNews") or scraper names: snapi, reddit, arxiv, bluesky, twitter.'
    ),
)
@click.option("--dry-run", is_flag=True, help="Print items without saving.")
def scrape(source_name: str | None, dry_run: bool) -> None:
    """Scrape all configured sources (RSS, SNAPI, Reddit, arXiv, Bluesky, Twitter/X)."""
    asyncio.run(_scrape(source_name, dry_run))


def _want(source_name: str | None, *labels: str) -> bool:
    """Return True if no filter is active or the filter matches any label."""
    if not source_name:
        return True
    needle = source_name.lower()
    return any(needle == label.lower() for label in labels)


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
        new, skipped = _save_items(items, store, dry_run)
        click.echo(f"{new} new, {skipped} skipped")
        total_new += new
        total_skipped += skipped

    # SNAPI
    if _want(source_name, "snapi", "spaceflight news api"):
        click.echo("Fetching Spaceflight News API... ", nl=False)
        try:
            items = await _build_snapi_scraper(cfg).fetch()
        except Exception as e:
            click.echo(f"ERROR: {e}")
        else:
            new, skipped = _save_items(items, store, dry_run)
            click.echo(f"{new} new, {skipped} skipped")
            total_new += new
            total_skipped += skipped

    # Reddit
    if _want(source_name, "reddit"):
        reddit = _build_reddit_scraper(cfg)
        if reddit:
            click.echo("Fetching Reddit... ", nl=False)
            try:
                items = await reddit.fetch()
            except Exception as e:
                click.echo(f"ERROR: {e}")
            else:

                def _reddit_label(item: ContentItem) -> str:
                    return f" [score:{item.reddit_score}]" if item.reddit_score else ""

                new, skipped = _save_items(
                    items, store, dry_run, label_fn=_reddit_label
                )
                click.echo(f"{new} new, {skipped} skipped")
                total_new += new
                total_skipped += skipped

    # arXiv
    if _want(source_name, "arxiv"):
        for scraper in _build_arxiv_scrapers(cfg):
            click.echo(f"Fetching arXiv: {scraper.name}... ", nl=False)
            try:
                items = await scraper.fetch()
            except Exception as e:
                click.echo(f"ERROR: {e}")
                continue
            new, skipped = _save_items(items, store, dry_run)
            click.echo(f"{new} new, {skipped} skipped")
            total_new += new
            total_skipped += skipped

    # Bluesky
    if _want(source_name, "bluesky"):
        bluesky = _build_bluesky_scraper(cfg)
        if bluesky:
            click.echo("Fetching Bluesky... ", nl=False)
            try:
                items = await bluesky.fetch()
            except Exception as e:
                click.echo(f"ERROR: {e}")
            else:

                def _bluesky_label(item: ContentItem) -> str:
                    handle = item.social_author_handle
                    return f" [@{handle}]" if handle else ""

                new, skipped = _save_items(
                    items, store, dry_run, label_fn=_bluesky_label
                )
                click.echo(f"{new} new, {skipped} skipped")
                total_new += new
                total_skipped += skipped

    # Twitter/X
    if _want(source_name, "twitter", "twitter/x"):
        twitter = _build_twitter_scraper(cfg)
        if twitter:
            click.echo("Fetching Twitter/X... ", nl=False)
            try:
                items = await twitter.fetch()
            except Exception as e:
                click.echo(f"ERROR: {e}")
            else:

                def _twitter_label(item: ContentItem) -> str:
                    eng = (
                        f" [eng:{item.tweet_engagement}]"
                        if item.tweet_engagement
                        else ""
                    )
                    return eng

                new, skipped = _save_items(
                    items, store, dry_run, label_fn=_twitter_label
                )
                click.echo(f"{new} new, {skipped} skipped")
                total_new += new
                total_skipped += skipped

    click.echo(f"\nDone: {total_new} new items, {total_skipped} skipped")


@cli.command()
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
@click.option("--js", is_flag=True, help="Enable Playwright JS rendering fallback.")
@click.option("--concurrency", default=5, type=int, help="Max concurrent requests.")
@click.option("--dry-run", is_flag=True, help="Print candidates without expanding.")
def expand(
    since: datetime, before: datetime | None, js: bool, concurrency: int, dry_run: bool
) -> None:
    """Expand excerpt-only items by fetching full article text."""
    asyncio.run(_expand(since, before, js, concurrency, dry_run))


async def _expand(
    since: datetime,
    before: datetime | None,
    use_js: bool,
    concurrency: int,
    dry_run: bool,
) -> None:
    from .expand import expand_items

    store = ContentStore()
    all_items = store.list_items(since=since, before=before)

    # Find items that need expansion: no body_text and never expanded
    candidates = [
        item
        for item in all_items
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

    with click.progressbar(
        length=len(candidates), label="Expanding", show_pos=True
    ) as bar:
        expanded = await expand_items(
            candidates,
            store,
            concurrency=concurrency,
            use_js=use_js,
            on_progress=lambda: bar.update(1),
        )

    click.echo(f"\nExpanded {len(expanded)}/{len(candidates)} items")
    for item in expanded:
        method = item.extraction_method or "unknown"
        pw = " [paywalled]" if item.is_paywalled else ""
        click.echo(f"  [{method}] {item.title} ({item.word_count}w){pw}")


@cli.command()
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
@click.option("--llm/--no-llm", default=True, help="Enable LLM fallback.")
@click.option("--dry-run", is_flag=True, help="Print results without saving.")
def classify(
    since: datetime, before: datetime | None, llm: bool, dry_run: bool
) -> None:
    """Classify uncategorized items using keywords + optional LLM."""
    asyncio.run(_classify(since, before, llm, dry_run))


async def _classify(
    since: datetime, before: datetime | None, use_llm: bool, dry_run: bool
) -> None:
    from .classify.keywords import classify_by_keywords
    from .classify.llm import classify_batch_with_llm

    store = ContentStore()
    all_items = store.list_items(since=since, before=before)

    # Find items with no categories
    uncategorized = [item for item in all_items if not item.categories]

    if not uncategorized:
        click.echo("No uncategorized items found.")
        return

    click.echo(f"Found {len(uncategorized)} uncategorized items")

    # Pass 1: keyword classification
    keyword_classified = 0
    still_uncategorized = []

    with click.progressbar(
        uncategorized, label="Pass 1 (keywords)", show_pos=True
    ) as bar:
        for item in bar:
            cats = classify_by_keywords(item.title, item.body_text or item.excerpt)
            if cats:
                keyword_classified += 1
                if dry_run:
                    labels = ", ".join(c.value for c in cats)
                    click.echo(f"  [keywords] {item.title[:60]}... -> {labels}")
                else:
                    item.categories = cats
                    store.save(item)
            else:
                still_uncategorized.append(item)

    click.echo(f"Pass 1 (keywords): {keyword_classified} classified")

    # Pass 2: LLM fallback
    llm_classified = 0
    if use_llm and still_uncategorized:
        with click.progressbar(
            length=len(still_uncategorized),
            label="Pass 2 (LLM)    ",
            show_pos=True,
        ) as bar:
            batch = [
                (item.title, item.body_text or item.excerpt)
                for item in still_uncategorized
            ]
            results = await classify_batch_with_llm(
                batch, on_progress=lambda: bar.update(1)
            )

        for item, cat in zip(still_uncategorized, results, strict=True):
            if cat:
                llm_classified += 1
                if dry_run:
                    click.echo(f"  [llm] {item.title[:60]}... -> {cat.value}")
                else:
                    item.categories = [cat]
                    store.save(item)
        click.echo(f"Pass 2 (LLM): {llm_classified} classified")
    elif still_uncategorized:
        click.echo(
            f"{len(still_uncategorized)} items remain uncategorized"
            " (use --llm to enable LLM fallback)"
        )

    total = keyword_classified + llm_classified
    action = "would classify" if dry_run else "classified"
    click.echo(f"\nDone: {action} {total}/{len(uncategorized)} items")


@cli.command()
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
@click.option("--source", "source_name", default=None, help="Filter by source name.")
@click.option(
    "--format",
    "fmt",
    default="markdown",
    type=click.Choice(["markdown", "json"]),
    help="Output format.",
)
def export(
    since: datetime, before: datetime | None, source_name: str | None, fmt: str
) -> None:
    """Export stored items as markdown or JSON."""
    store = ContentStore()
    items = store.list_items(since=since, before=before, source_name=source_name)

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
        click.echo(f"# Space News Digest ({_describe_range(since, before)})\n")
        current_source = None
        for item in sorted(
            items, key=lambda i: (i.source_name, i.published_at or i.scraped_at)
        ):
            if item.source_name != current_source:
                current_source = item.source_name
                click.echo(f"\n## {current_source}\n")
            date_str = ""
            if item.published_at:
                date_str = item.published_at.strftime("%Y-%m-%d")
            click.echo(f"- **{item.title}** ({date_str})")
            click.echo(f"  {item.source_url}")
            if item.excerpt:
                short = (
                    item.excerpt[:200] + "..."
                    if len(item.excerpt) > 200
                    else item.excerpt
                )
                click.echo(f"  > {short}")
            click.echo()
