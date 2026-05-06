import unittest

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
        self.assertEqual(service.values_api.get_calls[0]["range"], "'업로드정리'!B2:B5000")

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


if __name__ == "__main__":
    unittest.main()
