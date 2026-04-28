from __future__ import annotations

from services import crawler_service as legacy


class LegacyCrawler:
    """Bridge to existing crawler implementation while enabling app-layer DI."""

    def crawl(self, url: str) -> bool:
        # Legacy crawler has many extraction primitives; quick health check uses JSON fetch.
        payload = legacy.fetch_json(url)
        return bool(payload)

