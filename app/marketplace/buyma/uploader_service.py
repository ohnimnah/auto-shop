from __future__ import annotations

from typing import Protocol
from tenacity import retry, stop_after_attempt, wait_fixed


class BuymaUploader(Protocol):
    def run(self, mode: str = "auto") -> int:
        ...


class BuymaUploaderService:
    """Application-layer facade for BUYMA upload execution."""

    def __init__(self, uploader: BuymaUploader) -> None:
        self._uploader = uploader

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def execute(self, mode: str = "auto") -> int:
        return int(self._uploader.run(mode=mode))
