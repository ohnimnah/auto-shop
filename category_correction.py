"""Keyword-based correction layer for BUYMA child-category labels."""

from __future__ import annotations


EYEWEAR_KEYWORDS = ["선글라스", "썬글라스", "안경", "sunglasses", "eyewear", "glasses"]
BEANIE_KEYWORDS = ["비니", "beanie", "니트 모자", "watch cap"]
CAP_KEYWORDS = ["캡", "볼캡", "baseball cap", "ball cap", "cap"]

BRA_KEYWORDS = ["브라", "bra", "bralette", "브라렛"]
PANTY_KEYWORDS = ["팬티", "panty", "panties", "쇼츠", "속바지"]
BRA_SET_KEYWORDS = ["브라팬티세트", "브라 세트", "bra set", "bra&shorts", "bra and shorts"]
SLIP_CAMI_KEYWORDS = ["슬립", "캐미", "캐미솔", "camisole", "cami", "inner camisole"]
SPATS_LEGGINGS_KEYWORDS = ["레깅스", "leggings", "스패츠", "속바지", "보정레깅스"]
TIGHTS_SOCKS_KEYWORDS = ["타이즈", "스타킹", "양말", "삭스", "tights", "socks", "sock"]
UNDERWEAR_KEYWORDS = [
    "속옷", "언더웨어", "이너웨어", "속바지", "브라", "팬티",
    "underwear", "innerwear", "inner", "bra", "panty", "panties", "seamless",
]
PAJAMA_KEYWORDS = ["파자마", "잠옷", "pajama", "sleepwear", "loungewear", "homewear", "홈웨어"]

HOODIE_KEYWORDS = ["후드", "hoodie", "hooded", "zip hoodie"]
SWEAT_KEYWORDS = ["맨투맨", "스웻", "스웨트", "sweatshirt", "sweat shirt", "sweatshirts"]
TSHIRT_KEYWORDS = ["티셔츠", "반팔", "긴팔", "t-shirt", "tee"]
BLOUSE_KEYWORDS = ["블라우스", "브라우스", "blouse"]
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
    return "" if value is None else str(value)


def _contains_any(text: str, keywords: list[str]) -> bool:
    return bool(text) and any(keyword in text for keyword in keywords)


def _has_tshirt_signal(text: str) -> bool:
    return _contains_any(text, ["티셔츠", "t-shirt", "t shirt", "tshirt", "tee", "カットソー"])


def _has_sweat_signal(text: str) -> bool:
    return _contains_any(text, SWEAT_KEYWORDS)


def correct_buyma_category(base_category, product_name, musinsa_category) -> str:
    """Return corrected BUYMA child-category label."""
    base = _to_text(base_category).strip()
    text = f"{_to_text(product_name).strip().lower()} {_to_text(musinsa_category).strip().lower()}"

    if "サングラス" in base or _contains_any(text, EYEWEAR_KEYWORDS):
        return "サングラス"
    if _contains_any(text, BEANIE_KEYWORDS):
        return "ニットキャップ・ビーニー"
    if _contains_any(text, CAP_KEYWORDS):
        return "キャップ"

    # Women innerwear detailed buckets (BUYMA available children).
    if _contains_any(text, BRA_SET_KEYWORDS) or (_contains_any(text, BRA_KEYWORDS) and _contains_any(text, PANTY_KEYWORDS)):
        return "ブラジャー＆ショーツ"
    if _contains_any(text, BRA_KEYWORDS):
        return "ブラジャー"
    if _contains_any(text, PANTY_KEYWORDS):
        return "ショーツ"
    if _contains_any(text, SLIP_CAMI_KEYWORDS):
        return "スリップ・インナー・キャミ"
    if _contains_any(text, SPATS_LEGGINGS_KEYWORDS):
        return "スパッツ・レギンス"
    if _contains_any(text, TIGHTS_SOCKS_KEYWORDS):
        return "タイツ・ソックス"
    if _contains_any(text, UNDERWEAR_KEYWORDS):
        return "インナー・ルームウェアその他"
    if _contains_any(text, PAJAMA_KEYWORDS):
        return "ルームウェア・パジャマ"

    if _contains_any(text, HOODIE_KEYWORDS):
        return "パーカー・フーディ"
    if _contains_any(text, DOWN_KEYWORDS):
        return "ダウンジャケット"
    if _has_sweat_signal(text):
        return "スウェット・トレーナー"
    if _contains_any(text, BLOUSE_KEYWORDS):
        return "ブラウス・シャツ"
    if _contains_any(text, SHIRT_KEYWORDS) and not _has_tshirt_signal(text) and not _has_sweat_signal(text):
        return "ブラウス・シャツ"
    if _contains_any(text, TSHIRT_KEYWORDS):
        return "Tシャツ・カットソー"
    if _contains_any(text, KNIT_KEYWORDS):
        return "ニット・セーター"
    if _contains_any(text, CARDIGAN_KEYWORDS):
        return "カーディガン"
    if _contains_any(text, DENIM_KEYWORDS):
        return "デニム・ジーンズ"
    if _contains_any(text, SLACKS_KEYWORDS):
        return "スラックス"
    if _contains_any(text, SHORTS_KEYWORDS):
        return "ハーフ・ショートパンツ"
    if _contains_any(text, SKIRT_KEYWORDS):
        return "スカート"
    if _contains_any(text, DRESS_KEYWORDS):
        return "ワンピース・オールインワン"
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
        return "バックパック・リュック"
    if _contains_any(text, BAG_KEYWORDS):
        return "バッグ"

    return base
