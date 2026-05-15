import unittest

from category_correction import correct_buyma_category


class CategoryCorrectionTests(unittest.TestCase):
    def test_blouse_does_not_collapse_to_missing_shirt_label(self) -> None:
        result = correct_buyma_category(
            "ブラウス・シャツ",
            "MISTY SHEER BLOUSE",
            "여성 상의 셔츠/블라우스",
        )

        self.assertEqual(result, "ブラウス・シャツ")

    def test_short_sleeve_tshirt_stays_tshirt(self) -> None:
        result = correct_buyma_category(
            "Tシャツ・カットソー",
            "LOGO T-SHIRT",
            "여성 상의 반팔 티셔츠",
        )

        self.assertEqual(result, "Tシャツ・カットソー")

    def test_sweatshirt_does_not_collapse_to_blouse_shirt(self) -> None:
        result = correct_buyma_category(
            "スウェット・トレーナー",
            "소프트 헤비 워싱 오버 핏 스웻 셔츠",
            "여성 상의 맨투맨/스웨트",
        )

        self.assertEqual(result, "スウェット・トレーナー")

    def test_explicit_tshirt_category_is_not_overridden_by_hooded_title(self) -> None:
        result = correct_buyma_category(
            "Tシャツ・カットソー",
            "Lettering Hooded Slim-Fit Long Sleeve Top",
            "여성 상의 긴소매 티셔츠",
        )

        self.assertEqual(result, "Tシャツ・カットソー")


if __name__ == "__main__":
    unittest.main()
