import unittest

from marketplace.buyma.standard_category import StandardCategory
from marketplace.common.category_classifier import classify_standard_category_from_sheet


class MusinsaCategoryOverrideTests(unittest.TestCase):
    def test_shorts_musinsa_category_wins_over_padding_keywords(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="바지",
            musinsa_small="반바지",
            product_name="Hip-Boosting Low-Waist Light Blue Shorts_Hip-Padding Jeans",
            brand="KINDAME",
        )

        self.assertEqual(result, StandardCategory.PANTS_SHORTS)
        self.assertEqual(meta["reason"], "musinsa_category_override")


if __name__ == "__main__":
    unittest.main()
