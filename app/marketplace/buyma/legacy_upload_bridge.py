from __future__ import annotations

import buyma_upload as legacy_upload


class LegacyBuymaUploader:
    """Adapter over legacy buyma_upload entrypoint."""

    def run(self, mode: str = "auto") -> int:
        legacy_upload.upload_products(upload_mode=mode, interactive=False)
        return 1

