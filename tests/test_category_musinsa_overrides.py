import unittest

from marketplace.buyma.standard_category import StandardCategory
from marketplace.common.category_classifier import classify_category_with_reason, classify_standard_category_from_sheet


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
            ("상의", "반팔 셔츠", "SHORT SLEEVE SHIRT", StandardCategory.TOP_SHIRT),
            ("상의", "긴팔 브라우스", "LONG SLEEVE BLOUSE", StandardCategory.TOP_BLOUSE),
            ("상의", "반팔 티셔츠", "LOGO T-SHIRT", StandardCategory.TOP_TSHIRT),
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
            ("액세서리", "버킷햇", StandardCategory.ACC_HAT),
            ("악세서리", "시계", StandardCategory.ACC_WATCH),
            ("액세서리", "목걸이", StandardCategory.ACC_JEWELRY),
            ("소품", "양말/레그웨어", StandardCategory.ACC_SOCKS),
            ("스포츠/레저", "수영복/비치웨어", StandardCategory.SWIMWEAR),
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

    def test_musinsa_pants_category_wins_over_belted_product_name(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="바지",
            musinsa_small="코튼 팬츠",
            product_name="Belted Two-Pocket Cutline Oversized Pants",
            brand="ETRE AU SOMMET",
        )

        self.assertEqual(result, StandardCategory.PANTS_REGULAR)
        self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_jacket_product_title_wins_over_vague_top_category(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="상의",
            musinsa_small="기타 상의",
            product_name="Cropped Short Sleeve Tailored Jacket",
            brand="ETRE AU SOMMET",
        )

        self.assertEqual(result, StandardCategory.OUTER_JACKET)
        self.assertEqual(meta["reason"], "product_keyword_override")

    def test_explicit_tshirt_bucket_wins_over_hooded_product_title(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="상의",
            musinsa_small="긴소매 티셔츠",
            product_name="Lettering Hooded Slim-Fit Long Sleeve Top",
            brand="ETRE AU SOMMET",
        )

        self.assertEqual(result, StandardCategory.TOP_TSHIRT)
        self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_musinsa_sports_vest_maps_to_outer_vest(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="스포츠/레저",
            musinsa_small="베스트",
            product_name="BREEZE RUN TRACK VEST",
            brand="GLOWNY",
        )

        self.assertEqual(result, StandardCategory.OUTER_VEST)
        self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_musinsa_zip_up_top_maps_to_cardigan(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="상의",
            musinsa_small="집업",
            product_name="G CLASSIC ESSENTIAL RIB ZIP-UP",
            brand="GLOWNY",
        )

        self.assertEqual(result, StandardCategory.TOP_CARDIGAN)
        self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_overalls_fallback_maps_to_jumpsuit(self):
        result, reason = classify_category_with_reason(
            name="THE JANE OVERALLS",
            brand="GLOWNY",
        )

        self.assertEqual(result, StandardCategory.JUMPSUIT)
        self.assertEqual(reason, "overall_keyword_override")

    def test_musinsa_overalls_maps_to_jumpsuit(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="원피스",
            musinsa_small="오버롤",
            product_name="THE JANE OVERALLS",
            brand="GLOWNY",
        )

        self.assertEqual(result, StandardCategory.JUMPSUIT)
        self.assertEqual(meta["reason"], "musinsa_category_override")

    def test_musinsa_digital_category_wins_over_tshirt_keywords(self):
        result, meta = classify_standard_category_from_sheet(
            musinsa_large="여성",
            musinsa_middle="디지털/가전",
            musinsa_small="",
            product_name="GRAPHIC TEE AIRPODS CASE",
            brand="BRAND",
        )

        self.assertEqual(result, StandardCategory.TECH_ACCESSORY)
        self.assertEqual(meta["reason"], "musinsa_category_override")


if __name__ == "__main__":
    unittest.main()
