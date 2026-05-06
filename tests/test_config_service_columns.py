import unittest

from config.config_service import _migrate_japanese_name_column


class ConfigServiceColumnTests(unittest.TestCase):
    def test_japanese_name_column_migration_shifts_old_default_mapping(self):
        columns = {
            "product_name_kr": "E",
            "product_name_en": "F",
            "musinsa_sku": "G",
            "price": "L",
            "buyma_price": "M",
            "buyma_meta": "N",
            "image_paths": "O",
            "shipping_cost": "P",
            "category_large": "X",
            "category_middle": "Y",
            "category_small": "Z",
            "shipping_table_range": "AA1:AC60",
        }

        migrated = _migrate_japanese_name_column(columns)

        self.assertEqual(migrated["product_name_jp"], "F")
        self.assertEqual(migrated["product_name_en"], "G")
        self.assertEqual(migrated["musinsa_sku"], "H")
        self.assertEqual(migrated["price"], "M")
        self.assertEqual(migrated["buyma_price"], "N")
        self.assertEqual(migrated["buyma_meta"], "O")
        self.assertEqual(migrated["image_paths"], "P")
        self.assertEqual(migrated["shipping_cost"], "Q")
        self.assertEqual(migrated["category_small"], "AA")
        self.assertEqual(migrated["shipping_table_range"], "AB1:AD60")


if __name__ == "__main__":
    unittest.main()
