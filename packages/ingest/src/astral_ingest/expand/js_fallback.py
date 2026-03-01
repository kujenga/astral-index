"""JavaScript-rendered page fetching via Playwright (optional dependency)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def fetch_js_rendered(url: str, timeout_ms: int = 30_000) -> str | None:
    """Fetch a page using headless Chromium. Returns HTML or None.

    Requires playwright (`pip install playwright` + `playwright install chromium`).
    Returns None gracefully if Playwright isn't available.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.debug("Playwright not installed, skipping JS rendering")
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = await page.content()
            await browser.close()
            return html
    except Exception:
        logger.exception("Playwright rendering failed for %s", url)
        return None
