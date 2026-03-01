"""Per-domain rate limiting for polite crawling."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse


class DomainRateLimiter:
    """Enforces ~1 request/sec per domain using per-domain semaphores + timing."""

    def __init__(self, delay: float = 1.0) -> None:
        self._delay = delay
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    async def acquire(self, url: str) -> None:
        """Wait until we can make a request to this URL's domain."""
        domain = self._domain(url)
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()

        async with self._locks[domain]:
            last = self._last_request.get(domain, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < self._delay:
                await asyncio.sleep(self._delay - elapsed)
            self._last_request[domain] = time.monotonic()
