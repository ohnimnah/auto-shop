from __future__ import annotations

from typing import Protocol
try:
    from tenacity import retry, stop_after_attempt, wait_fixed
except Exception:  # pragma: no cover
    def retry(*_args, **_kwargs):
        def _decorator(fn):
            return fn

        return _decorator

    def stop_after_attempt(_n):
        return None

    def wait_fixed(_n):
        return None


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
