"""Three-stage article text extraction cascade.

All functions are synchronous — they operate on already-fetched HTML.
HTTP fetching is handled by the pipeline orchestrator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from astral_core import ExtractionMethod

logger = logging.getLogger(__name__)

# Minimum word count to consider an extraction successful
_MIN_WORDS = 50


@dataclass
class ExtractionResult:
    text: str
    method: ExtractionMethod
    word_count: int


def _try_trafilatura(html: str, url: str) -> ExtractionResult | None:
    try:
        import trafilatura
    except ImportError:
        logger.debug("trafilatura not installed, skipping")
        return None

    text = trafilatura.extract(html, url=url, include_comments=False)
    if not text:
        return None
    wc = len(text.split())
    if wc < _MIN_WORDS:
        return None
    return ExtractionResult(text=text, method=ExtractionMethod.TRAFILATURA, word_count=wc)


def _try_newspaper(html: str, url: str) -> ExtractionResult | None:
    try:
        from newspaper import Article
    except ImportError:
        logger.debug("newspaper4k not installed, skipping")
        return None

    article = Article(url)
    article.download(input_html=html)
    article.parse()
    text = article.text
    if not text:
        return None
    wc = len(text.split())
    if wc < _MIN_WORDS:
        return None
    return ExtractionResult(text=text, method=ExtractionMethod.NEWSPAPER, word_count=wc)


def _try_readability(html: str, url: str) -> ExtractionResult | None:
    try:
        from readability import Document
    except ImportError:
        logger.debug("readability-lxml not installed, skipping")
        return None

    from ..util import strip_html

    doc = Document(html, url=url)
    summary_html = doc.summary()
    text = strip_html(summary_html)
    if not text:
        return None
    wc = len(text.split())
    if wc < _MIN_WORDS:
        return None
    return ExtractionResult(text=text, method=ExtractionMethod.READABILITY, word_count=wc)


def extract_from_html(html: str, url: str) -> ExtractionResult | None:
    """Try extraction via trafilatura → newspaper4k → readability-lxml.

    Returns the first successful result meeting the minimum word threshold,
    or None if all methods fail.
    """
    for extractor in (_try_trafilatura, _try_newspaper, _try_readability):
        try:
            result = extractor(html, url)
            if result:
                logger.debug("Extracted %d words via %s from %s", result.word_count, result.method, url)
                return result
        except Exception:
            logger.exception("Extraction failed with %s for %s", extractor.__name__, url)
    return None
