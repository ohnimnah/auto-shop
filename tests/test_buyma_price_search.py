import unittest
import json
from unittest.mock import patch

from bs4 import BeautifulSoup

from services import buyma_service


class _WaitStub:
    def __init__(self, *args, **kwargs):
        pass

    def until(self, *args, **kwargs):
        return True


class _ECStub:
    @staticmethod
    def presence_of_element_located(*args, **kwargs):
        return True


class _ByStub:
    TAG_NAME = "tag name"


class _DriverStub:
    def __init__(self, search_html: str, detail_html: str = "") -> None:
        self.search_html = search_html
        self.detail_html = detail_html or search_html
        self.page_source = ""

    def get(self, url: str) -> None:
        if "/item/" in url:
            self.page_source = self.detail_html
        else:
            self.page_source = self.search_html


class BuymaPriceSearchTests(unittest.TestCase):
    def test_price_search_query_order_prefers_sku_brand_then_names(self):
        queries = buyma_service.build_buyma_price_search_queries(
            "G CLASSIC TANK",
            "GLOWNY",
            "GC25SPSL0010GR",
            "クラシック タンク",
        )

        self.assertEqual(
            queries,
            [
                "GC25SPSL0010GR",
                "GLOWNY GC25SPSL0010GR",
                "GLOWNY G CLASSIC TANK",
                "GLOWNY クラシック タンク",
                "G CLASSIC TANK",
                "クラシック タンク",
            ],
        )

    def test_weak_english_fragment_query_is_skipped(self):
        queries = buyma_service.build_buyma_price_search_queries(
            "클래식 H라인 스커트 (숏/롱)",
            "카인다미",
            "BS25S3402",
            "クラシックHラインスカート（ショート/ロング）",
        )

        self.assertEqual(queries, ["BS25S3402", "クラシックHラインスカート（ショート/ロング）"])
        self.assertNotIn("H /", queries)

    def test_sheet_english_name_is_used_before_extracting_from_korean_name(self):
        queries = buyma_service.build_buyma_price_search_queries(
            "클래식 H라인 스커트 (숏/롱)",
            "KINDAME",
            "BS25S3402",
            "クラシックHラインスカート（ショート/ロング）",
            "Classic H-Line Skirt",
        )

        self.assertIn("KINDAME Classic H-Line Skirt", queries)
        self.assertIn("Classic H-Line Skirt", queries)
        self.assertNotIn("H /", queries)

    def test_listing_entry_does_not_reuse_price_from_multi_item_parent(self):
        soup = BeautifulSoup(
            """
            <ul>
              <li><a href="/item/111111/">Target Product</a></li>
              <li>
                <a href="/item/222222/">Other Product</a>
                <span class="Price_Txt">¥8,000</span>
              </li>
            </ul>
            """,
            "html.parser",
        )

        entries = buyma_service.extract_buyma_listing_entries(soup)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["url"], "https://www.buyma.com/item/222222/")
        self.assertEqual(entries[0]["price"], 8000)

    def test_sku_prefix6_alone_is_not_reliable(self):
        self.assertFalse(
            buyma_service.is_relevant_buyma_listing_entry(
                "GC25SP completely unrelated item ¥12,000",
                "GC25SPSL0010GR",
                "",
                "",
                "",
            )
        )

    def test_fetch_buyma_price_with_meta_prefers_reliable_detail_price(self):
        search_html = """
        <div>
          <a href="/item/222222/">GLOWNY G CLASSIC TANK GC25SPSL0010GR</a>
          <span class="Price_Txt">¥9,000</span>
        </div>
        """
        detail_html = """
        <html>
          <body>
            <h1>GLOWNY G CLASSIC TANK GC25SPSL0010GR</h1>
            <span class="Price_Txt">¥8,800</span>
          </body>
        </html>
        """
        driver = _DriverStub(search_html, detail_html)

        with patch.object(buyma_service, "WebDriverWait", _WaitStub), patch.object(
            buyma_service, "EC", _ECStub
        ), patch.object(buyma_service, "By", _ByStub), patch.object(
            buyma_service.time, "sleep", lambda *_: None
        ), patch("builtins.print"):
            result = buyma_service.fetch_buyma_lowest_price_with_meta(
                driver,
                "G CLASSIC TANK",
                "GLOWNY",
                "GC25SPSL0010GR",
                "クラシック タンク",
                "5,000",
            )

        meta = json.loads(result["buyma_meta"])
        self.assertEqual(result["buyma_price"], "8,800")
        self.assertGreaterEqual(meta["score"], 80)
        self.assertEqual(meta["source"], "detail")
        self.assertEqual(meta["selected_reason"], "lowest_valid_price")

    def test_low_outlier_price_is_filtered_against_median(self):
        candidates = [
            {"price": 5000, "score": 90},
            {"price": 10000, "score": 90},
            {"price": 11000, "score": 90},
        ]

        filtered = buyma_service._filter_valid_buyma_candidates(candidates)

        self.assertEqual([item["price"] for item in filtered], [10000, 11000])

    def test_fetch_buyma_lowest_price_returns_empty_when_only_unrelated_cards_match(self):
        search_html = """
        <div>
          <a href="/item/222222/">Completely Different Product</a>
          <span class="Price_Txt">¥8,000</span>
        </div>
        """
        detail_html = """
        <html>
          <body>
            <h1>Completely Different Product</h1>
            <span class="Price_Txt">¥8,000</span>
          </body>
        </html>
        """
        driver = _DriverStub(search_html, detail_html)

        with patch.object(buyma_service, "WebDriverWait", _WaitStub), patch.object(
            buyma_service, "EC", _ECStub
        ), patch.object(buyma_service, "By", _ByStub), patch.object(
            buyma_service.time, "sleep", lambda *_: None
        ), patch("builtins.print"):
            price = buyma_service.fetch_buyma_lowest_price(driver, "Target Product", "TARGETBRAND", "TARGETSKU")

        self.assertEqual(price, "")


if __name__ == "__main__":
    unittest.main()
