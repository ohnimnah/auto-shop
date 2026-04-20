"""Qoo10 mapper placeholder."""

from marketplace.common.interfaces import MarketplacePayload, MarketplaceRow, MarketplaceRowMapper


class Qoo10RowMapper(MarketplaceRowMapper):
    """Placeholder for a future Qoo10 mapper."""

    def map_row(self, row_data: MarketplaceRow) -> MarketplacePayload:
        raise NotImplementedError("Qoo10 mapper is not implemented yet.")
