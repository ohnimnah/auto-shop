"""BUYMA category and gender inference helpers."""

from typing import List, Tuple


FEMALE_KEYWORDS = [
    "women", "woman", "female", "lady", "ladies", "girl", "girls",
    "여성", "여자", "우먼", "레이디", "걸", "숙녀",
]
MALE_KEYWORDS = [
    "men", "man", "male", "gentleman", "boy", "boys",
    "남성", "남자", "맨", "보이", "신사",
]
BUYMA_GENDER_CATEGORY_MAP = {
    "F": "レディースファッション",
    "M": "メンズファッション",
    "U": "メンズファッション",
}

CATEGORY_KEYWORDS = [
    (["티셔츠", "반팔", "긴팔", "tee", "t-shirt"], None, "トップス", "Tシャツ・カットソー"),
    (["후드", "hoodie", "hood"], None, "トップス", "パーカー・フーディ"),
    (["맨투맨", "sweatshirt", "sweat"], None, "トップス", "スウェット"),
    (["셔츠", "shirt", "blouse"], None, "トップス", "シャツ"),
    (["니트", "sweater", "knit"], None, "トップス", "ニット・セーター"),
    (["청바지", "데님", "jeans", "denim"], None, "ボトムス", "デニム・ジーンズ"),
    (["슬랙스", "trousers"], None, "ボトムス", "スラックス"),
    (["팬츠", "바지", "pants"], None, "ボトムス", "パンツ"),
    (["반바지", "shorts"], None, "ボトムス", "ショーツ"),
    (["원피스", "dress"], None, "ワンピース", ""),
    (["자켓", "재킷", "jacket"], None, "アウター", "ジャケット"),
    (["코트", "coat"], None, "アウター", "コート"),
    (["가디건", "cardigan"], None, "アウター", "カーディガン"),
    (["바람막이", "windbreaker"], None, "アウター", "ナイロンジャケット"),
    (["운동화", "스니커즈", "sneaker"], None, "靴", "スニーカー"),
    (["샌들", "sandal"], None, "靴", "サンダル"),
    (["부츠", "boot"], None, "靴", "ブーツ"),
    (["로퍼", "loafer"], None, "靴", "ローファー"),
]


def detect_gender_raw(title: str) -> str:
    text = (title or "").lower()
    if any(keyword in text for keyword in FEMALE_KEYWORDS):
        return "F"
    if any(keyword in text for keyword in MALE_KEYWORDS):
        return "M"
    return "U"


def convert_gender_for_buyma(gender: str) -> str:
    if gender == "F":
        return "レディース"
    if gender == "M":
        return "メンズ"
    return "メンズ"


def detect_gender(title: str) -> str:
    return convert_gender_for_buyma(detect_gender_raw(title))


def get_buyma_fashion_category_from_gender(title: str) -> str:
    raw_gender = detect_gender_raw(title)
    return BUYMA_GENDER_CATEGORY_MAP.get(raw_gender, BUYMA_GENDER_CATEGORY_MAP["U"])


def infer_buyma_category(product_name_kr: str, product_name_en: str, brand: str = "") -> Tuple[str, str, str]:
    title = f"{product_name_kr} {product_name_en}".strip()
    text = f"{product_name_kr} {product_name_en} {brand}".lower()
    fashion_category = get_buyma_fashion_category_from_gender(title)
    if any(token in text for token in ["new balance", "뉴발란스", "mr530", "530lg", "530sg", "530ka", "m1906", "1906r", "2002r", "327", "990v", "991", "992", "993"]):
        return (fashion_category, "靴", "スニーカー")
    for keywords, cat1, cat2, cat3 in CATEGORY_KEYWORDS:
        if any(keyword.lower() in text for keyword in keywords):
            if cat1 is None:
                cat1 = fashion_category
            return (cat1, cat2 or "", cat3 or "")
    return ("", "", "")


def normalize_sheet_category_labels(cat1: str, cat2: str, cat3: str) -> Tuple[str, str, str]:
    c1 = (cat1 or "").strip()
    c2 = (cat2 or "").strip()
    c3 = (cat3 or "").strip()

    top_map = {
        "여성": "レディースファッション",
        "여자": "レディースファッション",
        "레이디스": "レディースファッション",
        "레ディース": "レディースファッション",
        "남성": "メンズファッション",
        "남자": "メンズファッション",
        "멘즈": "メンズファッション",
        "メンズ": "メンズファッション",
        "レディース": "レディースファッション",
    }
    mid_map = {
        "상의": "トップス",
        "하의": "ボトムス",
        "바지": "ボトムス",
        "신발": "靴",
        "슈즈": "靴",
        "운동화": "靴",
        "아우터": "アウター",
        "가방": "バッグ",
        "악세서리": "アクセサリー",
        "악세사리": "アクセサリー",
        "원피스": "ワンピース",
    }
    sub_map = {
        "데님 팬츠": "デニム・ジーンズ",
        "데님팬츠": "デニム・ジーンズ",
        "청바지": "デニム・ジーンズ",
        "슬랙스": "スラックス",
        "팬츠": "パンツ",
        "조거팬츠": "ジョガーパンツ",
        "카고팬츠": "カーゴパンツ",
        "반바지": "ショーツ",
        "스니커즈": "スニーカー",
        "러닝화": "ランニングシューズ",
        "샌들": "サンダル",
        "부츠": "ブーツ",
        "로퍼": "ローファー",
        "티셔츠": "Tシャツ・カットソー",
        "후드": "パーカー・フーディ",
        "후드티": "パーカー・フーディ",
        "맨투맨": "スウェット",
        "셔츠": "シャツ",
        "니트": "ニット・セーター",
        "코트": "コート",
        "자켓": "ジャケット",
        "블레이저": "テーラードジャケット",
        "가디건": "カーディガン",
        "바람막이": "ナイロンジャケット",
    }

    return top_map.get(c1, c1), mid_map.get(c2, c2), sub_map.get(c3, c3)


def normalize_gender_label_for_sheet(text: str) -> str:
    value = (text or "").strip().lower()
    if not value:
        return ""
    if value in {"여성", "여자", "레ディース", "レディース", "w", "female", "women", "womens"}:
        return "여성"
    if value in {"남성", "남자", "メンズ", "m", "male", "men", "mens"}:
        return "남성"
    if "여성" in value or "レディース" in value or "women" in value or "female" in value:
        return "여성"
    if "남성" in value or "メンズ" in value or "men" in value or "male" in value:
        return "남성"
    return ""


def remap_sheet_categories_with_gender(cat1: str, cat2: str, cat3: str) -> Tuple[str, str, str]:
    values = [(cat1 or "").strip(), (cat2 or "").strip(), (cat3 or "").strip()]
    gender = ""
    rest: List[str] = []
    for value in values:
        if not value:
            continue
        normalized_gender = normalize_gender_label_for_sheet(value)
        if normalized_gender and not gender:
            gender = normalized_gender
            continue
        if normalized_gender:
            continue
        rest.append(value)

    if not gender:
        return cat1, cat2, cat3
    new_mid = rest[0] if len(rest) > 0 else ""
    new_small = rest[1] if len(rest) > 1 else ""
    return gender, new_mid, new_small
