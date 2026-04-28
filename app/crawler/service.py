from __future__ import annotations

from typing import Protocol


class ProductCrawler(Protocol):
    def crawl(self, url: str) -> bool:
        ...


class CrawlerServiceAdapter:
    """Dependency-inverted crawler adapter."""

    def __init__(self, crawler: ProductCrawler) -> None:
        self._crawler = crawler

    def crawl_url(self, url: str) -> bool:
        return bool(self._crawler.crawl(url))

