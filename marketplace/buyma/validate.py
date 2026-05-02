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
    try:
        return float(text.replace(",", "")) == 0.0
    except Exception:
        return False


def extract_actual_measure_map(actual_size_text: str) -> Dict[str, str]:
    if not actual_size_text:
        return {}

    pairs: Dict[str, str] = {}
    normalized = actual_size_text.replace("\n", " ").replace("\r", " ")
    for key, val in re.findall(r"([가-힣A-Za-z ]{1,20})\s*[:：]?\s*(-?\d+(?:\.\d+)?)", normalized):
        clean_key = key.strip()
        clean_val = val.strip()
        if clean_key and not is_blank_or_zero_measure_value(clean_val) and clean_key not in pairs:
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
            if key and not is_blank_or_zero_measure_value(value):
                measure_map[key] = value
        if measure_map:
            rows[size_name] = measure_map
    return rows


MEASURE_ALIASES: Dict[str, List[str]] = {
    "총장": ["총장", "着丈", "総丈", "全長", "length"],
    "어깨너비": ["어깨너비", "肩幅", "shoulder"],
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
    lowered_label = (label_text or "").strip().lower()
    if not lowered_label:
        return ""

    for key, value in measure_map.items():
        if key and key.lower() in lowered_label and not is_blank_or_zero_measure_value(value):
            return value

    for base_key, aliases in MEASURE_ALIASES.items():
        if not any(alias.lower() in lowered_label for alias in aliases):
            continue
        if base_key in measure_map:
            value = measure_map[base_key]
            if not is_blank_or_zero_measure_value(value):
                return value
        for alias in aliases:
            if alias in measure_map:
                value = measure_map[alias]
                if not is_blank_or_zero_measure_value(value):
                    return value
    return ""
