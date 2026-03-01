"""PDF text extraction via pdfplumber."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from astral_core import ExtractionMethod

logger = logging.getLogger(__name__)


@dataclass
class PDFResult:
    text: str
    method: ExtractionMethod
    word_count: int


def extract_from_pdf(content: bytes) -> PDFResult | None:
    """Extract text from PDF bytes.

    Returns None if pdfplumber is missing or extraction fails.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.debug("pdfplumber not installed, skipping PDF extraction")
        return None

    try:
        pages_text: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

        if not pages_text:
            return None

        full_text = "\n\n".join(pages_text)
        wc = len(full_text.split())
        if wc < 50:
            return None

        return PDFResult(text=full_text, method=ExtractionMethod.PDF, word_count=wc)
    except Exception:
        logger.exception("PDF extraction failed")
        return None
