"""BUYMA-specific pure mapping helpers."""

import re
import unicodedata
from typing import List


def normalize_buyma_title_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def buyma_char_units(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in {"F", "W", "A"} else 1


def buyma_title_units(text: str) -> int:
    return sum(buyma_char_units(ch) for ch in (text or ""))


def slice_buyma_title_by_units(text: str, limit_units: int) -> str:
    if limit_units <= 0:
        return ""
    out: List[str] = []
    used = 0
    for ch in text:
        units = buyma_char_units(ch)
        if used + units > limit_units:
            break
        out.append(ch)
        used += units
    return "".join(out)


def truncate_buyma_title_text(text: str, limit: int) -> str:
    text = normalize_buyma_title_text(text)
    if limit <= 0 or buyma_title_units(text) <= limit:
        return text
    if limit <= 3:
        return slice_buyma_title_by_units(text, limit)

    ellipsis = "..."
    ellipsis_units = buyma_title_units(ellipsis)
    body_limit = max(0, limit - ellipsis_units)
    body = slice_buyma_title_by_units(text, body_limit).rstrip()
    return body + ellipsis


def build_buyma_product_title(brand_en: str, name_en: str, color_en: str, max_length: int = 0) -> str:
    brand_en = normalize_buyma_title_text(brand_en)
    name_en = normalize_buyma_title_text(name_en)
    color_en = normalize_buyma_title_text(color_en)

    candidates = []
    full_parts = []
    if brand_en:
        full_parts.append(f"[{brand_en}]")
    if name_en:
        full_parts.append(name_en)
    if color_en:
        full_parts.append(color_en)
    candidates.append(normalize_buyma_title_text(" ".join(full_parts)))

    no_bracket_parts = []
    if brand_en:
        no_bracket_parts.append(brand_en)
    if name_en:
        no_bracket_parts.append(name_en)
    if color_en:
        no_bracket_parts.append(color_en)
    candidates.append(normalize_buyma_title_text(" ".join(no_bracket_parts)))

    name_color = normalize_buyma_title_text(" ".join([part for part in [name_en, color_en] if part]))
    if name_color:
        candidates.append(name_color)
    if name_en:
        candidates.append(name_en)

    seen = set()
    unique_candidates = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)

    if max_length > 0:
        for candidate in unique_candidates:
            if buyma_title_units(candidate) <= max_length:
                return candidate
        if name_en:
            return truncate_buyma_title_text(name_en, max_length)
        return truncate_buyma_title_text(unique_candidates[0] if unique_candidates else "", max_length)

    return unique_candidates[0] if unique_candidates else ""


def build_buyma_title_retry_candidates(brand_en: str, name_en: str, color_en: str, max_length: int) -> List[str]:
    brand = normalize_buyma_title_text(brand_en)
    name = normalize_buyma_title_text(name_en)
    color = normalize_buyma_title_text(color_en)

    def _fit(text: str) -> str:
        text = normalize_buyma_title_text(text)
        if not text:
            return ""
        if max_length > 0 and buyma_title_units(text) > max_length:
            return truncate_buyma_title_text(text, max_length)
        return text

    candidates: List[str] = []
    candidates.append(_fit(" ".join([part for part in [f"[{brand}]" if brand else "", name, color] if part])))
    candidates.append(_fit(" ".join([part for part in [f"[{brand}]" if brand else "", name] if part])))
    candidates.append(_fit(name))

    base_name = name
    if max_length > 0:
        candidates.append(truncate_buyma_title_text(base_name, max_length))
        candidates.append(truncate_buyma_title_text(base_name, max(10, max_length - 3)))
        candidates.append(truncate_buyma_title_text(base_name, max(8, max_length - 6)))
    else:
        candidates.append(truncate_buyma_title_text(base_name, 60))
        candidates.append(truncate_buyma_title_text(base_name, 45))

    unique: List[str] = []
    seen = set()
    for candidate in candidates:
        candidate = normalize_buyma_title_text(candidate)
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique
