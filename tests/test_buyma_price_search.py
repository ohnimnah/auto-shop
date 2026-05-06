import unittest
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
    def test_price_search_query_order_prefers_sku_then_name_then_brand_name(self):
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
                "G CLASSIC TANK",
                "GLOWNY G CLASSIC TANK",
                "クラシック タンク",
                "GLOWNY クラシック タンク",
            ],
        )

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

    def test_japanese_name_can_match_listing_without_english_tokens(self):
        self.assertTrue(
            buyma_service.is_relevant_buyma_listing_entry(
                "GLOWNY クラシック タンクトップ ¥12,000",
                "",
                "",
                "GLOWNY",
                "クラシック タンクトップ",
            )
        )

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
