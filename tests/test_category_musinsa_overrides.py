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

    def test_musinsa_short_pants_wins_over_knit_keyword(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="바지",
            musinsa_small="숏 팬츠",
            product_name="CANDY POP KNIT SHORTS",
            brand="GLOWNY",
        )

        self.assertEqual(result, StandardCategory.PANTS_SHORTS)
        self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_musinsa_english_shorts_wins_over_knit_keyword(self):
        for middle, small in (
            ("바지", "Short Pants"),
            ("팬츠", "SHORTS"),
            ("Bottoms", "Half Pants"),
        ):
            with self.subTest(middle=middle, small=small):
                result, meta = classify_standard_category_from_sheet(
                    musinsa_large="여성",
                    musinsa_middle=middle,
                    musinsa_small=small,
                    product_name="CANDY POP KNIT SHORTS",
                    brand="GLOWNY",
                )

                self.assertEqual(result, StandardCategory.PANTS_SHORTS)
                self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_musinsa_konglish_shorts_wins_over_knit_keyword(self):
        for middle, small in (
            ("바지", "쇼트 팬츠"),
            ("바지", "하프팬츠"),
            ("팬츠", "핫 팬츠"),
            ("팬츠", "숏츠"),
        ):
            with self.subTest(middle=middle, small=small):
                result, meta = classify_standard_category_from_sheet(
                    musinsa_large="여성",
                    musinsa_middle=middle,
                    musinsa_small=small,
                    product_name="CANDY POP KNIT SHORTS",
                    brand="GLOWNY",
                )

                self.assertEqual(result, StandardCategory.PANTS_SHORTS)
                self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_musinsa_top_category_wins_with_korean_english_labels(self):
        cases = (
            ("상의", "니트", "COTTON SHORTS DETAIL", StandardCategory.TOP_KNIT),
            ("상의", "Hoodie", "BASIC PANTS", StandardCategory.TOP_HOODIE),
            ("Tops", "Sleeveless", "SUMMER SHORTS", StandardCategory.TOP_TANK),
            ("상의", "블라우스", "DENIM SKIRT", StandardCategory.TOP_BLOUSE),
        )
        for middle, small, product_name, expected in cases:
            with self.subTest(middle=middle, small=small):
                result, meta = classify_standard_category_from_sheet(
                    musinsa_large="여성",
                    musinsa_middle=middle,
                    musinsa_small=small,
                    product_name=product_name,
                    brand="BRAND",
                )

                self.assertEqual(result, expected)
                self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_musinsa_accessory_category_wins_with_korean_english_labels(self):
        cases = (
            ("악세서리", "선글라스", StandardCategory.ACC_EYEWEAR),
            ("액세서리", "비니", StandardCategory.ACC_BEANIE),
            ("Accessories", "Scarf", StandardCategory.ACC_SCARF),
            ("악세서리", "벨트", StandardCategory.ACC_BELT),
        )
        for middle, small, expected in cases:
            with self.subTest(middle=middle, small=small):
                result, meta = classify_standard_category_from_sheet(
                    musinsa_large="여성",
                    musinsa_middle=middle,
                    musinsa_small=small,
                    product_name="NOISY KNIT PANTS",
                    brand="BRAND",
                )

                self.assertEqual(result, expected)
                self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_musinsa_outer_category_wins_over_broad_sports_label(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="스포츠/레저",
            musinsa_small="아우터",
            product_name="URBAN SUEDE JUMPER",
            brand="GLOWNY",
        )

        self.assertEqual(result, StandardCategory.OUTER_JACKET)
        self.assertEqual(meta["reason"], "musinsa_category_override")


if __name__ == "__main__":
    unittest.main()
