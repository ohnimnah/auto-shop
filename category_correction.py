"""Keyword-based correction layer for BUYMA category labels.

Important:
- This module does NOT replace existing 1:1 mapping logic.
- It only applies additive keyword corrections on top of base_category.
"""

from __future__ import annotations


HOODIE_KEYWORDS = ["후드", "후디", "후드티", "hoodie", "hooded", "zip hoodie"]
PAJAMA_KEYWORDS = ["파자마", "잠옷", "룸웨어", "홈웨어", "라운지웨어", "pajama", "sleepwear", "loungewear"]
SWEAT_KEYWORDS = ["맨투맨", "스웨트", "스웻", "sweatshirt"]
TSHIRT_KEYWORDS = ["티셔츠", "반팔", "긴팔", "t-shirt", "tee"]
SHIRT_KEYWORDS = ["셔츠", "남방", "button-down"]
KNIT_KEYWORDS = ["니트", "스웨터", "knit", "sweater"]
CARDIGAN_KEYWORDS = ["가디건", "cardigan"]
DENIM_KEYWORDS = ["데님", "청바지", "jeans", "denim"]
SLACKS_KEYWORDS = ["슬랙스", "정장바지", "trousers"]
SHORTS_KEYWORDS = ["반바지", "쇼츠", "shorts"]
SKIRT_KEYWORDS = ["스커트", "치마", "skirt"]
DRESS_KEYWORDS = ["원피스", "드레스", "dress"]
JACKET_KEYWORDS = ["자켓", "재킷", "jacket"]
COAT_KEYWORDS = ["코트", "coat"]
DOWN_KEYWORDS = ["패딩", "다운", "down jacket", "puffer"]
SNEAKER_KEYWORDS = ["스니커즈", "운동화", "sneakers"]
SANDAL_KEYWORDS = ["샌들", "슬리퍼", "sandals", "slides"]
BOOT_KEYWORDS = ["부츠", "boots"]
BAG_KEYWORDS = ["가방", "백", "bag"]
BACKPACK_KEYWORDS = ["백팩", "배낭", "backpack"]


def _to_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _contains_any(text: str, keywords: list[str]) -> bool:
    if not text:
        return False
    return any(keyword in text for keyword in keywords)


def correct_buyma_category(base_category, product_name, musinsa_category) -> str:
    """Return final corrected BUYMA category string.

    Flow:
    1) Start from existing base_category
    2) Apply rule-based keyword corrections by priority
    3) If no rule matched, return base_category unchanged
    """
    base = _to_text(base_category).strip()
    product = _to_text(product_name).strip().lower()
    musinsa = _to_text(musinsa_category).strip().lower()
    text = f"{product} {musinsa}"

    # Priority order (also resolves conflicts):
    # PAJAMA > HOODIE > SWEAT > TSHIRT > SHIRT > KNIT > CARDIGAN >
    # DENIM > SLACKS > SHORTS > SKIRT > DRESS > JACKET > COAT > DOWN >
    # SNEAKER > SANDAL > BOOT > BACKPACK > BAG
    # Explicit conflict notes:
    # - PAJAMA overrides everything
    # - HOODIE overrides SWEAT
    # - DOWN overrides JACKET
    # - SHIRT overrides TSHIRT
    #
    # To satisfy DOWN > JACKET and SHIRT > TSHIRT, we evaluate DOWN and SHIRT
    # before their lower-priority counterparts.

    if _contains_any(text, PAJAMA_KEYWORDS):
        return "ルームウェア・パジャマ"

    if _contains_any(text, HOODIE_KEYWORDS):
        return "パーカー・フーディ"

    if _contains_any(text, DOWN_KEYWORDS):
        return "ダウンジャケット"

    if _contains_any(text, SHIRT_KEYWORDS):
        return "シャツ"

    if _contains_any(text, SWEAT_KEYWORDS):
        return "スウェット・トレーナー"

    if _contains_any(text, TSHIRT_KEYWORDS):
        return "Tシャツ・カットソー"

    if _contains_any(text, KNIT_KEYWORDS):
        return "ニット・セーター"

    if _contains_any(text, CARDIGAN_KEYWORDS):
        return "カーディガン"

    if _contains_any(text, DENIM_KEYWORDS):
        return "デニム・ジーパン"

    if _contains_any(text, SLACKS_KEYWORDS):
        return "スラックス"

    if _contains_any(text, SHORTS_KEYWORDS):
        return "ハーフ・ショートパンツ"

    if _contains_any(text, SKIRT_KEYWORDS):
        return "スカート"

    if _contains_any(text, DRESS_KEYWORDS):
        return "ワンピース"

    if _contains_any(text, JACKET_KEYWORDS):
        return "ジャケット"

    if _contains_any(text, COAT_KEYWORDS):
        return "コート"

    if _contains_any(text, SNEAKER_KEYWORDS):
        return "スニーカー"

    if _contains_any(text, SANDAL_KEYWORDS):
        return "サンダル"

    if _contains_any(text, BOOT_KEYWORDS):
        return "ブーツ"

    if _contains_any(text, BACKPACK_KEYWORDS):
        return "バックパック"

    if _contains_any(text, BAG_KEYWORDS):
        return "ショルダーバッグ"

    return base

