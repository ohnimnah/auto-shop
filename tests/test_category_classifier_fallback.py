import unittest

from marketplace.buyma.standard_category import StandardCategory
from marketplace.common.category_classifier import classify_category, normalize_product_name


class CategoryClassifierFallbackTests(unittest.TestCase):
    def test_normalize_product_name(self):
        self.assertEqual(
            normalize_product_name("1+1 심리스 이너프리 브라 (무료배송)"),
            "심리스 이너프리 브라",
        )
        self.assertEqual(
            normalize_product_name("[정품] 카인다미 홈웨어 세트"),
            "카인다미 홈웨어 세트",
        )

    def test_category_classification_short_sleeve(self):
        result = classify_category("나이키 반팔 티셔츠", "NIKE")
        self.assertEqual(result, StandardCategory.TOP_TSHIRT)

    def test_category_classification_jogger(self):
        result = classify_category("아디다스 조거 팬츠", "ADIDAS")
        self.assertEqual(result, StandardCategory.PANTS_JOGGER)

    def test_category_classification_expanded_rules(self):
        self.assertEqual(classify_category("MICHIKO LONDON K 원피스 블랙", ""), StandardCategory.DRESS)
        self.assertEqual(classify_category("WOOL CARDIGAN", ""), StandardCategory.TOP_CARDIGAN)
        self.assertEqual(classify_category("basic knit sweater", ""), StandardCategory.TOP_KNIT)
        self.assertEqual(classify_category("cotton shirt", ""), StandardCategory.TOP_SHIRT)
        self.assertEqual(classify_category("long coat", ""), StandardCategory.OUTER_COAT)
        self.assertEqual(classify_category("down jacket puffer", ""), StandardCategory.OUTER_PADDING)
        self.assertEqual(classify_category("crossbody bag", ""), StandardCategory.BAG_SHOULDER)
        self.assertEqual(classify_category("logo beanie", ""), StandardCategory.ACC_CAP)
        self.assertEqual(classify_category("leather belt", ""), StandardCategory.ACC_BELT)
        self.assertEqual(classify_category("black sunglasses", ""), StandardCategory.ACC_EYEWEAR)
        self.assertEqual(classify_category("sports socks", ""), StandardCategory.INNER_UNDERWEAR)
        self.assertEqual(classify_category("심리스 이너프리 브라", "카인다미"), StandardCategory.INNER_UNDERWEAR)
        self.assertEqual(classify_category("골반뽕 볼륨업 보정속옷", "KINDAME"), StandardCategory.INNER_UNDERWEAR)
        self.assertIn(
            classify_category("홈웨어 파자마 세트", ""),
            (StandardCategory.HOME_PAJAMA, StandardCategory.INNER_UNDERWEAR),
        )
        self.assertEqual(classify_category("하이웨스트 레깅스", ""), StandardCategory.PANTS_LEGGINGS)
        self.assertEqual(classify_category("골반뽕 힙업 팬티", ""), StandardCategory.INNER_UNDERWEAR)
        self.assertEqual(classify_category("심리스 이너프리 브라", ""), StandardCategory.INNER_UNDERWEAR)
        self.assertEqual(classify_category("홈웨어 파자마 세트", ""), StandardCategory.HOME_PAJAMA)
        self.assertEqual(classify_category("심리스브라", ""), StandardCategory.INNER_UNDERWEAR)
        self.assertEqual(classify_category("sports bra", ""), StandardCategory.INNER_UNDERWEAR)
        self.assertEqual(classify_category("innerfree bra", ""), StandardCategory.INNER_UNDERWEAR)


if __name__ == "__main__":
    unittest.main()
