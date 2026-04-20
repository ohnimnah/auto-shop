"""BUYMA option-related pure transformation helpers."""

import re
from typing import Dict, List

from marketplace.buyma.selectors import JP_SHITEI_NASHI, JP_SIZE_SHITEI_NASHI


def infer_color_system(color_text: str) -> str:
    c = (color_text or "").strip().lower()
    if not c or c == "none":
        return "色指定なし"
    if any(k in c for k in ["black", "블랙", "검정"]):
        return "ブラック系"
    if any(k in c for k in ["white", "ivory", "오프화이트", "아이보리", "흰"]):
        return "ホワイト系"
    if any(k in c for k in ["gray", "grey", "그레이", "회색"]):
        return "グレー系"
    if any(k in c for k in ["beige", "camel", "베이지", "카멜"]):
        return "ベージュ系"
    if any(k in c for k in ["brown", "브라운", "갈색"]):
        return "ブラウン系"
    if any(k in c for k in ["pink", "핑크"]):
        return "ピンク系"
    if any(k in c for k in ["red", "레드", "빨강"]):
        return "レッド系"
    if any(k in c for k in ["orange", "오렌지"]):
        return "オレンジ系"
    if any(k in c for k in ["yellow", "옐로우", "노랑"]):
        return "イエロー系"
    if any(k in c for k in ["green", "khaki", "olive", "그린", "카키", "올리브"]):
        return "グリーン系"
    if any(k in c for k in ["blue", "navy", "블루", "네이비"]):
        return "ブルー系"
    if any(k in c for k in ["purple", "violet", "퍼플", "보라"]):
        return "パープル系"
    if any(k in c for k in ["gold", "실버", "silver", "metal", "메탈"]):
        return "シルバー・ゴールド系"
    return "マルチカラー"


def split_color_values(color_text: str) -> List[str]:
    if not color_text:
        return []
    parts = re.split(r"[,/|]|\s+and\s+|\s*&\s*", color_text)
    return [part.strip() for part in parts if part.strip()]


COLOR_ABBR_MAP: Dict[str, str] = {
    "bk": "Black",
    "br": "Brown",
    "dg": "Dark Gray",
    "lg": "Light Gray",
    "cg": "Charcoal Gray",
    "mg": "Melange Gray",
    "gy": "Gray",
    "iv": "Ivory",
    "na": "Navy",
    "nv": "Navy",
    "wh": "White",
    "wt": "White",
    "be": "Beige",
    "kh": "Khaki",
    "ol": "Olive",
    "rd": "Red",
    "pk": "Pink",
    "ye": "Yellow",
    "gr": "Green",
    "bl": "Blue",
    "pu": "Purple",
    "or": "Orange",
}


def expand_color_abbreviations(color_text: str) -> str:
    normalized_text = (color_text or "").strip()
    dot_parts = [part.strip() for part in normalized_text.split(".") if part.strip()]
    if len(dot_parts) >= 2 and all(re.fullmatch(r"[A-Za-z]{1,3}", part) for part in dot_parts):
        values = dot_parts
    else:
        values = split_color_values(normalized_text)
    if not values:
        return color_text

    expanded: List[str] = []
    for raw in values:
        key = re.sub(r"[^a-z0-9]", "", raw.strip().lower())
        mapped = COLOR_ABBR_MAP.get(key)
        value = mapped if mapped else raw.strip()
        if value and value not in expanded:
            expanded.append(value)
    return ", ".join(expanded)


def build_size_variants(size_raw: str) -> List[str]:
    sz = (size_raw or "").strip()
    if not sz:
        return []

    variants = [sz]
    normalized = sz.upper().replace(" ", "")
    parts = [part.strip() for part in re.split(r"[/|]", sz) if part.strip()]
    for part in parts:
        if part not in variants:
            variants.append(part)

    if normalized in {"F", "FREE", "FREESIZE", "OS", "ONESIZE", "O/S"}:
        variants.extend([
            "F", "FREE", "FREE SIZE", "ONE SIZE", "ONESIZE", "OS", "O/S",
            "フリー", "フリーサイズ", "ワンサイズ", "サイズ指定なし", "指定なし"
        ])

    numeric_seeds = []
    for token in [sz] + parts:
        only_num = re.sub(r"[^0-9.]", "", token)
        if not only_num:
            continue
        try:
            if "." in only_num:
                value = float(only_num)
                if 20 <= value <= 35:
                    numeric_seeds.append(int(round(value * 10)))
                elif 200 <= value <= 350:
                    numeric_seeds.append(int(round(value)))
            else:
                int_value = int(only_num)
                if 200 <= int_value <= 350:
                    numeric_seeds.append(int_value)
                elif 20 <= int_value <= 35:
                    numeric_seeds.append(int_value * 10)
        except Exception:
            continue

    for numeric in numeric_seeds:
        cm = numeric / 10.0
        cm_str = f"{cm:.1f}".rstrip("0").rstrip(".")
        variants.extend([
            str(numeric),
            f"{cm:.1f}",
            cm_str,
            f"{cm_str}cm",
            f"{numeric}mm",
            f"JP{cm_str}",
            f"KR{cm_str}",
        ])

    seen = set()
    out = []
    for value in variants:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def normalize_size_token_for_match(text: str) -> str:
    value = (text or "").lower().strip()
    if not value:
        return ""
    value = value.replace("?", " ")
    value = value.replace("ｃｍ", "cm").replace("㎝", "cm").replace("センチ", "cm")
    value = value.replace("サイズ", "").replace("size", "")
    value = value.replace("cm", "").replace("mm", "")
    value = value.replace("jp", "").replace("kr", "").replace("us", "").replace("uk", "").replace("eu", "").replace("it", "")
    value = re.sub(r"[\s\-_/\(\)\[\]\{\}:;,+]", "", value)
    return value.replace(".", "")


def size_match(a: str, b: str) -> bool:
    normalized_a = normalize_size_token_for_match(a)
    normalized_b = normalize_size_token_for_match(b)
    if not normalized_a or not normalized_b:
        return False
    if normalized_a == normalized_b:
        return True

    fixed_tokens = {"xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl"}
    if normalized_a in fixed_tokens or normalized_b in fixed_tokens:
        return normalized_a == normalized_b
    return (normalized_a in normalized_b) or (normalized_b in normalized_a)


def is_free_size_text(size_text: str) -> bool:
    raw = (size_text or "").strip()
    if not raw:
        return False

    tokens = [token.strip() for token in re.split(r"[,/|]+", raw) if token.strip()]
    if not tokens:
        return False

    normalized_tokens = []
    for token in tokens:
        value = token.lower().strip()
        value = value.replace("?", " ")
        value = re.sub(r"\s+", "", value)
        value = value.replace("-", "").replace("_", "").replace(".", "")
        normalized_tokens.append(value)

    free_aliases = {
        "f", "free", "freesize", "onesize", "os", "o/s".replace("/", ""),
        "none", "n/a", "na", "no", "nosize", "nosizes", "notapplicable",
        "지정없음", "사이즈없음", "없음", "해당없음",
        JP_SIZE_SHITEI_NASHI, JP_SHITEI_NASHI, "サイズなし", "なし",
        "프리", "프리사이즈",
        "フリー", "フリーサイズ", "ワンサイズ",
    }
    return all(token in free_aliases for token in normalized_tokens)
