import unittest

from marketplace.common.sheet_source import column_letter_to_index, read_upload_rows

DEFAULT_UPLOAD_COLUMNS = {
    "url": "B",
    "brand": "C",
    "brand_en": "D",
    "product_name_kr": "E",
    "product_name_jp": "F",
    "product_name_en": "G",
    "musinsa_sku": "H",
    "color_kr": "I",
    "color_en": "J",
    "size": "K",
    "actual_size": "L",
    "price_krw": "M",
    "buyma_price": "N",
    "image_paths": "P",
    "shipping_cost": "Q",
    "category_legacy_large": "V",
    "category_legacy_middle": "W",
    "category_legacy_small": "X",
    "musinsa_category_large": "Y",
    "musinsa_category_middle": "Z",
    "musinsa_category_small": "AA",
}


class _FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeValues:
    def get(self, *, spreadsheetId, range):
        if range.endswith("1:1"):
            return _FakeRequest({"values": [["진행상태"]]})
        row = [""] * 27
        row[column_letter_to_index("B")] = "https://example.com/product"
        row[column_letter_to_index("C")] = "Brand KR"
        row[column_letter_to_index("D")] = "Brand EN"
        row[column_letter_to_index("E")] = "상품명"
        row[column_letter_to_index("N")] = "12300"
        row[column_letter_to_index("P")] = "/tmp/images"
        row[column_letter_to_index("Q")] = "1200"
        row[column_letter_to_index("Y")] = "여성"
        row[column_letter_to_index("Z")] = "바지"
        row[column_letter_to_index("AA")] = "데님"
        row[column_letter_to_index("A")] = "썸네일완료"
        return _FakeRequest({"values": [row]})


class _FakeSpreadsheets:
    def values(self):
        return _FakeValues()


class _FakeService:
    def spreadsheets(self):
        return _FakeSpreadsheets()


