import unittest

from models.product_model import Product, product_from_sheet_row, product_to_sheet_field_map


class ProductModelTests(unittest.TestCase):
    def test_product_from_sheet_row_ignores_formula_errors(self):
        product = product_from_sheet_row(
            {"F": "#VALUE!", "G": "#N/A", "H": "TS25S3105"},
            {"product_name_jp": "F", "product_name_en": "G", "musinsa_sku": "H"},
        )

        self.assertEqual(product.product_name_jp, "")
        self.assertEqual(product.product_name_en, "")
        self.assertEqual(product.musinsa_sku, "TS25S3105")

    def test_product_to_sheet_field_map_keeps_runtime_brand_logo_url(self):
        product = Product(
            product_name_kr="HIGHNECK DRAPE HOOD ZIPUP DRESS",
            brand_en="BNFROM",
            brand_logo_url="https://image.msscdn.net/mfile_s01/_brand/free_medium/bnfrom.png",
        )

        product_map = product_to_sheet_field_map(product)

        self.assertEqual(
            product_map["brand_logo_url"],
            "https://image.msscdn.net/mfile_s01/_brand/free_medium/bnfrom.png",
        )


if __name__ == "__main__":
    unittest.main()
