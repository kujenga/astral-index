"""Link expansion pipeline orchestrator.

Fetches HTML for items missing body_text, runs the extraction cascade,
and saves updated items back to the store.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from astral_core import ContentItem, ContentStore, ExtractionMethod

from ..scrapers.base import make_http_client
from .extractor import extract_from_html
from .js_fallback import fetch_js_rendered
from .paywall import is_paywalled
from .pdf_extract import extract_from_pdf
from .rate_limiter import DomainRateLimiter
from .url_cleaner import clean_url

logger = logging.getLogger(__name__)


async def expand_item(
    item: ContentItem,
    *,
    rate_limiter: DomainRateLimiter,
    client: httpx.AsyncClient,
    use_js: bool = False,
) -> ContentItem | None:
    """Fetch and extract full text for a single item.

    Returns an updated ContentItem on success, or None if extraction fails.
    """
    url = item.canonical_url or item.source_url
    url = await clean_url(url)

    await rate_limiter.acquire(url)

    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None

    content_type = resp.headers.get("content-type", "")

    # PDF handling
    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        result = extract_from_pdf(resp.content)
        if result:
            return item.model_copy(
                update={
                    "body_text": result.text,
                    "word_count": result.word_count,
                    "extraction_method": result.method,
                    "expanded_at": datetime.now(UTC),
                    "is_paywalled": is_paywalled(result.text),
                }
            )
        return None

    # HTML extraction
    html = resp.text
    result = extract_from_html(html, url)

    # JS fallback if enabled and initial extraction failed
    if not result and use_js:
        logger.debug("Trying JS rendering for %s", url)
        js_html = await fetch_js_rendered(url)
        if js_html:
            result = extract_from_html(js_html, url)
            if result:
                # Override method to reflect JS rendering was needed
                result.method = ExtractionMethod.PLAYWRIGHT

    if not result:
        logger.debug("All extraction methods failed for %s", url)
        return None

    return item.model_copy(
        update={
            "body_text": result.text,
            "word_count": result.word_count,
            "excerpt": result.text[:500] if len(result.text) > 500 else result.text,
            "extraction_method": result.method,
            "expanded_at": datetime.now(UTC),
            "is_paywalled": is_paywalled(result.text),
        }
    )


async def expand_items(
    items: list[ContentItem],
    store: ContentStore,
    *,
    concurrency: int = 5,
    use_js: bool = False,
    dry_run: bool = False,
    on_progress: Callable[[], None] | None = None,
) -> list[ContentItem]:
    """Expand multiple items with bounded concurrency.

    Returns the list of successfully expanded items.
    """
    semaphore = asyncio.Semaphore(concurrency)
    rate_limiter = DomainRateLimiter()
    expanded: list[ContentItem] = []

    async def _process(item: ContentItem, client: httpx.AsyncClient) -> None:
        async with semaphore:
            result = await expand_item(
                item,
                rate_limiter=rate_limiter,
                client=client,
                use_js=use_js,
            )
            if result:
                if not dry_run:
                    store.save(result)
                expanded.append(result)
            if on_progress:
                on_progress()

    async with make_http_client() as client:
        tasks = [asyncio.create_task(_process(item, client)) for item in items]
        await asyncio.gather(*tasks)

    return expanded