class SheetSourceTests(unittest.TestCase):
    def test_column_letter_to_index(self):
        self.assertEqual(column_letter_to_index("A"), 0)
        self.assertEqual(column_letter_to_index("Z"), 25)
        self.assertEqual(column_letter_to_index("AA"), 26)

    def test_read_upload_rows_uses_column_letters(self):
        rows = read_upload_rows(
            _FakeService(),
            spreadsheet_id="spreadsheet",
            sheet_name="시트1",
            row_start=2,
            header_row=1,
            max_data_column="Y",
            upload_columns=DEFAULT_UPLOAD_COLUMNS,
            progress_status_header="진행상태",
            status_completed="출품완료",
            status_upload_ready="썸네일완료",
            status_thumbnails_done="썸네일완료",
            specific_row=2,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://example.com/product")
        self.assertEqual(rows[0]["product_name_kr"], "상품명")
        self.assertEqual(rows[0]["buyma_price"], "12300")
        self.assertEqual(rows[0]["musinsa_category_large"], "여성")
        self.assertEqual(rows[0]["musinsa_category_middle"], "바지")
        self.assertEqual(rows[0]["musinsa_category_small"], "데님")

    def test_read_upload_rows_follows_configured_column_letters(self):
        configured = {
            **DEFAULT_UPLOAD_COLUMNS,
            "url": "AA",
            "product_name_kr": "AB",
            "buyma_price": "AC",
            "musinsa_category_large": "AD",
            "musinsa_category_middle": "AE",
            "musinsa_category_small": "AF",
        }

        class CustomValues:
            def get(self, *, spreadsheetId, range):
                if range.endswith("1:1"):
                    return _FakeRequest({"values": [["진행상태"]]})
                row = [""] * 32
                row[column_letter_to_index("AA")] = "https://example.com/custom"
                row[column_letter_to_index("AB")] = "설정 상품명"
                row[column_letter_to_index("AC")] = "55500"
                row[column_letter_to_index("AD")] = "남성"
                row[column_letter_to_index("AE")] = "상의"
                row[column_letter_to_index("AF")] = "후드티"
                row[column_letter_to_index("A")] = "썸네일완료"
                return _FakeRequest({"values": [row]})

        class CustomSpreadsheets:
            def values(self):
                return CustomValues()

        class CustomService:
            def spreadsheets(self):
                return CustomSpreadsheets()

        rows = read_upload_rows(
            CustomService(),
            spreadsheet_id="spreadsheet",
            sheet_name="시트1",
            row_start=2,
            header_row=1,
            max_data_column="Y",
            upload_columns=configured,
            progress_status_header="진행상태",
            status_completed="출품완료",
            status_upload_ready="썸네일완료",
            status_thumbnails_done="썸네일완료",
            specific_row=2,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://example.com/custom")
        self.assertEqual(rows[0]["product_name_kr"], "설정 상품명")
        self.assertEqual(rows[0]["buyma_price"], "55500")
        self.assertEqual(rows[0]["musinsa_category_large"], "남성")
        self.assertEqual(rows[0]["musinsa_category_middle"], "상의")
        self.assertEqual(rows[0]["musinsa_category_small"], "후드티")

    def test_read_upload_rows_prefilters_candidates_by_status_only(self):
        calls = []

        class StatusOnlyValues:
            def get(self, *, spreadsheetId, range):
                calls.append(("get", range))
                if range.endswith("1:1"):
                    headers = [""] * 17
                    headers[column_letter_to_index("Q")] = "진행상태"
                    return _FakeRequest({"values": [headers]})
                if range == "'시트1'!Q2:Q":
                    return _FakeRequest({"values": [["정찰완료"], ["썸네일완료"]]})
                raise AssertionError(f"unexpected get range: {range}")

            def batchGet(self, *, spreadsheetId, ranges):
                calls.append(("batchGet", tuple(ranges)))
                if ranges != ["'시트1'!A3:AA3"]:
                    raise AssertionError(f"unexpected batch ranges: {ranges}")
                row = [""] * 27
                row[column_letter_to_index("B")] = "https://example.com/upload"
                row[column_letter_to_index("E")] = "업로드상품"
                row[column_letter_to_index("N")] = "222"
                row[column_letter_to_index("Q")] = "썸네일완료"
                row[column_letter_to_index("Y")] = "여성"
                return _FakeRequest({"valueRanges": [{"values": [row]}]})

        class StatusOnlySpreadsheets:
            def values(self):
                return StatusOnlyValues()

        class StatusOnlyService:
            def spreadsheets(self):
                return StatusOnlySpreadsheets()

        rows = read_upload_rows(
            StatusOnlyService(),
            spreadsheet_id="spreadsheet",
            sheet_name="시트1",
            row_start=2,
            header_row=1,
            max_data_column="AA",
            upload_columns=DEFAULT_UPLOAD_COLUMNS,
            progress_status_header="진행상태",
            status_completed="출품완료",
            status_upload_ready="썸네일완료",
            status_thumbnails_done="썸네일완료",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["row_num"], 3)
        self.assertEqual(rows[0]["product_name_kr"], "업로드상품")
        self.assertIn(("get", "'시트1'!Q2:Q"), calls)
        self.assertTrue(any(call[0] == "batchGet" for call in calls))

    def test_read_upload_rows_skips_completed_specific_row(self):
        class CompletedValues:
            def get(self, *, spreadsheetId, range):
                if range.endswith("1:1"):
                    return _FakeRequest({"values": [["진행상태"]]})
                row = [""] * 27
                row[column_letter_to_index("A")] = "출품완료"
                row[column_letter_to_index("B")] = "https://example.com/done"
                row[column_letter_to_index("E")] = "완료상품"
                row[column_letter_to_index("N")] = "999"
                return _FakeRequest({"values": [row]})

        class CompletedSpreadsheets:
            def values(self):
                return CompletedValues()

        class CompletedService:
            def spreadsheets(self):
                return CompletedSpreadsheets()

        rows = read_upload_rows(
            CompletedService(),
            spreadsheet_id="spreadsheet",
            sheet_name="시트1",
            row_start=2,
            header_row=1,
            max_data_column="AA",
            upload_columns=DEFAULT_UPLOAD_COLUMNS,
            progress_status_header="진행상태",
            status_completed="출품완료",
            status_upload_ready="썸네일완료",
            status_thumbnails_done="썸네일완료",
            specific_row=2,
        )

        self.assertEqual(rows, [])

    def test_read_upload_rows_stops_when_status_header_missing(self):
        class MissingStatusValues:
            def get(self, *, spreadsheetId, range):
                if range.endswith("1:1"):
                    return _FakeRequest({"values": [["링크", "상품명"]]})
                raise AssertionError(f"unexpected get range: {range}")

        class MissingStatusSpreadsheets:
            def values(self):
                return MissingStatusValues()

        class MissingStatusService:
            def spreadsheets(self):
                return MissingStatusSpreadsheets()

        rows = read_upload_rows(
            MissingStatusService(),
            spreadsheet_id="spreadsheet",
            sheet_name="시트1",
            row_start=2,
            header_row=1,
            max_data_column="AA",
            upload_columns=DEFAULT_UPLOAD_COLUMNS,
            progress_status_header="진행상태",
            status_completed="출품완료",
            status_upload_ready="썸네일완료",
            status_thumbnails_done="썸네일완료",
        )

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
