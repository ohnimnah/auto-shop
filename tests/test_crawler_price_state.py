import unittest

from services.crawler_service_legacy import find_product_price_candidates_from_state


class CrawlerStatePriceTests(unittest.TestCase):
    def test_ignores_coupon_discount_amount_when_sale_price_exists(self):
        state = {
            "couponDcPrice": 3800,
            "goodsPrice": {
                "salePrice": 38000,
                "normalPrice": 38000,
                "couponPrice": 34200,
                "couponDiscount": True,
            },
        }

        self.assertEqual(find_product_price_candidates_from_state(state)[0], 38000)


if __name__ == "__main__":
    unittest.main()
