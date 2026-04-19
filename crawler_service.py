"""Crawler helper functions (low-risk extraction/parsing utilities)."""

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup


def has_hangul(text: str) -> bool:
    """문자열에 한글이 포함되어 있는지 확인"""
    return any("\uac00" <= char <= "\ud7a3" for char in text)


def fetch_json(url: str) -> Dict[str, object]:
    """JSON API를 호출한다"""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def sanitize_path_component(value: str) -> str:
    """파일/폴더명으로 안전한 문자열로 정리한다"""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ._") or "item"


def build_image_folder_name(row_num: int, row_start: int, product_name: str) -> str:
    """이미지 폴더명을 '행번호. 상품명' 형식으로 만든다"""
    display_index = max(1, row_num - row_start + 1)
    safe_name = sanitize_path_component(product_name or "상품명 미확인")
    return f"{display_index}. {safe_name}"


def normalize_image_source(src: str) -> str:
    """무신사 이미지 URL을 다운로드 가능한 형태로 정규화한다"""
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
    """같은 원본 사진의 다른 사이즈 URL을 하나로 묶기 위한 키를 만든다"""
    normalized = normalize_image_source(image_url)
    parsed = urllib.parse.urlparse(normalized)
    path = parsed.path.lower()
    path = re.sub(r"_(?:60|80|125|250|500|big)(\.[a-z0-9]+)$", r"\1", path)
    return path


def extract_musinsa_thumbnail_urls(
    soup: BeautifulSoup,
    product_json: Dict[str, object],
    goods_no: str,
    max_thumbnail_images: int,
) -> List[str]:
    """무신사 상품 페이지에서 이미지 URL 목록을 추출한다"""
    candidates: List[str] = []
    seen_urls = set()
    seen_images = set()

    def add_candidate(src: str):
        normalized = normalize_image_source(src)
        if not normalized or normalized in seen_urls:
            return
        if "goods_img" not in normalized and "prd_img" not in normalized:
            return
        if goods_no and goods_no not in normalized:
            return
        identity_key = build_image_identity_key(normalized)
        if identity_key in seen_images:
            return
        seen_urls.add(normalized)
        seen_images.add(identity_key)
        candidates.append(normalized)

    if isinstance(product_json, dict):
        image_field = product_json.get("image")
        if isinstance(image_field, str):
            add_candidate(image_field)
        elif isinstance(image_field, list):
            for item in image_field:
                if isinstance(item, str):
                    add_candidate(item)

    og_image = soup.select_one('meta[property="og:image"]')
    if og_image:
        add_candidate(og_image.get("content", ""))

    for img in soup.select("img"):
        for attr in ("src", "data-src", "data-original", "data-lazy-src"):
            src = img.get(attr, "")
            if not src:
                continue
            if goods_no and goods_no not in src:
                continue
            add_candidate(src)

    return candidates[:max_thumbnail_images]
