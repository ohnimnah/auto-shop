from __future__ import annotations

from typing import Any


class SheetsGateway:
    """Thin wrapper for batch updates to improve reliability and testability."""

    def __init__(self, service: Any, spreadsheet_id: str) -> None:
        self.service = service
        self.spreadsheet_id = spreadsheet_id

    def batch_update_values(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        body = {"valueInputOption": "RAW", "data": data}
        return (
            self.service.spreadsheets()
            .values()
            .batchUpdate(spreadsheetId=self.spreadsheet_id, body=body)
            .execute()
        )

