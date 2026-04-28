from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass
class CrawlJobResult:
    processed: int = 0
    succeeded: int = 0
    failed: int = 0


class CrawlJob:
    """Run crawl tasks in a single operational unit."""

    def __init__(self, crawl_one: Callable[[str], bool]) -> None:
        self._crawl_one = crawl_one

    def run_once(self, urls: Iterable[str]) -> CrawlJobResult:
        result = CrawlJobResult()
        for url in urls:
            clean = (url or "").strip()
            if not clean:
                continue
            result.processed += 1
            ok = bool(self._crawl_one(clean))
            if ok:
                result.succeeded += 1
            else:
                result.failed += 1
        return result

