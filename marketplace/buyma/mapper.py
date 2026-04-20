"""BUYMA-specific pure mapping helpers."""

import re
import unicodedata
from typing import Callable, Dict, List

from marketplace.common.interfaces import MarketplacePayload, MarketplaceRow, MarketplaceRowMapper


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


def build_buyma_form_payload(
    row_data: MarketplaceRow,
    *,
    normalize_actual_size_for_upload: Callable[[str], str],
    expand_color_abbreviations: Callable[[str], str],
    split_color_values: Callable[[str], List[str]],
    resolve_image_files: Callable[[str], List[str]],
) -> MarketplacePayload:
    """Build a browser-agnostic BUYMA form payload from a source row."""
    brand = (row_data.get("brand_en") or row_data.get("brand") or "").strip()
    name_en = (row_data.get("product_name_en") or row_data.get("product_name_kr") or "").strip()

    color_en_raw = (row_data.get("color_en") or "").strip()
    color_raw = (row_data.get("color_en") or row_data.get("color_kr") or "").strip()
    color_en = expand_color_abbreviations(color_en_raw)
    color = expand_color_abbreviations(color_raw)
    if color_en.lower() == "none":
        color_en = ""
    if color.lower() == "none":
        color = ""

    color_values = split_color_values(color_en or color)
    if not color_values and color:
        color_values = [color]

    raw_buyma_price = re.sub(r"[^\d]", "", row_data.get("buyma_price", ""))
    buyma_price_value = int(raw_buyma_price) if raw_buyma_price else 0
    adjusted_price = max(0, buyma_price_value - 10) if raw_buyma_price else 0

    return {
        "row_num": row_data.get("row_num"),
        "brand": brand,
        "product_name_kr": row_data.get("product_name_kr", ""),
        "name_en": name_en,
        "color": color,
        "color_en": color_en,
        "color_values": color_values,
        "size_text": row_data.get("size", "") or "",
        "actual_size_text": normalize_actual_size_for_upload(row_data.get("actual_size", "")),
        "image_files": resolve_image_files(row_data.get("image_paths", "")),
        "buyma_price_digits": raw_buyma_price,
        "adjusted_price": adjusted_price,
        "sheet_category_large": (row_data.get("musinsa_category_large") or "").strip(),
        "sheet_category_middle": (row_data.get("musinsa_category_middle") or "").strip(),
        "sheet_category_small": (row_data.get("musinsa_category_small") or "").strip(),
    }


class BuymaRowMapper(MarketplaceRowMapper):
    """Thin adapter around the existing BUYMA payload builder."""

    def __init__(
        self,
        *,
        normalize_actual_size_for_upload: Callable[[str], str],
        expand_color_abbreviations: Callable[[str], str],
        split_color_values: Callable[[str], List[str]],
        resolve_image_files: Callable[[str], List[str]],
    ) -> None:
        self._normalize_actual_size_for_upload = normalize_actual_size_for_upload
        self._expand_color_abbreviations = expand_color_abbreviations
        self._split_color_values = split_color_values
        self._resolve_image_files = resolve_image_files

    def map_row(self, row_data: MarketplaceRow) -> MarketplacePayload:
        return build_buyma_form_payload(
            row_data,
            normalize_actual_size_for_upload=self._normalize_actual_size_for_upload,
            expand_color_abbreviations=self._expand_color_abbreviations,
            split_color_values=self._split_color_values,
            resolve_image_files=self._resolve_image_files,
        )
