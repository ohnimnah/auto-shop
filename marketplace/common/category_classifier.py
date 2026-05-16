"""Sheet-driven StandardCategory classifier (minimal additive layer).

Reads keyword rules from Google Sheet and returns StandardCategory when matched.
If unavailable or unmatched, caller should fall back to existing resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from config.config_service import load_config as load_profile_config
from marketplace.buyma.standard_category import StandardCategory, build_combined_text
from marketplace.common.runtime import get_runtime_data_dir
from marketplace.common import sheet_source as sheet_source_mod


DEFAULT_CLASSIFIER_SHEET = "source_to_standard_mapping"
_CACHE_TTL_SECONDS = 120
_RULE_CACHE: Dict[str, object] = {
    "loaded_at": None,
    "key": "",
    "rules": [],
}
_LOGGER = logging.getLogger(__name__)
_UNRESOLVED_JSONL_PATH = os.path.join("logs", "category_unresolved.jsonl")
_REMOVE_WORDS = [
    "\ubb34\ub8cc\ubc30\uc1a1", "\ub2f9\uc77c\ucd9c\uace0", "\uc815\ud488", "\uacf5\uc2dd", "1+1", "\uc138\uc77c",
    "\ud2b9\uac00", "\uc774\ubca4\ud2b8", "\ud560\uc778", "\ucd94\ucc9c", "\uc2e0\uc0c1",
]


@dataclass
class ClassificationRule:
    standard_category: StandardCategory
    title_keywords_include: List[str]
    priority: int = 100
    enabled: bool = True


CATEGORY_FALLBACK_RULES: List[Tuple[str, List[str], StandardCategory]] = [
    ("long_sleeve_tshirt", ["긴팔", "롱슬리브", "long sleeve", "longsleeve", "ls tee", "lst"], StandardCategory.TOP_LONG_SLEEVE),
    ("short_sleeve_tshirt", ["반팔", "short sleeve", "t-shirt", "tee"], StandardCategory.TOP_TSHIRT),
    ("sleeveless_top", ["슬리브리스", "민소매", "나시", "sleeveless", "tank", "tank top", "halter", "camisole"], StandardCategory.TOP_TANK),
    ("generic_top", ["세미크롭", "크롭탑", "탑", "top"], StandardCategory.TOP_TSHIRT),
    ("shorts", ["숏팬츠", "반바지", "shorts", "short pants", "half pants"], StandardCategory.PANTS_SHORTS),
    ("denim_pants", ["청바지", "denim", "jeans"], StandardCategory.PANTS_DENIM),
    ("cargo_pants", ["카고", "cargo"], StandardCategory.PANTS_CARGO),
    ("training_pants", ["스웻팬츠", "스웨트팬츠", "트레이닝팬츠", "sweatpants", "sweat pants", "track pants"], StandardCategory.PANTS_TRAINING),
    ("jogger_pants", ["조거", "jogger"], StandardCategory.PANTS_JOGGER),
    ("regular_pants", ["팬츠", "바지", "pants"], StandardCategory.PANTS_REGULAR),
    ("backpack", ["백팩", "데이팩", "데이 팩", "라이트팩", "backpack", "daypack", "rucksack"], StandardCategory.BAG_BACKPACK),
    ("tote_bag", ["토트백", "토트", "tote bag", "tote"], StandardCategory.BAG_TOTE),
    ("crossbody_bag", ["크로스백", "메신저백", "crossbody", "messenger bag", "messenger"], StandardCategory.BAG_CROSSBODY),
    ("wallet", ["지갑", "카드지갑", "카드 홀더", "카드홀더", "wallet", "card holder"], StandardCategory.BAG_WALLET),
    ("sneakers", ["sneakers", "sneaker", "운동화", "스니커즈"], StandardCategory.SHOES_SNEAKER),
    ("sneaker_models", ["보메로", "vomero", "올드스쿨", "old skool", "oldskool", "컴피쿠시", "comfycush", "ld 1000", "ld-1000"], StandardCategory.SHOES_SNEAKER),
    ("sports_shoes", ["인도어화", "스포츠화", "코트화", "풋살화", "배드민턴화", "핸드볼화"], StandardCategory.SHOES_SNEAKER),
    ("mary_jane", ["메리제인", "mary jane"], StandardCategory.SHOES_FLAT),
    ("sandals", ["슬리퍼", "샌들", "sandal", "slide"], StandardCategory.SHOES_SANDAL),
    ("sweat_top", ["맨투맨", "스웻 셔츠", "스웨트 셔츠", "sweatshirt", "sweat shirt"], StandardCategory.TOP_SWEAT),
    ("hoodie", ["hoodie", "후드", "후디"], StandardCategory.TOP_HOODIE),
    ("dress", ["dress", "드레스", "원피스"], StandardCategory.DRESS),
    ("jumpsuit_overalls", ["점프수트", "오버롤", "오버롤즈", "jumpsuit", "overall", "overalls", "salopette"], StandardCategory.JUMPSUIT),
    ("skirt", ["skirt", "스커트"], StandardCategory.SKIRT_LONG),
    ("top_vest", ["니트베스트", "니트 베스트", "knit vest"], StandardCategory.TOP_VEST),
    ("outer_vest", ["트랙 베스트", "러닝 베스트", "패딩조끼", "다운 베스트", "track vest", "running vest", "puffer vest", "down vest"], StandardCategory.OUTER_VEST),
    ("cardigan", ["cardigan", "가디건", "집업", "zip-up", "zip up", "zipup"], StandardCategory.TOP_CARDIGAN),
    ("knit", ["knit", "sweater", "니트", "스웨터"], StandardCategory.TOP_KNIT),
    ("shirt_blouse", ["shirt", "blouse", "셔츠", "블라우스"], StandardCategory.TOP_SHIRT),
    ("coat", ["coat", "코트"], StandardCategory.OUTER_COAT),
    ("padding", ["padding", "puffer", "down jacket", "패딩"], StandardCategory.OUTER_PADDING),
    ("jacket", ["jacket", "jumper", "blouson", "자켓", "재킷", "점퍼"], StandardCategory.OUTER_JACKET),
    ("bag", ["shoulder bag", "숄더백", "bag", "백"], StandardCategory.BAG_SHOULDER),
    ("tech_accessory", ["디지털", "가전", "digital", "electronics", "tech accessory", "phone case", "airpods", "에어팟", "폰케이스"], StandardCategory.TECH_ACCESSORY),
    ("beanie", ["beanie", "비니", "니트모자", "토크", "toque"], StandardCategory.ACC_BEANIE),
    ("cap", ["baseball cap", "ball cap", "cap", "캡", "볼캡"], StandardCategory.ACC_CAP),
    ("hat", ["bucket hat", "hat", "버킷햇", "모자"], StandardCategory.ACC_HAT),
    ("belt", ["belt", "벨트"], StandardCategory.ACC_BELT),
    ("scarf", ["머플러", "스카프", "muffler", "scarf"], StandardCategory.ACC_SCARF),
    ("sunglasses", ["sunglasses", "선글라스", "썬글라스"], StandardCategory.ACC_EYEWEAR),
    ("watch", ["watch", "시계"], StandardCategory.ACC_WATCH),
    ("jewelry", ["necklace", "ring", "earring", "bracelet", "목걸이", "반지", "귀걸이", "팔찌"], StandardCategory.ACC_JEWELRY),
    ("socks", ["socks", "sock", "knee socks", "양말", "삭스", "레그웨어"], StandardCategory.ACC_SOCKS),
    ("swimwear", ["수영복", "비치웨어", "비키니", "bikini", "swimsuit", "swimwear", "beachwear"], StandardCategory.SWIMWEAR),
    ("homewear", ["홈웨어", "homewear", "lounge wear", "loungewear", "잠옷", "파자마", "pajama"], StandardCategory.HOME_PAJAMA),
    ("innerwear", ["이너", "이너프리", "inner", "innerwear", "underwear", "속옷", "속바지", "브라", "bra", "팬티", "panty", "panties", "padded"], StandardCategory.INNER_UNDERWEAR),
    ("seamless_innerwear", ["심리스", "seamless", "seamless inner", "심리스 이너"], StandardCategory.INNER_UNDERWEAR),
    ("leggings", ["레깅스", "leggings", "legging"], StandardCategory.PANTS_LEGGINGS),
    ("loafer", ["로퍼", "loafer"], StandardCategory.SHOES_LOAFER),
]

FORCE_CATEGORY_MAP: Dict[Tuple[str, ...], StandardCategory] = {
    ("골반뽕", "힙업", "볼륨업", "보정", "보정속옷", "shaper", "shapewear"): StandardCategory.INNER_UNDERWEAR,
    ("심리스", "seamless", "심리스브라", "seamlessbra"): StandardCategory.INNER_UNDERWEAR,
    ("이너프리", "innerfree", "inner", "이너", "innerwear", "underwear"): StandardCategory.INNER_UNDERWEAR,
    ("bra", "브라", "sports bra", "sportsbra", "padded", "panty", "panties", "팬티"): StandardCategory.INNER_UNDERWEAR,
    ("홈웨어", "homewear", "잠옷", "파자마", "pajama", "loungewear", "lounge wear"): StandardCategory.HOME_PAJAMA,
    ("인도어화", "스포츠화", "코트화", "풋살화", "배드민턴화", "핸드볼화", "실내화"): StandardCategory.SHOES_SNEAKER,
}

MUSINSA_CATEGORY_OVERRIDES: List[Tuple[Tuple[str, ...], StandardCategory]] = [
    (("디지털",), StandardCategory.TECH_ACCESSORY),
    (("가전",), StandardCategory.TECH_ACCESSORY),
    (("digital",), StandardCategory.TECH_ACCESSORY),
    (("electronics",), StandardCategory.TECH_ACCESSORY),
    (("소품", "양말"), StandardCategory.ACC_SOCKS),
    (("소품", "레그웨어"), StandardCategory.ACC_SOCKS),
    (("양말",), StandardCategory.ACC_SOCKS),
    (("레그웨어",), StandardCategory.ACC_SOCKS),
    (("socks",), StandardCategory.ACC_SOCKS),
    (("sock",), StandardCategory.ACC_SOCKS),
    (("legwear",), StandardCategory.ACC_SOCKS),
    (("수영복",), StandardCategory.SWIMWEAR),
    (("비치웨어",), StandardCategory.SWIMWEAR),
    (("비키니",), StandardCategory.SWIMWEAR),
    (("bikini",), StandardCategory.SWIMWEAR),
    (("swimsuit",), StandardCategory.SWIMWEAR),
    (("swimwear",), StandardCategory.SWIMWEAR),
    (("beachwear",), StandardCategory.SWIMWEAR),
    (("아우터", "패딩"), StandardCategory.OUTER_PADDING),
    (("아우터", "다운"), StandardCategory.OUTER_PADDING),
    (("아우터", "puffer"), StandardCategory.OUTER_PADDING),
    (("아우터", "padding"), StandardCategory.OUTER_PADDING),
    (("아우터", "코트"), StandardCategory.OUTER_COAT),
    (("아우터", "coat"), StandardCategory.OUTER_COAT),
    (("아우터", "트렌치"), StandardCategory.OUTER_TRENCH),
    (("아우터", "trench"), StandardCategory.OUTER_TRENCH),
    (("아우터", "블레이저"), StandardCategory.OUTER_BLAZER),
    (("아우터", "blazer"), StandardCategory.OUTER_BLAZER),
    (("아우터", "데님"), StandardCategory.OUTER_DENIM_JACKET),
    (("아우터", "denim jacket"), StandardCategory.OUTER_DENIM_JACKET),
    (("아우터", "레더"), StandardCategory.OUTER_LEATHER_JACKET),
    (("아우터", "leather"), StandardCategory.OUTER_LEATHER_JACKET),
    (("아우터", "바람막이"), StandardCategory.OUTER_WINDBREAKER),
    (("아우터", "윈드브레이커"), StandardCategory.OUTER_WINDBREAKER),
    (("아우터", "windbreaker"), StandardCategory.OUTER_WINDBREAKER),
    (("아우터", "플리스"), StandardCategory.OUTER_FLEECE),
    (("아우터", "fleece"), StandardCategory.OUTER_FLEECE),
    (("아우터", "베스트"), StandardCategory.OUTER_VEST),
    (("아우터", "조끼"), StandardCategory.OUTER_VEST),
    (("아우터", "vest"), StandardCategory.OUTER_VEST),
    (("아우터", "집업"), StandardCategory.OUTER_JACKET),
    (("아우터", "zip up"), StandardCategory.OUTER_JACKET),
    (("아우터", "zip-up"), StandardCategory.OUTER_JACKET),
    (("아우터", "자켓"), StandardCategory.OUTER_JACKET),
    (("아우터", "재킷"), StandardCategory.OUTER_JACKET),
    (("아우터", "점퍼"), StandardCategory.OUTER_JACKET),
    (("아우터", "jacket"), StandardCategory.OUTER_JACKET),
    (("아우터", "jumper"), StandardCategory.OUTER_JACKET),
    (("스포츠 레저", "아우터"), StandardCategory.OUTER_JACKET),
    (("스포츠 레저", "베스트"), StandardCategory.OUTER_VEST),
    (("스포츠 레저", "조끼"), StandardCategory.OUTER_VEST),
    (("스포츠 레저", "vest"), StandardCategory.OUTER_VEST),
    (("outer", "jacket"), StandardCategory.OUTER_JACKET),
    (("outer", "jumper"), StandardCategory.OUTER_JACKET),
    (("상의", "맨투맨"), StandardCategory.TOP_SWEAT),
    (("상의", "스웻"), StandardCategory.TOP_SWEAT),
    (("상의", "스웨트"), StandardCategory.TOP_SWEAT),
    (("상의", "sweatshirt"), StandardCategory.TOP_SWEAT),
    (("상의", "sweat shirt"), StandardCategory.TOP_SWEAT),
    (("상의", "티셔츠"), StandardCategory.TOP_TSHIRT),
    (("상의", "t shirt"), StandardCategory.TOP_TSHIRT),
    (("상의", "t-shirt"), StandardCategory.TOP_TSHIRT),
    (("상의", "tee"), StandardCategory.TOP_TSHIRT),
    (("상의", "블라우스"), StandardCategory.TOP_BLOUSE),
    (("상의", "브라우스"), StandardCategory.TOP_BLOUSE),
    (("상의", "blouse"), StandardCategory.TOP_BLOUSE),
    (("상의", "셔츠"), StandardCategory.TOP_SHIRT),
    (("상의", "남방"), StandardCategory.TOP_SHIRT),
    (("상의", "shirt"), StandardCategory.TOP_SHIRT),
    (("상의", "긴팔"), StandardCategory.TOP_LONG_SLEEVE),
    (("상의", "롱슬리브"), StandardCategory.TOP_LONG_SLEEVE),
    (("상의", "long sleeve"), StandardCategory.TOP_LONG_SLEEVE),
    (("상의", "반팔"), StandardCategory.TOP_TSHIRT),
    (("상의", "니트"), StandardCategory.TOP_KNIT),
    (("상의", "스웨터"), StandardCategory.TOP_KNIT),
    (("상의", "knit"), StandardCategory.TOP_KNIT),
    (("상의", "sweater"), StandardCategory.TOP_KNIT),
    (("상의", "후드"), StandardCategory.TOP_HOODIE),
    (("상의", "후디"), StandardCategory.TOP_HOODIE),
    (("상의", "hoodie"), StandardCategory.TOP_HOODIE),
    (("상의", "슬리브리스"), StandardCategory.TOP_TANK),
    (("상의", "민소매"), StandardCategory.TOP_TANK),
    (("상의", "나시"), StandardCategory.TOP_TANK),
    (("상의", "sleeveless"), StandardCategory.TOP_TANK),
    (("상의", "tank"), StandardCategory.TOP_TANK),
    (("상의", "가디건"), StandardCategory.TOP_CARDIGAN),
    (("상의", "cardigan"), StandardCategory.TOP_CARDIGAN),
    (("상의", "집업"), StandardCategory.TOP_CARDIGAN),
    (("상의", "zip up"), StandardCategory.TOP_CARDIGAN),
    (("상의", "zip-up"), StandardCategory.TOP_CARDIGAN),
    (("상의", "베스트"), StandardCategory.TOP_VEST),
    (("상의", "조끼"), StandardCategory.TOP_VEST),
    (("상의", "vest"), StandardCategory.TOP_VEST),
    (("top", "knit"), StandardCategory.TOP_KNIT),
    (("tops", "knit"), StandardCategory.TOP_KNIT),
    (("top", "hoodie"), StandardCategory.TOP_HOODIE),
    (("tops", "hoodie"), StandardCategory.TOP_HOODIE),
    (("top", "shirt"), StandardCategory.TOP_SHIRT),
    (("tops", "shirt"), StandardCategory.TOP_SHIRT),
    (("top", "sleeveless"), StandardCategory.TOP_TANK),
    (("tops", "sleeveless"), StandardCategory.TOP_TANK),
    (("바지", "반바지"), StandardCategory.PANTS_SHORTS),
    (("바지", "숏팬츠"), StandardCategory.PANTS_SHORTS),
    (("바지", "쇼츠"), StandardCategory.PANTS_SHORTS),
    (("바지", "숏츠"), StandardCategory.PANTS_SHORTS),
    (("바지", "쇼트팬츠"), StandardCategory.PANTS_SHORTS),
    (("바지", "하프팬츠"), StandardCategory.PANTS_SHORTS),
    (("바지", "핫팬츠"), StandardCategory.PANTS_SHORTS),
    (("바지", "short"), StandardCategory.PANTS_SHORTS),
    (("바지", "half pants"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "반바지"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "숏팬츠"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "쇼츠"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "숏츠"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "쇼트팬츠"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "하프팬츠"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "핫팬츠"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "short"), StandardCategory.PANTS_SHORTS),
    (("팬츠", "half pants"), StandardCategory.PANTS_SHORTS),
    (("bottom", "short"), StandardCategory.PANTS_SHORTS),
    (("bottoms", "short"), StandardCategory.PANTS_SHORTS),
    (("pants", "short"), StandardCategory.PANTS_SHORTS),
    (("pants", "half pants"), StandardCategory.PANTS_SHORTS),
    (("바지", "팬츠"), StandardCategory.PANTS_REGULAR),
    (("바지", "코튼"), StandardCategory.PANTS_REGULAR),
    (("팬츠", "코튼"), StandardCategory.PANTS_REGULAR),
    (("bottom", "pants"), StandardCategory.PANTS_REGULAR),
    (("bottoms", "pants"), StandardCategory.PANTS_REGULAR),
    (("오버롤",), StandardCategory.JUMPSUIT),
    (("오버롤즈",), StandardCategory.JUMPSUIT),
    (("점프수트",), StandardCategory.JUMPSUIT),
    (("overall",), StandardCategory.JUMPSUIT),
    (("overalls",), StandardCategory.JUMPSUIT),
    (("jumpsuit",), StandardCategory.JUMPSUIT),
    (("악세서리", "선글라스"), StandardCategory.ACC_EYEWEAR),
    (("악세서리", "안경"), StandardCategory.ACC_EYEWEAR),
    (("악세서리", "아이웨어"), StandardCategory.ACC_EYEWEAR),
    (("악세서리", "sunglasses"), StandardCategory.ACC_EYEWEAR),
    (("악세서리", "eyewear"), StandardCategory.ACC_EYEWEAR),
    (("액세서리", "선글라스"), StandardCategory.ACC_EYEWEAR),
    (("액세서리", "안경"), StandardCategory.ACC_EYEWEAR),
    (("액세서리", "아이웨어"), StandardCategory.ACC_EYEWEAR),
    (("액세서리", "sunglasses"), StandardCategory.ACC_EYEWEAR),
    (("액세서리", "eyewear"), StandardCategory.ACC_EYEWEAR),
    (("악세서리", "비니"), StandardCategory.ACC_BEANIE),
    (("악세서리", "토크"), StandardCategory.ACC_BEANIE),
    (("악세서리", "beanie"), StandardCategory.ACC_BEANIE),
    (("악세서리", "toque"), StandardCategory.ACC_BEANIE),
    (("액세서리", "비니"), StandardCategory.ACC_BEANIE),
    (("액세서리", "토크"), StandardCategory.ACC_BEANIE),
    (("액세서리", "beanie"), StandardCategory.ACC_BEANIE),
    (("액세서리", "toque"), StandardCategory.ACC_BEANIE),
    (("악세서리", "캡"), StandardCategory.ACC_CAP),
    (("악세서리", "볼캡"), StandardCategory.ACC_CAP),
    (("악세서리", "cap"), StandardCategory.ACC_CAP),
    (("액세서리", "캡"), StandardCategory.ACC_CAP),
    (("액세서리", "볼캡"), StandardCategory.ACC_CAP),
    (("액세서리", "cap"), StandardCategory.ACC_CAP),
    (("악세서리", "모자"), StandardCategory.ACC_HAT),
    (("악세서리", "버킷햇"), StandardCategory.ACC_HAT),
    (("악세서리", "hat"), StandardCategory.ACC_HAT),
    (("액세서리", "모자"), StandardCategory.ACC_HAT),
    (("액세서리", "버킷햇"), StandardCategory.ACC_HAT),
    (("액세서리", "hat"), StandardCategory.ACC_HAT),
    (("악세서리", "머플러"), StandardCategory.ACC_SCARF),
    (("악세서리", "스카프"), StandardCategory.ACC_SCARF),
    (("악세서리", "muffler"), StandardCategory.ACC_SCARF),
    (("악세서리", "scarf"), StandardCategory.ACC_SCARF),
    (("액세서리", "머플러"), StandardCategory.ACC_SCARF),
    (("액세서리", "스카프"), StandardCategory.ACC_SCARF),
    (("액세서리", "muffler"), StandardCategory.ACC_SCARF),
    (("액세서리", "scarf"), StandardCategory.ACC_SCARF),
    (("악세서리", "벨트"), StandardCategory.ACC_BELT),
    (("악세서리", "belt"), StandardCategory.ACC_BELT),
    (("액세서리", "벨트"), StandardCategory.ACC_BELT),
    (("액세서리", "belt"), StandardCategory.ACC_BELT),
    (("악세서리", "시계"), StandardCategory.ACC_WATCH),
    (("악세서리", "watch"), StandardCategory.ACC_WATCH),
    (("액세서리", "시계"), StandardCategory.ACC_WATCH),
    (("액세서리", "watch"), StandardCategory.ACC_WATCH),
    (("악세서리", "목걸이"), StandardCategory.ACC_JEWELRY),
    (("악세서리", "반지"), StandardCategory.ACC_JEWELRY),
    (("악세서리", "귀걸이"), StandardCategory.ACC_JEWELRY),
    (("악세서리", "팔찌"), StandardCategory.ACC_JEWELRY),
    (("액세서리", "목걸이"), StandardCategory.ACC_JEWELRY),
    (("액세서리", "반지"), StandardCategory.ACC_JEWELRY),
    (("액세서리", "귀걸이"), StandardCategory.ACC_JEWELRY),
    (("액세서리", "팔찌"), StandardCategory.ACC_JEWELRY),
    (("accessory", "sunglasses"), StandardCategory.ACC_EYEWEAR),
    (("accessories", "sunglasses"), StandardCategory.ACC_EYEWEAR),
    (("accessory", "eyewear"), StandardCategory.ACC_EYEWEAR),
    (("accessories", "eyewear"), StandardCategory.ACC_EYEWEAR),
    (("accessory", "beanie"), StandardCategory.ACC_BEANIE),
    (("accessories", "beanie"), StandardCategory.ACC_BEANIE),
    (("accessory", "cap"), StandardCategory.ACC_CAP),
    (("accessories", "cap"), StandardCategory.ACC_CAP),
    (("accessory", "hat"), StandardCategory.ACC_HAT),
    (("accessories", "hat"), StandardCategory.ACC_HAT),
    (("accessory", "scarf"), StandardCategory.ACC_SCARF),
    (("accessories", "scarf"), StandardCategory.ACC_SCARF),
    (("accessory", "watch"), StandardCategory.ACC_WATCH),
    (("accessories", "watch"), StandardCategory.ACC_WATCH),
    (("accessory", "necklace"), StandardCategory.ACC_JEWELRY),
    (("accessories", "necklace"), StandardCategory.ACC_JEWELRY),
    (("accessory", "ring"), StandardCategory.ACC_JEWELRY),
    (("accessories", "ring"), StandardCategory.ACC_JEWELRY),
    (("선글라스",), StandardCategory.ACC_EYEWEAR),
    (("썬글라스",), StandardCategory.ACC_EYEWEAR),
    (("sunglasses",), StandardCategory.ACC_EYEWEAR),
    (("eyewear",), StandardCategory.ACC_EYEWEAR),
    (("안경",), StandardCategory.ACC_EYEWEAR),
]

SKIRT_TOKENS = ("미니스커트", "롱스커트", "스커트", "치마", "skirt")


def _normalize_text(text: str) -> str:
    value = (text or "").lower().strip()
    for sep in ["/", "\\", "|", ",", ";", "_", "-", "(", ")", "[", "]"]:
        value = value.replace(sep, " ")
    return " ".join(value.split())


def normalize_product_name(text: str) -> str:
    value = (text or "").lower()
    value = re.sub(r"\(.*?\)", " ", value)
    value = re.sub(r"\[.*?\]", " ", value)
    value = re.sub(r"\b\d+\+?\d*\b", " ", value)
    for word in _REMOVE_WORDS:
        value = value.replace(word.lower(), " ")
    value = re.sub(r"[^a-z0-9가-힣\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _contains_keyword(text: str, keyword: str) -> bool:
    text_norm = (text or "").lower()
    keyword_norm = (keyword or "").lower()
    if not text_norm or not keyword_norm:
        return False
    if keyword_norm in text_norm:
        return True
    compact_text = text_norm.replace(" ", "")
    compact_keyword = keyword_norm.replace(" ", "")
    if compact_keyword and compact_keyword in compact_text:
        return True
    tokens = text_norm.split()
    return any(compact_keyword in token.replace(" ", "") for token in tokens if token)


def _has_tshirt_signal(text: str) -> bool:
    tshirt_tokens = ("티셔츠", "t shirt", "tshirt", "t-shirt", "tee", "cutsew", "cut sew", "カットソー")
    return any(_contains_keyword(text, token) for token in tshirt_tokens)


def _has_sweat_top_signal(text: str) -> bool:
    sweat_tokens = ("맨투맨", "스웻 셔츠", "스웨트 셔츠", "sweatshirt", "sweat shirt")
    return any(_contains_keyword(text, token) for token in sweat_tokens)


def _has_hoodie_signal(text: str) -> bool:
    hoodie_tokens = ("후드", "후디", "hoodie", "hooded")
    return any(_contains_keyword(text, token) for token in hoodie_tokens)


def _has_outer_jacket_signal(text: str) -> bool:
    jacket_tokens = ("자켓", "재킷", "점퍼", "jacket", "blouson")
    return any(_contains_keyword(text, token) for token in jacket_tokens)


def _has_padding_signal(text: str) -> bool:
    padding_tokens = ("패딩", "다운", "down jacket", "puffer", "padding")
    return any(_contains_keyword(text, token) for token in padding_tokens)


def _has_belt_product_signal(text: str) -> bool:
    normalized = _normalize_text(text)
    return (
        _contains_keyword(normalized, "벨트")
        or _contains_keyword(normalized, "ベルト")
        or bool(re.search(r"\bbelt\b", normalized))
    )


def _has_english_phrase(text: str, phrase: str) -> bool:
    normalized = _normalize_text(text)
    pattern = r"\b" + r"\s+".join(re.escape(part) for part in phrase.lower().split()) + r"\b"
    return bool(re.search(pattern, normalized))


def _resolve_pants_signal(text: str) -> Optional[StandardCategory]:
    if (
        any(_contains_keyword(text, token) for token in ("숏팬츠", "쇼츠", "반바지"))
        or any(_has_english_phrase(text, token) for token in ("shorts", "short pants", "half pants"))
    ):
        return StandardCategory.PANTS_SHORTS
    if any(_contains_keyword(text, token) for token in ("청바지", "데님", "denim", "jeans")):
        return StandardCategory.PANTS_DENIM
    if any(_contains_keyword(text, token) for token in ("카고", "cargo")):
        return StandardCategory.PANTS_CARGO
    if any(_contains_keyword(text, token) for token in ("스웻팬츠", "스웨트팬츠", "트레이닝팬츠", "sweatpants", "sweat pants", "track pants")):
        return StandardCategory.PANTS_TRAINING
    if any(_contains_keyword(text, token) for token in ("조거", "jogger")):
        return StandardCategory.PANTS_JOGGER
    if any(_contains_keyword(text, token) for token in ("레깅스", "leggings", "legging")):
        return StandardCategory.PANTS_LEGGINGS
    if (
        any(_contains_keyword(text, token) for token in ("팬츠", "바지"))
        or any(_has_english_phrase(text, token) for token in ("pants", "trousers"))
    ):
        return StandardCategory.PANTS_REGULAR
    return None


def _resolve_shirt_blouse_signal(text: str) -> Optional[StandardCategory]:
    if any(_contains_keyword(text, token) for token in ("블라우스", "브라우스", "blouse")):
        return StandardCategory.TOP_BLOUSE
    if (
        any(_contains_keyword(text, token) for token in ("셔츠", "남방", "shirt"))
        and not _has_tshirt_signal(text)
        and not _has_sweat_top_signal(text)
    ):
        return StandardCategory.TOP_SHIRT
    return None


def _resolve_from_musinsa_category_text(text: str) -> Optional[StandardCategory]:
    normalized = _normalize_text(text)
    compact = normalized.replace(" ", "")
    # Guardrail: shirt/blouse labels should not be downgraded to t-shirt.
    shirt_blouse_category = _resolve_shirt_blouse_signal(normalized)
    if shirt_blouse_category is not None:
        return shirt_blouse_category

    # Guardrail: mixed labels like "속옷/홈웨어" should prefer underwear.
    has_underwear_token = any(
        _contains_keyword(normalized, token)
        for token in ("속옷", "언더웨어", "이너웨어", "innerwear", "underwear", "브라", "팬티", "속바지")
    )
    has_homewear_token = any(
        _contains_keyword(normalized, token)
        for token in ("홈웨어", "잠옷", "파자마", "homewear", "pajama", "loungewear")
    )
    if has_underwear_token and has_homewear_token:
        return StandardCategory.INNER_UNDERWEAR

    for keywords, category in MUSINSA_CATEGORY_OVERRIDES:
        if all(_contains_keyword(normalized, keyword) or keyword.replace(" ", "") in compact for keyword in keywords):
            return category
    return None


def _has_non_top_category_context(text: str) -> bool:
    non_top_tokens = (
        "바지", "팬츠", "스커트", "치마", "원피스", "드레스",
        "신발", "슈즈", "가방", "백", "악세서리", "액세서리",
        "속옷", "홈웨어", "디지털", "가전",
        "bottom", "bottoms", "pants", "skirt", "dress", "shoes",
        "bag", "accessory", "accessories", "inner", "underwear",
    )
    return any(_contains_keyword(text, token) for token in non_top_tokens)


def _has_vague_top_category_context(text: str) -> bool:
    normalized = _normalize_text(text)
    has_top = any(_contains_keyword(normalized, token) for token in ("상의", "top", "tops"))
    has_vague = any(_contains_keyword(normalized, token) for token in ("기타", "etc", "other", "기본", "일반"))
    return has_top and has_vague


def _resolve_product_strong_top_signal(
    product_name: str,
    *,
    musinsa_category_text: str = "",
) -> Optional[StandardCategory]:
    product_text = _normalize_text(product_name)
    category_text = _normalize_text(musinsa_category_text)
    if not product_text:
        return None

    # Product titles like "Tailored Jacket" are stronger than vague
    # Musinsa buckets such as "기타 상의".
    if _has_outer_jacket_signal(product_text) and not _has_padding_signal(product_text) and not _has_non_top_category_context(category_text):
        return StandardCategory.OUTER_JACKET
    if _has_hoodie_signal(product_text) and _has_vague_top_category_context(category_text):
        return StandardCategory.TOP_HOODIE
    return None


def fallback_category(name: str, brand: str) -> str:
    clean_name = normalize_product_name(name)
    text = _normalize_text(f"{clean_name} {brand}")
    for category_label, keywords, _standard in CATEGORY_FALLBACK_RULES:
        if any(_normalize_text(keyword) in text for keyword in keywords):
            return category_label
    return "unresolved"


def classify_category_with_reason(
    name: str,
    brand: str,
    existing_category: Optional[StandardCategory] = None,
) -> Tuple[StandardCategory, str]:
    clean_name = normalize_product_name(name)
    force_text = f"{clean_name} {(brand or '').lower()}".strip()
    raw_text = _normalize_text(f"{name or ''} {brand or ''}")
    result: StandardCategory | None = None
    reason = "unresolved"

    # Guardrail: skirt signals should win over broad/ambiguous top keywords.
    if any(_contains_keyword(force_text, token) for token in SKIRT_TOKENS):
        if _contains_keyword(force_text, "미니"):
            return StandardCategory.SKIRT_MINI, "skirt_keyword_override_mini"
        return StandardCategory.SKIRT_LONG, "skirt_keyword_override"

    # Guardrail: overalls/salopettes often contain broad bottom/top words, but
    # BUYMA expects them under all-in-one categories.
    overall_tokens = ("오버롤", "오버롤즈", "점프수트", "overall", "overalls", "jumpsuit", "salopette")
    if any(_contains_keyword(force_text, token) for token in overall_tokens):
        return StandardCategory.JUMPSUIT, "overall_keyword_override"

    # Guardrail: explicit dress/one-piece signals should win over noisy top keywords.
    dress_tokens = ("원피스", "드레스", "onepiece", "one-piece", "shirt dress", "dress")
    has_dress = any(_contains_keyword(force_text, token) for token in dress_tokens)
    has_skirt = any(_contains_keyword(force_text, token) for token in SKIRT_TOKENS)
    if has_dress and not has_skirt:
        return StandardCategory.DRESS, "dress_keyword_override"

    if _has_sweat_top_signal(force_text):
        return StandardCategory.TOP_SWEAT, "sweat_keyword_override"

    if _has_padding_signal(force_text):
        return StandardCategory.OUTER_PADDING, "padding_keyword_override"

    if _has_outer_jacket_signal(force_text):
        return StandardCategory.OUTER_JACKET, "jacket_keyword_override"

    if _has_hoodie_signal(force_text):
        return StandardCategory.TOP_HOODIE, "hoodie_keyword_override"

    pants_category = _resolve_pants_signal(force_text)
    if pants_category is not None:
        return pants_category, "pants_keyword_override"

    shirt_blouse_category = _resolve_shirt_blouse_signal(force_text)
    if shirt_blouse_category == StandardCategory.TOP_BLOUSE:
        return StandardCategory.TOP_BLOUSE, "blouse_keyword_override"
    if shirt_blouse_category == StandardCategory.TOP_SHIRT:
        return StandardCategory.TOP_SHIRT, "shirt_keyword_override"

    sneaker_model_tokens = ("ld 1000", "ld1000")
    if any(_contains_keyword(raw_text, token) for token in sneaker_model_tokens):
        return StandardCategory.SHOES_SNEAKER, "sneaker_model_keyword_override"

    # Guardrail: beanie should not fall into generic cap/hat buckets.
    beanie_tokens = ("비니", "beanie", "니트모자", "니트 캡")
    if any(_contains_keyword(force_text, token) for token in beanie_tokens):
        return StandardCategory.ACC_BEANIE, "beanie_keyword_override"

    # Guardrail: belt products may include noisy shape/innerwear words like
    # "padded" or "body-shaping"; explicit belt signals should stay in belts.
    if _has_belt_product_signal(force_text):
        return StandardCategory.ACC_BELT, "belt_keyword_override"

    # If caller already resolved a concrete category from sheet/mapping,
    # keep it unless stronger domain-specific guardrails above overrode it.
    if existing_category is not None and existing_category != StandardCategory.ETC:
        return existing_category, "existing_category"

    # Guardrail: denim/jeans product names should not be flipped to innerwear
    # by broad body-shape keywords such as "골반뽕", "볼륨업".
    denim_tokens = ("청바지", "데님", "jeans", "denim", "부츠컷", "bootcut")
    if any(_contains_keyword(force_text, token) for token in denim_tokens):
        return StandardCategory.PANTS_DENIM, "denim_keyword_override"

    outer_vest_tokens = ("트랙 베스트", "러닝 베스트", "패딩조끼", "다운 베스트", "track vest", "running vest", "puffer vest", "down vest")
    if any(_contains_keyword(force_text, token) for token in outer_vest_tokens):
        return StandardCategory.OUTER_VEST, "outer_vest_keyword_override"

    for keywords, category in FORCE_CATEGORY_MAP.items():
        if any(_contains_keyword(force_text, keyword) for keyword in keywords):
            result = category
            reason = "force_map"
            break

    if result is None:
        if existing_category is not None:
            result = existing_category
            reason = "existing_category"
        else:
            label = fallback_category(clean_name, brand)
            matched = next((std for cat, _kw, std in CATEGORY_FALLBACK_RULES if cat == label), None)
            result = matched or StandardCategory.ETC
            reason = "fallback_rules" if matched else "unresolved"

    return result, reason


def classify_category(name: str, brand: str, existing_category: Optional[StandardCategory] = None) -> StandardCategory:
    result, _reason = classify_category_with_reason(name, brand, existing_category)
    _LOGGER.info(
        "category_classification product=%s brand=%s result=%s",
        (name or "").strip(),
        (brand or "").strip(),
        result.value,
    )
    if result == StandardCategory.ETC:
        _LOGGER.warning("category_unresolved product=%s brand=%s", (name or "").strip(), (brand or "").strip())
        _write_unresolved_jsonl(product_name=(name or "").strip(), brand=(brand or "").strip())
    return result


def _tokenize_unresolved(text: str) -> List[str]:
    normalized = normalize_product_name(text)
    raw = re.findall(r"[a-zA-Z]{3,}|[가-힣]{2,}", normalized)
    stopwords = {
        "black", "white", "ivory", "navy", "blue", "red",
        "new", "official", "authentic", "women", "men",
        "臾대즺諛곗넚", "?뺥뭹", "怨듭떇",
        "value", "移댁씤?ㅻ?", "kindame", "free", "volume", "hip",
    }
    return [token for token in raw if token not in stopwords]


def _write_unresolved_jsonl(*, product_name: str, brand: str, row: int = 0) -> None:
    try:
        os.makedirs(os.path.dirname(_UNRESOLVED_JSONL_PATH), exist_ok=True)
        payload = {
            "row": row,
            "product_name": product_name,
            "brand": brand,
            "tokens": _tokenize_unresolved(f"{product_name} {brand}"),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        with open(_UNRESOLVED_JSONL_PATH, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # 遺꾨쪟 濡쒖쭅? ?덈? 以묐떒?쒗궎吏 ?딅뒗??
        return


def _split_keywords(raw: str) -> List[str]:
    text = (raw or "").strip()
    if not text:
        return []
    parts = re.split(r"[\n,|;/]+", text)
    return [p.strip().lower() for p in parts if p.strip()]


def _parse_bool(value: str, default: bool = True) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "y", "yes", "true", "on"}


def _parse_int(value: str, default: int = 100) -> int:
    text = (value or "").strip()
    try:
        return int(text)
    except Exception:
        return default


def _resolve_spreadsheet_id_from_runtime() -> str:
    cfg_path = os.path.join(get_runtime_data_dir(), "sheets_config.json")
    if not os.path.exists(cfg_path):
        return ""
    try:
        with open(cfg_path, "r", encoding="utf-8") as fp:
            cfg = json.load(fp)
        raw_id = str((cfg or {}).get("spreadsheet_id", "") or "")
        return sheet_source_mod.extract_spreadsheet_id(raw_id)
    except Exception:
        return ""


def _resolve_category_sheet_name(default_name: str = DEFAULT_CLASSIFIER_SHEET) -> str:
    try:
        profile_name = (os.environ.get("AUTO_SHOP_PROFILE") or "default").strip() or "default"
        config = load_profile_config(profile_name)
        tabs_cfg = ((config.get("spreadsheet") or {}).get("tabs") or {})
        configured = str(tabs_cfg.get("category") or "").strip()
        return configured or default_name
    except Exception:
        return default_name


def _to_standard_category(raw: str) -> Optional[StandardCategory]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return StandardCategory(text)
    except Exception:
        return None


def _load_rules_from_sheet(
    *,
    spreadsheet_id: str,
    sheet_name: str,
    _retried: bool = False,
) -> List[ClassificationRule]:
    if not spreadsheet_id:
        return []

    try:
        credentials_path = sheet_source_mod.get_credentials_path(os.getcwd())
        service = sheet_source_mod.get_sheets_service(credentials_path)
        # 癒쇱? ??議댁옱 ?щ?瑜??뺤씤??range parse ?먮윭瑜??쇳븳??
        meta = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(title))",
        ).execute()
        titles = [
            ((s.get("properties", {}) or {}).get("title") or "").strip()
            for s in meta.get("sheets", [])
        ]
        if sheet_name not in titles:
            print(f"[classifier] sheet not found: '{sheet_name}'")
            print(f"[classifier] available sheets: {titles}")
            return []

        quoted_name = sheet_name.replace("'", "''")
        header_result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{quoted_name}'!A1:ZZ1",
        ).execute()
        header_row = header_result.get("values", [[]])[0] if header_result.get("values") else []
        header_map: Dict[str, int] = {}
        for idx, value in enumerate(header_row):
            key = (value or "").strip()
            if key:
                header_map[key] = idx
        if not header_map:
            return []

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{quoted_name}'!A2:ZZ1000",
        ).execute()
        rows = result.get("values", [])
        rules: List[ClassificationRule] = []
        for row in rows:
            def v(col: str) -> str:
                idx = header_map.get(col)
                if idx is None or idx >= len(row):
                    return ""
                return (row[idx] or "").strip()

            std = _to_standard_category(v("standard_category"))
            if not std:
                continue
            keywords = _split_keywords(v("title_keywords_include"))
            if not keywords:
                continue
            enabled = _parse_bool(v("enabled"), True)
            priority = _parse_int(v("priority"), 100)
            if not enabled:
                continue

            rules.append(
                ClassificationRule(
                    standard_category=std,
                    title_keywords_include=keywords,
                    priority=priority,
                    enabled=enabled,
                )
            )

        rules.sort(key=lambda r: r.priority)
        return rules
    except Exception as exc:
        # ???대쫫???뺥솗???쇱튂?섏? ?딆쓣 ????뚮Ц??怨듬갚/?몃뜑?ㅼ퐫??李⑥씠) ?먮룞 ?댁꽍 ?ъ떆??
        try:
            if _retried:
                print(f"[classifier] rule load failed: {exc}")
                return []
            credentials_path = sheet_source_mod.get_credentials_path(os.getcwd())
            service = sheet_source_mod.get_sheets_service(credentials_path)
            meta = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(title))",
            ).execute()
            titles = [
                ((s.get("properties", {}) or {}).get("title") or "").strip()
                for s in meta.get("sheets", [])
            ]
            normalized_target = re.sub(r"[\s_]+", "", (sheet_name or "").strip().lower())
            resolved = ""
            for t in titles:
                nt = re.sub(r"[\s_]+", "", (t or "").strip().lower())
                if nt == normalized_target:
                    resolved = t
                    break
            if not resolved:
                for t in titles:
                    nt = re.sub(r"[\s_]+", "", (t or "").strip().lower())
                    if normalized_target and (normalized_target in nt or nt in normalized_target):
                        resolved = t
                        break
            if resolved:
                print(f"[classifier] sheet name fallback: '{sheet_name}' -> '{resolved}'")
                return _load_rules_from_sheet(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=resolved,
                    _retried=True,
                )
            print(f"[classifier] rule load failed: {exc}")
            print(f"[classifier] available sheets: {titles}")
            return []
        except Exception as meta_exc:
            print(f"[classifier] rule load failed: {exc}")
            print(f"[classifier] metadata fallback failed: {meta_exc}")
            return []


def _get_rules(
    *,
    spreadsheet_id: str,
    sheet_name: str,
) -> List[ClassificationRule]:
    now = datetime.now()
    loaded_at = _RULE_CACHE.get("loaded_at")
    cache_key = f"{spreadsheet_id}::{sheet_name}"
    if (
        isinstance(loaded_at, datetime)
        and _RULE_CACHE.get("key") == cache_key
        and now - loaded_at < timedelta(seconds=_CACHE_TTL_SECONDS)
    ):
        return list(_RULE_CACHE.get("rules", []))

    rules = _load_rules_from_sheet(spreadsheet_id=spreadsheet_id, sheet_name=sheet_name)
    _RULE_CACHE["loaded_at"] = now
    _RULE_CACHE["key"] = cache_key
    _RULE_CACHE["rules"] = list(rules)
    return rules


def classify_standard_category_from_sheet(
    *,
    musinsa_large: str,
    musinsa_middle: str,
    musinsa_small: str,
    product_name: str,
    brand: str = "",
    sheet_name: str = DEFAULT_CLASSIFIER_SHEET,
) -> Tuple[Optional[StandardCategory], Dict[str, str]]:
    """Return (standard_category_or_none, debug_meta)."""
    musinsa_category_text = build_combined_text(
        musinsa_large or "",
        musinsa_middle or "",
        musinsa_small or "",
        "",
    )
    product_override = _resolve_product_strong_top_signal(product_name, musinsa_category_text=musinsa_category_text)
    if product_override is not None:
        return product_override, {
            "reason": "product_keyword_override",
            "standard_category": product_override.value,
        }

    category_override = _resolve_from_musinsa_category_text(musinsa_category_text)
    if category_override is not None:
        return category_override, {
            "reason": "musinsa_category_override",
            "standard_category": category_override.value,
        }

    spreadsheet_id = _resolve_spreadsheet_id_from_runtime()
    if not spreadsheet_id:
        fallback_std = classify_category(product_name, brand)
        return fallback_std, {"reason": "no_spreadsheet_id_fallback", "standard_category": fallback_std.value}

    resolved_sheet_name = sheet_name
    if sheet_name == DEFAULT_CLASSIFIER_SHEET:
        resolved_sheet_name = _resolve_category_sheet_name(DEFAULT_CLASSIFIER_SHEET)

    rules = _get_rules(spreadsheet_id=spreadsheet_id, sheet_name=resolved_sheet_name)
    if not rules and resolved_sheet_name != DEFAULT_CLASSIFIER_SHEET:
        rules = _get_rules(spreadsheet_id=spreadsheet_id, sheet_name=DEFAULT_CLASSIFIER_SHEET)
        resolved_sheet_name = DEFAULT_CLASSIFIER_SHEET
    if not rules:
        fallback_std = classify_category(product_name, brand)
        return fallback_std, {"reason": "no_rules_fallback", "standard_category": fallback_std.value}

    combined_text = build_combined_text(
        musinsa_large or "",
        musinsa_middle or "",
        musinsa_small or "",
        product_name or "",
    )
    if not combined_text:
        fallback_std = classify_category(product_name, brand)
        return fallback_std, {"reason": "empty_text_fallback", "standard_category": fallback_std.value}

    matched_rule: Optional[ClassificationRule] = None
    matched_keyword = ""
    text = _normalize_text(combined_text)
    for rule in rules:
        for kw in rule.title_keywords_include:
            k = _normalize_text(kw)
            if k and k in text:
                matched_rule = rule
                matched_keyword = kw
                break
        if matched_rule:
            break

    if not matched_rule:
        fallback_std = classify_category(product_name, brand)
        return fallback_std, {"reason": "no_match_fallback", "standard_category": fallback_std.value}

    resolved = classify_category(product_name, brand, matched_rule.standard_category)
    return resolved, {
        "reason": "matched",
        "matched_keyword": matched_keyword,
        "sheet_name": resolved_sheet_name,
        "standard_category": resolved.value,
    }
