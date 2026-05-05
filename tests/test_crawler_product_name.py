import unittest

from services.crawler_service_legacy import clean_product_name, remove_trailing_product_name_suffix


class CrawlerProductNameTests(unittest.TestCase):
    def test_removes_parenthesized_english_color_suffix(self):
        self.assertEqual(clean_product_name("G CLASSIC TANK (GRAY)"), "G CLASSIC TANK")

    def test_removes_bracketed_korean_color_suffix(self):
        self.assertEqual(clean_product_name("클래식 탱크 [그레이]"), "클래식 탱크")

    def test_removes_hyphen_color_suffix(self):
        self.assertEqual(clean_product_name("클래식 탱크 - 블랙"), "클래식 탱크")

    def test_removes_plain_trailing_color_suffix(self):
        self.assertEqual(clean_product_name("클래식 탱크 라이트 그레이"), "클래식 탱크")

    def test_removes_color_count_placeholder(self):
        self.assertEqual(remove_trailing_product_name_suffix("클래식 탱크 2COLOR"), "클래식 탱크")
        self.assertEqual(clean_product_name("클래식 탱크 (2color)"), "클래식 탱크")

    def test_removes_trailing_sku_suffix(self):
        self.assertEqual(clean_product_name("클래식 탱크 ABC1234"), "클래식 탱크")
        self.assertEqual(clean_product_name("클래식 탱크 (ABC1234)"), "클래식 탱크")
        self.assertEqual(clean_product_name("클래식 탱크 [AB-1234]"), "클래식 탱크")

    def test_keeps_plain_number_or_word_suffix(self):
        self.assertEqual(clean_product_name("클래식 탱크 2026"), "클래식 탱크 2026")
        self.assertEqual(clean_product_name("클래식 탱크 SPECIAL"), "클래식 탱크 SPECIAL")

    def test_keeps_non_color_parenthesized_suffix(self):
        self.assertEqual(clean_product_name("클래식 탱크 (기획상품)"), "클래식 탱크 (기획상품)")


if __name__ == "__main__":
    unittest.main()
