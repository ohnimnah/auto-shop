"""Marketplace-neutral interfaces for mappers and uploaders."""

from __future__ import annotations

from typing import Dict, Protocol


MarketplaceRow = Dict[str, str]
MarketplacePayload = Dict[str, object]


class MarketplaceRowMapper(Protocol):
    """Convert a source row into marketplace-specific payload."""

    def map_row(self, row_data: MarketplaceRow) -> MarketplacePayload:
        ...


class MarketplaceUploader(Protocol):
    """Execute marketplace-specific upload flows."""

    def fill_form(self, driver, row_data: MarketplaceRow) -> str:
        ...

    def upload_rows(
        self,
        *,
        specific_row: int = 0,
        upload_mode: str = "auto",
        max_items: int = 0,
        interactive: bool = True,
    ) -> None:
        ...
