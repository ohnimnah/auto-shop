"""Qoo10 uploader placeholder."""

from marketplace.common.interfaces import MarketplaceRow, MarketplaceUploader


class Qoo10Uploader(MarketplaceUploader):
    """Placeholder for a future Qoo10 uploader."""

    def fill_form(self, driver, row_data: MarketplaceRow) -> str:
        raise NotImplementedError("Qoo10 uploader is not implemented yet.")

    def upload_rows(
        self,
        *,
        specific_row: int = 0,
        upload_mode: str = "auto",
        max_items: int = 0,
        interactive: bool = True,
    ) -> None:
        raise NotImplementedError("Qoo10 uploader is not implemented yet.")
