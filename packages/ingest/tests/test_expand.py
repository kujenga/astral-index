"""Integration tests for the expansion pipeline.

Covers: extractor cascade, URL cleaner, pipeline orchestration,
and graceful degradation when optional deps are missing.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx

from astral_core import ExtractionMethod
from astral_ingest.expand.extractor import extract_from_html
from astral_ingest.expand.pipeline import expand_item, expand_items
from astral_ingest.expand.rate_limiter import DomainRateLimiter
from astral_ingest.expand.url_cleaner import clean_url

# ---------------------------------------------------------------------------
# Extractor cascade
# ---------------------------------------------------------------------------


class TestExtractorCascade:
    def test_extracts_from_html(self, canned):
        result = extract_from_html(
            canned.sample_html_article, "https://example.com/article"
        )
        assert result is not None
        assert result.word_count >= 50
        assert result.method in (
            ExtractionMethod.TRAFILATURA,
            ExtractionMethod.NEWSPAPER,
            ExtractionMethod.READABILITY,
        )

    def test_returns_none_on_empty_html(self):
        result = extract_from_html("", "https://example.com")
        assert result is None

    def test_respects_min_word_threshold(self):
        short_html = "<html><body><p>Too short.</p></body></html>"
        result = extract_from_html(short_html, "https://example.com")
        assert result is None


# ---------------------------------------------------------------------------
# URL cleaner
# ---------------------------------------------------------------------------


class TestURLCleaner:
    async def test_normalizes_tracking_params(self):
        url = "https://spacenews.com/article?utm_source=twitter&utm_medium=social"
        result = await clean_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert result == "https://spacenews.com/article"

    async def test_short_url_triggers_head_request(self, patch_http):
        """Short URLs make an HTTP HEAD request to resolve."""
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.method)
            return httpx.Response(200)

        patch_http(handler)
        await clean_url("https://bit.ly/abc123")
        # Verify a HEAD request was made for the short URL
        assert "HEAD" in calls

    async def test_non_short_url_skips_http(self, patch_http):
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200)

        patch_http(handler)
        result = await clean_url("https://spacenews.com/article")
        # No HTTP call for non-short URLs
        assert calls == []
        assert result == "https://spacenews.com/article"


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


class TestExpandPipeline:
    async def test_expand_item_sets_fields(self, patch_http, make_item, canned):
        """Mocked HTML fetch → extract → updated ContentItem."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=canned.sample_html_article,
                headers={"content-type": "text/html"},
            )

        patch_http(handler)

        item = make_item(
            body_text=None,
            canonical_url="https://spacenews.com/article",
        )
        rate_limiter = DomainRateLimiter(delay=0)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await expand_item(item, rate_limiter=rate_limiter, client=client)

        assert result is not None
        assert result.body_text is not None
        assert result.word_count is not None
        assert result.word_count >= 50
        assert result.extraction_method is not None
        assert result.expanded_at is not None

    async def test_expand_item_http_404_returns_none(self, patch_http, make_item):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        patch_http(handler)

        item = make_item(
            body_text=None,
            canonical_url="https://spacenews.com/gone",
        )
        rate_limiter = DomainRateLimiter(delay=0)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await expand_item(item, rate_limiter=rate_limiter, client=client)

        assert result is None

    async def test_expand_items_saves_to_store(
        self, patch_http, tmp_store, make_item, canned
    ):
        """expand_items persists results to ContentStore."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=canned.sample_html_article,
                headers={"content-type": "text/html"},
            )

        patch_http(handler)

        item = make_item(
            body_text=None,
            canonical_url="https://spacenews.com/article",
        )

        results = await expand_items([item], tmp_store, concurrency=1)

        assert len(results) == 1
        assert tmp_store.exists(results[0].id)

    async def test_expand_items_dry_run_no_save(
        self, patch_http, tmp_store, make_item, canned
    ):
        """dry_run=True does not persist to store."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=canned.sample_html_article,
                headers={"content-type": "text/html"},
            )

        patch_http(handler)

        item = make_item(
            body_text=None,
            canonical_url="https://spacenews.com/article",
        )

        results = await expand_items([item], tmp_store, concurrency=1, dry_run=True)

        assert len(results) == 1
        assert not tmp_store.exists(results[0].id)


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_pdf_extract_without_pdfplumber(self):
        from astral_ingest.expand.pdf_extract import extract_from_pdf

        with patch.dict("sys.modules", {"pdfplumber": None}):
            result = extract_from_pdf(b"fake pdf bytes")
        assert result is None

    async def test_js_fallback_without_playwright(self):
        from astral_ingest.expand.js_fallback import (
            fetch_js_rendered,
        )

        with patch.dict(
            "sys.modules",
            {"playwright": None, "playwright.async_api": None},
        ):
            result = await fetch_js_rendered("https://example.com")
        assert result is None
