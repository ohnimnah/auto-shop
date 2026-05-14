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
        self.assertEqual(classify_category("logo beanie", ""), StandardCategory.ACC_BEANIE)
        self.assertEqual(classify_category("leather belt", ""), StandardCategory.ACC_BELT)
        self.assertEqual(classify_category("padded waist belt", ""), StandardCategory.ACC_BELT)
        self.assertEqual(classify_category("보정 벨트", ""), StandardCategory.ACC_BELT)
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
        self.assertEqual(classify_category("리브레 CF(1073A073100) 인도어화", "아식스"), StandardCategory.SHOES_SNEAKER)

    def test_category_classification_from_unresolved_log_terms(self):
        self.assertEqual(classify_category("무드먼트 피그먼트 롱슬리브", "벤힛"), StandardCategory.TOP_LONG_SLEEVE)
        self.assertEqual(classify_category("로고 베이직 슬리브리스 (그레이)", "탄산마그네슘"), StandardCategory.TOP_TANK)
        self.assertEqual(classify_category("NEW HALTER NECK LACE SLEEVELESS_GREY", "오버듀플레어"), StandardCategory.TOP_TANK)
        self.assertEqual(classify_category("홀스슈 아플리케 팬츠 (블랙)", "탄산마그네슘"), StandardCategory.PANTS_REGULAR)
        self.assertEqual(classify_category("코튼 와이드 카고 팬츠 (브라운)", "탄산마그네슘"), StandardCategory.PANTS_CARGO)
        self.assertEqual(classify_category("프로스 밴드 스웻팬츠 (BLACK) F26QD158", "팬시클럽"), StandardCategory.PANTS_TRAINING)
        self.assertEqual(classify_category("스튜디오할 로퍼 2color", "모그어스"), StandardCategory.SHOES_LOAFER)
        self.assertEqual(classify_category("[:DOT EDITION] 로미타 플랫폼 밴딩 도트 메리제인 슈즈 FLOTGA1W85", "오찌"), StandardCategory.SHOES_FLAT)
        self.assertEqual(classify_category("이클립스 라이트팩 15/20L (4 color)", "헬리녹스 웨어"), StandardCategory.BAG_BACKPACK)
        self.assertEqual(classify_category("스탬프 패치 데이 팩 (Blue)", "엔조 블루스"), StandardCategory.BAG_BACKPACK)
        self.assertEqual(classify_category("믹스 체크 머플러 (Sky)", "엔조 블루스"), StandardCategory.ACC_SCARF)
        self.assertEqual(classify_category("버드 헤드 토크", "아크테릭스"), StandardCategory.ACC_BEANIE)
        self.assertEqual(classify_category("보메로 18", "나이키"), StandardCategory.SHOES_SNEAKER)
        self.assertEqual(classify_category("LD-1000 프리미엄", "나이키"), StandardCategory.SHOES_SNEAKER)


if __name__ == "__main__":
    unittest.main()
