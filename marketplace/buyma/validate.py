"""BUYMA validation and parsing helpers."""

from __future__ import annotations

import re
from typing import Dict, List


def normalize_actual_size_for_upload(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in {"none", "n/a", "na"}:
        return ""
    if text in {"없음", "-"}:
        return ""
    return text


def is_blank_or_zero_measure_value(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    return is_zero_measure_value(text)


def is_zero_measure_value(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    try:
        return float(text.replace(",", "")) == 0.0
    except Exception:
        return False


def _normalize_measure_text(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("㎝", "cm")
    text = re.sub(r"\s+", "", text)
    return text


def _extract_pairs(text: str) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    if not text:
        return pairs
    normalized = text.replace("\r", "\n")
    normalized = normalized.replace("，", ",").replace("：", ":")
    normalized = normalized.replace(" / ", ", ").replace("·", " ")
    normalized = normalized.replace("(", " ").replace(")", " ")
    normalized = normalized.replace("[", " ").replace("]", " ")
    normalized = normalized.replace("cm", " ").replace("㎝", " ")
    normalized = normalized.replace("\n", ", ")

    # Supports:
    # - "フレーム横 13.4"
    # - "フレーム横:13.4"
    # - "전체너비 13.4"
    pattern = re.compile(r"([^\d,\|:]{1,40}?)\s*[: ]\s*(-?\d+(?:\.\d+)?)")
    for key, val in pattern.findall(normalized):
        clean_key = key.strip().strip(",")
        clean_val = val.strip()
        if clean_key and clean_val and clean_key not in pairs:
            pairs[clean_key] = clean_val
    return pairs


def extract_actual_measure_map(actual_size_text: str) -> Dict[str, str]:
    return _extract_pairs(actual_size_text or "")


def extract_actual_size_rows(actual_size_text: str) -> Dict[str, Dict[str, str]]:
    rows: Dict[str, Dict[str, str]] = {}
    text = (actual_size_text or "").strip()
    if not text:
        return rows

    # Primary: "size: key val, key val | size2: ..."
    chunks = [c.strip() for c in text.split("|") if c.strip()]
    for chunk in chunks:
        match = re.match(r"^([^:]+)\s*:\s*(.+)$", chunk)
        if not match:
            continue
        size_name = match.group(1).strip() or "default"
        body = match.group(2).strip()
        measure_map = _extract_pairs(body)
        if measure_map:
            rows[size_name] = measure_map

    # Fallback: no size prefix, treat as single row
    if not rows:
        measure_map = _extract_pairs(text)
        if measure_map:
            rows["default"] = measure_map

    return rows


MEASURE_ALIASES: Dict[str, List[str]] = {
    "총장": ["총장", "기장", "length", "着丈", "身丈", "総丈", "スカート丈"],
    "어깨너비": ["어깨너비", "어깨", "shoulder", "shoulderwidth", "肩幅"],
    "가슴단면": ["가슴단면", "가슴", "품", "chest", "chestwidth", "bust", "身幅", "胸幅", "バスト"],
    "소매길이": ["소매길이", "소매", "sleeve", "sleevelength", "袖丈"],
    "목둘레": ["목둘레", "목너비", "넥", "neck", "首周り", "ネック"],
    "암홀": ["암홀", "armhole", "アームホール"],
    "허리단면": ["허리단면", "허리", "waist", "ウエスト"],
    "힙단면": ["힙단면", "힙", "엉덩이", "hip", "ヒップ"],
    "허벅지단면": ["허벅지단면", "허벅지", "thigh", "わたり幅", "もも幅", "もも周り"],
    "밑위": ["밑위", "rise", "股上"],
    "인심": ["인심", "밑아래", "inseam", "股下"],
    "밑단단면": ["밑단단면", "밑단", "hem", "hemwidth", "裾幅", "すそ幅", "すそ周り"],
    "가로": ["가로", "너비", "width", "横", "幅"],
    "세로": ["세로", "높이", "height", "縦", "高さ"],
    "폭": ["폭", "깊이", "마치", "depth", "マチ", "奥行き"],
    "손잡이": ["손잡이", "핸들", "handle", "持ち手"],
    "스트랩": ["스트랩", "strap", "shoulderstrap", "ショルダー", "ストラップ"],
    "머리둘레": ["머리둘레", "머리", "circumference", "頭周り", "頭囲"],
    "챙길이": ["챙길이", "챙", "brim", "つば"],
    "발볼": ["발볼", "width", "横幅", "ワイズ"],
    "발길이": ["발길이", "footlength", "足長", "インソール", "アウトソール", "insole", "outsole"],
    "굽높이": ["굽높이", "heel", "heelheight", "ヒール", "ヒール高"],
    # Eyewear specific
    "フレーム縦": ["フレーム縦", "프레임세로", "프레임높이"],
    "フレーム横": ["フレーム横", "프레임가로", "전체너비", "프레임너비"],
    "レンズ縦": ["レンズ縦", "렌즈세로", "렌즈높이"],
    "レンズ横": ["レンズ横", "렌즈가로", "렌즈너비"],
    "テンプル": ["テンプル", "다리길이", "템플", "temple"],
    "ブリッジ": ["ブリッジ", "브릿지", "브릿지길이", "코받침너비", "bridge"],
}


def pick_measure_value_by_label(label_text: str, measure_map: Dict[str, str]) -> str:
    if not measure_map:
        return ""

    normalized_label = _normalize_measure_text(label_text)
    if not normalized_label:
        return ""

    # 1) Direct partial match
    for key, value in measure_map.items():
        if not (value or "").strip():
            continue
        nk = _normalize_measure_text(key)
        if nk and (nk in normalized_label or normalized_label in nk):
            return value

    # 2) Alias match
    for _, aliases in MEASURE_ALIASES.items():
        normalized_aliases = [_normalize_measure_text(alias) for alias in aliases if _normalize_measure_text(alias)]
        if not any(alias in normalized_label or normalized_label in alias for alias in normalized_aliases):
            continue
        for key, value in measure_map.items():
            if not (value or "").strip():
                continue
            nk = _normalize_measure_text(key)
            if any(alias in nk or nk in alias for alias in normalized_aliases):
                return value

    return ""
