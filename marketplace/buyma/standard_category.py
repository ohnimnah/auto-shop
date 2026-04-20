"""Semantic StandardCategory resolver for BUYMA category correction layer."""

from __future__ import annotations

from enum import Enum
from typing import List, Tuple


class StandardCategory(str, Enum):
    TOP_HOODIE = "TOP_HOODIE"
    TOP_SWEAT = "TOP_SWEAT"
    TOP_TSHIRT = "TOP_TSHIRT"
    TOP_SHIRT = "TOP_SHIRT"
    TOP_KNIT = "TOP_KNIT"
    TOP_CARDIGAN = "TOP_CARDIGAN"
    OUTER = "OUTER"
    PANTS = "PANTS"
    HOME_PAJAMA = "HOME_PAJAMA"
    ETC = "ETC"


HOME_PAJAMA_KEYWORDS = [
    "파자마", "잠옷", "룸웨어", "홈웨어", "라운지웨어",
    "pajama", "sleepwear", "loungewear",
]
TOP_HOODIE_KEYWORDS = ["후드", "후디", "후드티", "hoodie", "hooded", "zip hoodie"]
TOP_SWEAT_KEYWORDS = ["맨투맨", "스웨트", "스웻", "sweatshirt"]
TOP_SHIRT_KEYWORDS = ["셔츠", "남방", "button-down", "shirt"]
TOP_TSHIRT_KEYWORDS = ["티셔츠", "반팔", "긴팔", "t-shirt", "tee"]
TOP_KNIT_KEYWORDS = ["니트", "스웨터", "knit", "sweater"]
TOP_CARDIGAN_KEYWORDS = ["가디건", "cardigan"]
OUTER_KEYWORDS = [
    "자켓", "재킷", "jacket",
    "코트", "coat",
    "패딩", "다운", "down jacket", "puffer",
    "바람막이", "windbreaker",
]
PANTS_KEYWORDS = [
    "팬츠", "바지",
    "슬랙스", "trousers", "slacks",
    "데님", "청바지", "jeans", "denim",
    "쇼츠", "반바지", "shorts",
]

OUTER_DOWN_KEYWORDS = ["down jacket", "puffer", "패딩", "다운"]
OUTER_COAT_KEYWORDS = ["coat", "코트"]
PANTS_DENIM_KEYWORDS = ["denim", "jeans", "데님", "청바지"]
PANTS_SLACKS_KEYWORDS = ["slacks", "trousers", "슬랙스"]
PANTS_SHORTS_KEYWORDS = ["shorts", "쇼츠", "반바지"]


def _normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.lower().strip()
    for token in ("|", "/", "\\", ",", ";", "_", "-", "(", ")", "[", "]"):
        text = text.replace(token, " ")
    return " ".join(text.split())


def _contains_any(text: str, keywords: List[str]) -> bool:
    if not text:
        return False
    return any(keyword.lower() in text for keyword in keywords)


def build_combined_text(
    musinsa_large: str,
    musinsa_middle: str,
    musinsa_small: str,
    product_name: str,
) -> str:
    return _normalize_text(
        " ".join([
            musinsa_large or "",
            musinsa_middle or "",
            musinsa_small or "",
            product_name or "",
        ])
    )


def resolve_standard_category(
    musinsa_large: str,
    musinsa_middle: str,
    musinsa_small: str,
    product_name: str,
) -> Tuple[StandardCategory, str]:
    """Resolve semantic category from Musinsa category text + product name."""
    text = build_combined_text(musinsa_large, musinsa_middle, musinsa_small, product_name)
    if not text:
        return StandardCategory.ETC, text

    # Priority:
    # HOME_PAJAMA > TOP_HOODIE > TOP_SWEAT > TOP_SHIRT > TOP_TSHIRT >
    # TOP_KNIT > TOP_CARDIGAN > OUTER > PANTS > ETC
    if _contains_any(text, HOME_PAJAMA_KEYWORDS):
        return StandardCategory.HOME_PAJAMA, text
    if _contains_any(text, TOP_HOODIE_KEYWORDS):
        return StandardCategory.TOP_HOODIE, text
    if _contains_any(text, TOP_SWEAT_KEYWORDS):
        return StandardCategory.TOP_SWEAT, text
    if _contains_any(text, TOP_SHIRT_KEYWORDS):
        return StandardCategory.TOP_SHIRT, text
    if _contains_any(text, TOP_TSHIRT_KEYWORDS):
        return StandardCategory.TOP_TSHIRT, text
    if _contains_any(text, TOP_KNIT_KEYWORDS):
        return StandardCategory.TOP_KNIT, text
    if _contains_any(text, TOP_CARDIGAN_KEYWORDS):
        return StandardCategory.TOP_CARDIGAN, text
    if _contains_any(text, OUTER_KEYWORDS):
        return StandardCategory.OUTER, text
    if _contains_any(text, PANTS_KEYWORDS):
        return StandardCategory.PANTS, text
    return StandardCategory.ETC, text


def map_standard_to_buyma_middle_and_subcategory(
    standard_category: StandardCategory,
    combined_text: str,
    *,
    is_mens: bool = False,
) -> Tuple[str, str]:
    """Return (buyma_middle_category, buyma_sub_category)."""
    text = _normalize_text(combined_text)

    if standard_category == StandardCategory.TOP_HOODIE:
        return "トップス", "パーカー・フーディ"
    if standard_category == StandardCategory.TOP_SWEAT:
        return "トップス", "スウェット・トレーナー"
    if standard_category == StandardCategory.TOP_TSHIRT:
        return "トップス", "Tシャツ・カットソー"
    if standard_category == StandardCategory.TOP_SHIRT:
        return "トップス", "シャツ"
    if standard_category == StandardCategory.TOP_KNIT:
        return "トップス", "ニット・セーター"
    if standard_category == StandardCategory.TOP_CARDIGAN:
        return "トップス", "カーディガン"
    if standard_category == StandardCategory.HOME_PAJAMA:
        return "インナー・ルームウェア", "ルームウェア・パジャマ"

    if standard_category == StandardCategory.OUTER:
        outer_mid = "アウター・ジャケット" if is_mens else "アウター"
        if _contains_any(text, OUTER_DOWN_KEYWORDS):
            return outer_mid, "ダウンジャケット"
        if _contains_any(text, OUTER_COAT_KEYWORDS):
            return outer_mid, "コート"
        return outer_mid, "ジャケット"

    if standard_category == StandardCategory.PANTS:
        pants_mid = "パンツ・ボトムス" if is_mens else "ボトムス"
        if _contains_any(text, PANTS_DENIM_KEYWORDS):
            return pants_mid, "デニム・ジーパン"
        if _contains_any(text, PANTS_SLACKS_KEYWORDS):
            return pants_mid, "スラックス"
        if _contains_any(text, PANTS_SHORTS_KEYWORDS):
            return pants_mid, "ハーフ・ショートパンツ"
        return pants_mid, "パンツ"

    return "", ""
