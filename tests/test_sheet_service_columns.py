import unittest

from services.sheet_service import get_existing_row_values


class _FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeValues:
    def __init__(self):
        self.requested_range = ""

    def get(self, *, spreadsheetId, range):
        self.requested_range = range
        row = [""] * 32
        row[0] = "1"
        row[1] = "https://example.com"
        row[25] = "Moved Brand"
        row[26] = "Moved Product"
        row[27] = "Moved Price"
        row[28] = "Moved Images"
        row[29] = "Moved Shipping"
        row[30] = "JP Name"
        row[31] = "Meta"
        return _FakeRequest({"values": [row]})


class _FakeSpreadsheets:
    def __init__(self, values):
        self._values = values

    def values(self):
        return self._values


class _FakeService:
    def __init__(self):
        self.values = _FakeValues()

    def spreadsheets(self):
        return _FakeSpreadsheets(self.values)


class SheetServiceColumnTests(unittest.TestCase):
    def test_existing_row_values_use_configured_column_letters(self):
        service = _FakeService()

        row = get_existing_row_values(
            service=service,
            spreadsheet_id="spreadsheet",
            sheet_name="시트1",
            row_num=2,
            sequence_column="A",
            url_column="B",
            brand_column="Z",
            brand_en_column="D",
            product_name_kr_column="AA",
            product_name_jp_column="AE",
            product_name_en_column="F",
            musinsa_sku_column="G",
            color_kr_column="H",
            color_en_column="I",
            size_column="J",
            actual_size_column="K",
            price_column="AB",
            buyma_sell_price_column="M",
            buyma_meta_column="AF",
            image_paths_column="AC",
            shipping_cost_column="AD",
            category_large_column="W",
            category_middle_column="X",
            category_small_column="Y",
        )

        self.assertEqual(row["Z"], "Moved Brand")
        self.assertEqual(row["AA"], "Moved Product")
        self.assertEqual(row["AE"], "JP Name")
        self.assertEqual(row["AF"], "Meta")
        self.assertEqual(row["AB"], "Moved Price")
        self.assertEqual(row["AC"], "Moved Images")
        self.assertEqual(row["AD"], "Moved Shipping")
        self.assertIn(":AF2", service.values.requested_range)


if __name__ == "__main__":
    unittest.main()
