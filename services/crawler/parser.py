from __future__ import annotations

import re


def has_hangul(text: str) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in text)


def sanitize_path_component(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ._") or "item"


def build_image_folder_name(row_num: int, row_start: int, product_name: str) -> str:
    display_index = max(1, row_num - row_start + 1)
    safe_name = sanitize_path_component(product_name or "item")
    return f"{display_index}. {safe_name}"

