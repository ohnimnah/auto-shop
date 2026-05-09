"""Keyword-based correction layer for BUYMA category labels.

Important:
- This module does NOT replace existing 1:1 mapping logic.
- It only applies additive keyword corrections on top of ``base_category``.
- If ``base_category`` is already a precise category (e.g. sunglasses), keep it.
"""

from __future__ import annotations


EYEWEAR_KEYWORDS = ["선글라스", "썬글라스", "안경", "sunglasses", "eyewear", "glasses"]
BEANIE_KEYWORDS = ["비니", "beanie", "니트 모자", "watch cap"]
CAP_KEYWORDS = ["캡", "볼캡", "baseball cap", "ball cap", "cap"]

HOODIE_KEYWORDS = ["후드", "hoodie", "hooded", "zip hoodie"]
PAJAMA_KEYWORDS = ["파자마", "잠옷", "pajama", "sleepwear", "loungewear"]
SWEAT_KEYWORDS = ["맨투맨", "스웻", "스웨트", "sweatshirt"]
TSHIRT_KEYWORDS = ["티셔츠", "반팔", "긴팔", "t-shirt", "tee"]
SHIRT_KEYWORDS = ["셔츠", "남방", "button-down"]
KNIT_KEYWORDS = ["니트", "스웨터", "knit", "sweater"]
CARDIGAN_KEYWORDS = ["가디건", "cardigan"]
DENIM_KEYWORDS = ["데님", "청바지", "jeans", "denim"]
SLACKS_KEYWORDS = ["슬랙스", "정장바지", "trousers"]
SHORTS_KEYWORDS = ["반바지", "쇼츠", "shorts"]
SKIRT_KEYWORDS = ["스커트", "치마", "skirt"]
DRESS_KEYWORDS = ["원피스", "드레스", "dress"]
JACKET_KEYWORDS = ["재킷", "자켓", "jacket"]
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
    """Return final corrected BUYMA category string."""
    base = _to_text(base_category).strip()
    product = _to_text(product_name).strip().lower()
    musinsa = _to_text(musinsa_category).strip().lower()
    text = f"{product} {musinsa}"

    # Keep already-correct eyewear categories as-is.
    if "サングラス" in base:
        return base

    # Hard guardrail for eyewear tokens.
    if _contains_any(text, EYEWEAR_KEYWORDS):
        return "メンズファッション > ファッション雑貨・小物 > サングラス"

    # Hat guardrails for known troublesome cases.
    if _contains_any(text, BEANIE_KEYWORDS):
        return "メンズファッション > 帽子 > ニットキャップ・ビーニー"
    if _contains_any(text, CAP_KEYWORDS):
        return "メンズファッション > 帽子 > キャップ"

    # Generic clothing/accessory fallback rules.
    if _contains_any(text, PAJAMA_KEYWORDS):
        return "インナー・ルームウェア > ルームウェア・パジャマ"
    if _contains_any(text, HOODIE_KEYWORDS):
        return "トップス > パーカー・フーディ"
    if _contains_any(text, DOWN_KEYWORDS):
        return "アウター・ジャケット > ダウンジャケット"
    if _contains_any(text, SHIRT_KEYWORDS):
        return "トップス > シャツ"
    if _contains_any(text, SWEAT_KEYWORDS):
        return "トップス > スウェット・トレーナー"
    if _contains_any(text, TSHIRT_KEYWORDS):
        return "トップス > Tシャツ・カットソー"
    if _contains_any(text, KNIT_KEYWORDS):
        return "トップス > ニット・セーター"
    if _contains_any(text, CARDIGAN_KEYWORDS):
        return "トップス > カーディガン"
    if _contains_any(text, DENIM_KEYWORDS):
        return "パンツ > デニム・ジーンズ"
    if _contains_any(text, SLACKS_KEYWORDS):
        return "パンツ > スラックス"
    if _contains_any(text, SHORTS_KEYWORDS):
        return "パンツ > ハーフ・ショートパンツ"
    if _contains_any(text, SKIRT_KEYWORDS):
        return "スカート"
    if _contains_any(text, DRESS_KEYWORDS):
        return "ワンピース・オールインワン"
    if _contains_any(text, JACKET_KEYWORDS):
        return "アウター・ジャケット > ジャケット"
    if _contains_any(text, COAT_KEYWORDS):
        return "アウター・ジャケット > コート"
    if _contains_any(text, SNEAKER_KEYWORDS):
        return "靴・ブーツ・サンダル > スニーカー"
    if _contains_any(text, SANDAL_KEYWORDS):
        return "靴・ブーツ・サンダル > サンダル"
    if _contains_any(text, BOOT_KEYWORDS):
        return "靴・ブーツ・サンダル > ブーツ"
    if _contains_any(text, BACKPACK_KEYWORDS):
        return "バッグ・カバン > バックパック・リュック"
    if _contains_any(text, BAG_KEYWORDS):
        return "バッグ・カバン > バッグ"

    return base
