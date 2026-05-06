import unittest

from models.product_model import product_from_sheet_row


class ProductModelTests(unittest.TestCase):
    def test_product_from_sheet_row_ignores_formula_errors(self):
        product = product_from_sheet_row(
            {"F": "#VALUE!", "G": "#N/A", "H": "TS25S3105"},
            {"product_name_jp": "F", "product_name_en": "G", "musinsa_sku": "H"},
        )

        self.assertEqual(product.product_name_jp, "")
        self.assertEqual(product.product_name_en, "")
        self.assertEqual(product.musinsa_sku, "TS25S3105")


if __name__ == "__main__":
    unittest.main()
