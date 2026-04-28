from __future__ import annotations

import re
import urllib.parse


def normalize_image_source(src: str) -> str:
    if not src:
        return ""
    normalized = src.strip()
    if normalized.startswith("//"):
        normalized = f"https:{normalized}"
    elif normalized.startswith("/"):
        normalized = f"https://image.msscdn.net{normalized}"
    normalized = normalized.split("?")[0]
    normalized = normalized.replace("https://image.msscdn.net/thumbnails/", "https://image.msscdn.net/")
    normalized = normalized.replace("/thumbnails/", "/")
    return normalized


def build_image_identity_key(image_url: str) -> str:
    normalized = normalize_image_source(image_url)
    parsed = urllib.parse.urlparse(normalized)
    path = parsed.path.lower()
    path = re.sub(r"_(?:60|80|125|250|500|big)(\.[a-z0-9]+)$", r"\1", path)
    return path

