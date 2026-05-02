"""BUYMA validation and parsing helpers."""

import re
from typing import Dict, List


def normalize_actual_size_for_upload(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in {"none", "n/a", "na"}:
        return ""
    if text in {"못찾음", "없음", "-"}:
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


def extract_actual_measure_map(actual_size_text: str) -> Dict[str, str]:
    if not actual_size_text:
        return {}

    pairs: Dict[str, str] = {}
    normalized = actual_size_text.replace("\n", " ").replace("\r", " ")
    label_pattern = r"([가-힣A-Za-z一-龯ぁ-んァ-ンー\s]{1,30})"
    for key, val in re.findall(label_pattern + r"\s*[:：]?\s*(-?\d+(?:\.\d+)?)", normalized):
        clean_key = key.strip()
        clean_val = val.strip()
        if clean_key and clean_val and clean_key not in pairs:
            pairs[clean_key] = clean_val
    return pairs


def extract_actual_size_rows(actual_size_text: str) -> Dict[str, Dict[str, str]]:
    rows: Dict[str, Dict[str, str]] = {}
    text = (actual_size_text or "").strip()
    if not text:
        return rows

    for chunk in [c.strip() for c in text.split("|") if c.strip()]:
        match = re.match(r"^([^:]+)\s*:\s*(.+)$", chunk)
        if not match:
            continue
        size_name = match.group(1).strip()
        body = match.group(2).strip()
        measure_map: Dict[str, str] = {}
        for part in [p.strip() for p in body.split(",") if p.strip()]:
            measure_match = re.match(r"^(.+?)\s+(-?\d+(?:\.\d+)?)$", part)
            if not measure_match:
                continue
            key = measure_match.group(1).strip()
            value = measure_match.group(2).strip()
            if key and value:
                measure_map[key] = value
        if measure_map:
            rows[size_name] = measure_map
    return rows


MEASURE_ALIASES: Dict[str, List[str]] = {
    "총장": ["총장", "기장", "着丈", "総丈", "全長", "length"],
    "어깨너비": ["어깨너비", "어깨", "肩幅", "shoulder"],
    "가슴단면": ["가슴단면", "가슴", "身幅", "胸囲", "バスト", "chest"],
    "소매길이": ["소매길이", "袖丈", "裄丈", "sleeve"],
    "허리단면": ["허리단면", "허리", "ウエスト", "胴囲", "waist"],
    "엉덩이단면": ["엉덩이단면", "엉덩이", "ヒップ", "hip"],
    "허벅지단면": ["허벅지단면", "허벅지", "ワタリ", "もも", "もも周り", "thigh"],
    "밑위": ["밑위", "股上", "rise"],
    "밑아래": ["밑아래", "안쪽기장", "인심", "股下", "inseam"],
    "밑단단면": ["밑단단면", "밑단", "裾幅", "すそ", "すそ周り", "hem"],
    "발길이": ["발길이", "足長", "アウトソール"],
    "발볼": ["발볼", "足幅", "ワイズ", "幅"],
    "굽높이": ["굽높이", "힐", "ヒール高", "heel"],
}


def pick_measure_value_by_label(label_text: str, measure_map: Dict[str, str]) -> str:
    if not measure_map:
        return ""

    def _norm(value: str) -> str:
        return re.sub(r"\s+", "", (value or "").strip().lower())

    normalized_label = _norm(label_text)
    if not normalized_label:
        return ""

    def _value_for_aliases(aliases: List[str]) -> str:
        normalized_aliases = [_norm(alias) for alias in aliases if _norm(alias)]
        for key, value in measure_map.items():
            if not (value or "").strip():
                continue
            normalized_key = _norm(key)
            if any(alias in normalized_key or normalized_key in alias for alias in normalized_aliases):
                return value
        return ""

    for key, value in measure_map.items():
        if _norm(key) in normalized_label and (value or "").strip():
            return value

    for base_key, aliases in MEASURE_ALIASES.items():
        normalized_aliases = [_norm(alias) for alias in aliases if _norm(alias)]

        if not any(alias in normalized_label or normalized_label in alias for alias in normalized_aliases):
            continue

        value = _value_for_aliases([base_key, *aliases])
        if value:
            return value

    return ""
