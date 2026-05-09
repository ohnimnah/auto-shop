import unittest
from unittest.mock import patch

from services import listing_queue_service


class _FakeExecute:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def execute(self):
        return self.payload


class _FakeValues:
    def __init__(self):
        self.get_calls = []
        self.append_calls = []
        self.update_calls = []
        self.next_get_payload = {"values": []}

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return _FakeExecute(self.next_get_payload)

    def append(self, **kwargs):
        self.append_calls.append(kwargs)
        return _FakeExecute({})

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return _FakeExecute({})


class _FakeSpreadsheets:
    def __init__(self, values):
        self._values = values

    def values(self):
        return self._values


class _FakeSheetsService:
    def __init__(self):
        self.values_api = _FakeValues()

    def spreadsheets(self):
        return _FakeSpreadsheets(self.values_api)


class ListingQueueServiceTests(unittest.TestCase):
    def test_main_sheet_existing_product_ids_are_read_from_url_column(self):
        service = _FakeSheetsService()
        service.values_api.next_get_payload = {
            "values": [
                ["https://www.musinsa.com/products/1111111"],
                ["https://www.musinsa.com/products/2222222?foo=bar"],
                [""],
            ]
        }

        product_ids = listing_queue_service._read_existing_product_ids_from_main_sheet(
            service,
            "spreadsheet-id",
            "업로드정리",
            "B",
        )

        self.assertEqual(product_ids, {"1111111", "2222222"})
        self.assertEqual(service.values_api.get_calls[0]["range"], "'업로드정리'!B2:B")

    def test_append_product_urls_to_main_sheet_writes_after_last_b_value(self):
        service = _FakeSheetsService()
        service.values_api.next_get_payload = {
            "values": [
                ["https://www.musinsa.com/products/1111111"],
                [],
                ["https://www.musinsa.com/products/2222222"],
            ]
        }

        inserted = listing_queue_service._append_product_urls_to_main_sheet(
            service,
            "spreadsheet-id",
            "업로드정리",
            "B",
            [
                "https://www.musinsa.com/products/1111111",
                "",
                "not-a-url",
            ],
        )

        self.assertEqual(inserted, 1)
        self.assertEqual(service.values_api.get_calls[0]["range"], "'업로드정리'!B2:B")
        update_call = service.values_api.update_calls[0]
        self.assertEqual(update_call["range"], "'업로드정리'!B5:B5")
        self.assertEqual(update_call["body"]["values"], [["https://www.musinsa.com/products/1111111"]])

    def test_backfill_main_sheet_from_queue_rows_appends_queue_urls_missing_from_main(self):
        service = _FakeSheetsService()
        service.values_api.next_get_payload = {"values": [["https://www.musinsa.com/products/1111111"]]}
        queue_rows = [
            (2, {"상품ID": "1111111", "상품URL": "https://www.musinsa.com/products/1111111"}),
            (3, {"상품ID": "2222222", "상품URL": "https://www.musinsa.com/products/2222222"}),
            (4, {"상품ID": "3333333", "상품URL": ""}),
        ]

        inserted = listing_queue_service._backfill_main_sheet_from_queue_rows(
            service=service,
            spreadsheet_id="spreadsheet-id",
            product_sheet_name="업로드정리",
            product_url_column="B",
            queue_rows=queue_rows,
            main_existing_ids={"1111111"},
        )

        self.assertEqual(inserted, 1)
        update_call = service.values_api.update_calls[0]
        self.assertEqual(update_call["range"], "'업로드정리'!B3:B3")
        self.assertEqual(update_call["body"]["values"], [["https://www.musinsa.com/products/2222222"]])

    def test_collect_uses_separate_main_spreadsheet_id_for_main_backfill(self):
        service = _FakeSheetsService()
        header_map = {header: idx for idx, header in enumerate(listing_queue_service.QUEUE_HEADERS)}

        with patch("services.listing_queue_service._read_all_queue_rows", return_value=[]), patch(
            "services.listing_queue_service._read_existing_product_ids_from_main_sheet", return_value=set()
        ) as read_existing, patch(
            "services.listing_queue_service._backfill_main_sheet_from_queue_rows", return_value=0
        ) as backfill:
            listing_queue_service.collect_listing_queue_once(
                service=service,
                driver=object(),
                spreadsheet_id="queue-spreadsheet-id",
                queue_sheet_name="목록 페이지 url",
                seed_sheet_name="목록 페이지 url",
                get_sheet_header_map_fn=lambda _svc, _sheet: header_map,
                product_spreadsheet_id="main-spreadsheet-id",
                product_sheet_name="업로드정리",
                product_url_column="B",
            )

        self.assertEqual(read_existing.call_args.kwargs["spreadsheet_id"], "main-spreadsheet-id")
        self.assertEqual(backfill.call_args.kwargs["spreadsheet_id"], "main-spreadsheet-id")


if __name__ == "__main__":
    unittest.main()
