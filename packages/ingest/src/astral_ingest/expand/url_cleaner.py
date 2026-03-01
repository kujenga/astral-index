"""URL cleaning: normalization + short-URL expansion."""

from __future__ import annotations

import logging

import httpx
from astral_core import normalize_url

from ..scrapers.base import make_http_client

logger = logging.getLogger(__name__)

# Domains that host shortened/redirect URLs
_SHORT_DOMAINS = frozenset({
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly",
    "is.gd", "buff.ly", "dlvr.it", "j.mp", "lnkd.in",
})


def _is_short_url(url: str) -> bool:
    """Check if a URL is from a known shortener domain."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        return host in _SHORT_DOMAINS
    except Exception:
        return False


async def clean_url(url: str) -> str:
    """Normalize a URL and expand it if it's a known short URL.

    Strips tracking params via normalize_url(), then follows redirects
    on short URLs via a HEAD request to get the final destination.
    """
    url = normalize_url(url)

    if not _is_short_url(url):
        return url

    try:
        async with make_http_client() as client:
            resp = await client.head(url, follow_redirects=True)
            expanded = str(resp.url)
            logger.debug("Expanded %s -> %s", url, expanded)
            return normalize_url(expanded)
    except httpx.HTTPError as e:
        logger.warning("Failed to expand short URL %s: %s", url, e)
        return url
