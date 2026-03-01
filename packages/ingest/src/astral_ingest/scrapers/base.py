from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from astral_core import ContentItem

USER_AGENT = (
    "AstralIndex/0.1 (space newsletter aggregator; "
    "+https://github.com/aarontaylor/astral-index)"
)

DEFAULT_TIMEOUT = 30.0


def make_http_client(**kwargs: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        **kwargs,
    )


class BaseScraper(ABC):
    @abstractmethod
    async def fetch(self) -> list[ContentItem]:
        """Fetch new content items from this source."""
        ...
