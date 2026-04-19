"""Crawler helper functions for Musinsa extraction/parsing."""

import json
import re
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup


_COLOR_NAME_MAP: Dict[str, str] | None = None


def has_hangul(text: str) -> bool:
    """Return True if the text contains Hangul characters."""
    return any("\uac00" <= char <= "\ud7a3" for char in text)


def fetch_json(url: str) -> Dict[str, object]:
    """Call JSON API and return parsed dictionary."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def sanitize_path_component(value: str) -> str:
    """Sanitize filename/foldername component."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ._") or "item"


def build_image_folder_name(row_num: int, row_start: int, product_name: str) -> str:
    """Build image folder name in '<index>. <product>' format."""
    display_index = max(1, row_num - row_start + 1)
    safe_name = sanitize_path_component(product_name or "상품명 미확인")
    return f"{display_index}. {safe_name}"


def normalize_image_source(src: str) -> str:
    """Normalize image URL to a downloadable Musinsa CDN URL."""
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
    """Build key for deduplicating same image in different sizes."""
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
    """Extract product image URLs from Musinsa product page."""
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


def extract_product_json(soup: BeautifulSoup) -> Dict[str, object]:
    """Extract Product object from JSON-LD scripts."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_text = script.get_text(strip=True)
        if not raw_text:
            continue
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            continue

        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("@type") == "Product":
                return candidate
    return {}


def extract_mss_product_state(soup: BeautifulSoup) -> Dict[str, object]:
    """Extract window.__MSS__.product.state or __MSS_FE__.product.state JSON."""
    patterns = [
        r"window\.__MSS__\.product\.state\s*=\s*(\{.*?\});",
        r"window\.__MSS_FE__\.product\.state\s*=\s*(\{.*?\});",
    ]

    for script in soup.find_all("script"):
        script_text = script.get_text(strip=False)
        if not script_text:
            continue

        for pattern in patterns:
            match = re.search(pattern, script_text, re.DOTALL)
            if not match:
                continue
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return {}


def clean_product_name(name: str) -> str:
    """Remove color/sku suffix from product name."""
    if not name:
        return "상품명 미확인"

    cleaned = re.sub(r"\s*/\s*[A-Z0-9-]+$", "", name).strip()
    if " - " in cleaned:
        cleaned = cleaned.split(" - ", 1)[0].strip()
    cleaned = re.sub(r"\s+(?:M|W|K|FREE|O/S|OS)$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or "상품명 미확인"


def split_name_and_color(raw_name: str) -> Tuple[str, str]:
    """Split product name and color suffix."""
    if not raw_name:
        return "", ""

    text = re.sub(r"\s*/\s*[A-Z0-9-]+$", "", raw_name).strip()
    if " - " not in text:
        return text, ""

    name_part, color_part = text.split(" - ", 1)
    return name_part.strip(), color_part.strip()


def is_color_count_placeholder(text: str) -> bool:
    """Return True when text means only color count (e.g. 2color)."""
    value = (text or "").strip().lower()
    if not value:
        return False
    compact = re.sub(r"\s+", "", value)

    if re.fullmatch(r"^\d+(?:color|colors|colour|colours)$", compact):
        return True
    if re.fullmatch(r"^(?:color|colors|colour|colours)\d+$", compact):
        return True

    korean_suffixes = ("\uceec\ub7ec", "\uc0c9\uc0c1")
    m_prefix = re.fullmatch(r"^(\d+)(.+)$", compact)
    if m_prefix and m_prefix.group(2) in korean_suffixes:
        return True
    m_suffix = re.fullmatch(r"^(.+?)(\d+)$", compact)
    if m_suffix and m_suffix.group(1) in korean_suffixes:
        return True
    return False


def extract_color_from_name(raw_name: str) -> str:
    """Extract color hint from product name text."""
    if not raw_name:
        return ""

    cleaned = re.sub(r"\s*/\s*[A-Z0-9-]+$", "", raw_name).strip()
    _, color_part = split_name_and_color(cleaned)
    if color_part and not is_color_count_placeholder(color_part):
        return color_part

    bracket_match = re.search(r"\[([^\[\]]{1,50})\]\s*$", cleaned)
    if bracket_match:
        candidate = bracket_match.group(1).strip()
        if not is_color_count_placeholder(candidate):
            return candidate

    paren_match = re.search(r"\(([^()]{1,50})\)\s*$", cleaned)
    if paren_match:
        candidate = paren_match.group(1).strip()
        if (
            not is_color_count_placeholder(candidate)
            and (any(token in candidate for token in ["/", ",", "-", ":"]) or has_hangul(candidate))
        ):
            return candidate

    return ""


def normalize_korean_color(color_text: str) -> str:
    """Normalize Korean color string for sheet output."""
    if not color_text:
        return ""

    normalized = color_text.replace(":", ", ")
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,")

    tokens = []
    for token in normalized.split(","):
        value = token.strip()
        if value.endswith("색") and len(value) > 1 and has_hangul(value):
            value = value[:-1].strip()
        if value and not is_color_count_placeholder(value):
            tokens.append(value)

    return ", ".join(tokens)


def normalize_english_color(color_text: str) -> str:
    """Normalize English color string for sheet output."""
    if not color_text:
        return ""

    normalized = color_text.replace("/", ", ")
    normalized = re.sub(r"\s*-\s*", ", ", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,")
    return normalized.title()


def extract_brand_text(product_json: Dict[str, object], title_text: str) -> str:
    """Extract brand text from product JSON/title."""
    brand = product_json.get("brand", {}) if isinstance(product_json, dict) else {}
    if isinstance(brand, dict) and brand.get("name"):
        return str(brand["name"]).strip()

    match = re.match(r"([^()]+)\(", title_text)
    if match:
        return match.group(1).strip()
    return ""


def get_color_name_map() -> Dict[str, str]:
    """Load Musinsa color code map lazily."""
    global _COLOR_NAME_MAP
    if _COLOR_NAME_MAP is not None:
        return _COLOR_NAME_MAP

    try:
        payload = fetch_json("https://goods-detail.musinsa.com/api2/goods/color-images")
        color_images = payload.get("data", {}).get("colorImages", [])
        _COLOR_NAME_MAP = {
            str(item.get("colorId")): str(item.get("colorName", "")).strip()
            for item in color_images
            if item.get("colorId") is not None and item.get("colorName")
        }
    except Exception:
        _COLOR_NAME_MAP = {}
    return _COLOR_NAME_MAP


def fetch_goods_options(goods_no: str, goods_sale_type: str, opt_kind_cd: str) -> Dict[str, object]:
    """Fetch goods options metadata."""
    if not goods_no:
        return {}

    sale_type = goods_sale_type or "SALE"
    opt_kind = opt_kind_cd or "CLOTHES"
    url = (
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options"
        f"?goodsSaleType={sale_type}&optKindCd={opt_kind}"
    )
    try:
        payload = fetch_json(url)
        return payload.get("data", {})
    except Exception:
        return {}


def fetch_actual_size(goods_no: str) -> Dict[str, object]:
    """Fetch actual size table metadata."""
    if not goods_no:
        return {}

    url = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/actual-size"
    try:
        payload = fetch_json(url)
        return payload.get("data", {})
    except Exception:
        return {}


def extract_actual_size_text(goods_no: str) -> str:
    """Extract actual-size rows as one-line text."""
    data = fetch_actual_size(goods_no)
    if not isinstance(data, dict):
        return ""

    rows = data.get("sizes")
    if not isinstance(rows, list):
        return ""

    result_rows: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        size_name = str(row.get("name", "")).strip()
        values = row.get("values")
        if not isinstance(values, list) or not values:
            values = row.get("items")
        if not isinstance(values, list) or not values:
            continue

        parts: List[str] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            measure_name = str(item.get("name", "")).strip()
            raw_value = item.get("value", "")
            if isinstance(raw_value, (int, float)):
                measure_value = f"{raw_value:g}"
            else:
                measure_value = str(raw_value).strip()
            if not measure_name or not measure_value:
                continue
            parts.append(f"{measure_name} {measure_value}")

        if not parts:
            continue

        if size_name:
            result_rows.append(f"{size_name}: {', '.join(parts)}")
        else:
            result_rows.append(", ".join(parts))

    return " | ".join(result_rows)


def extract_brand_en_from_musinsa(driver, product_url: str) -> str:
    """Extract English brand from current page state or brand page."""
    _ = product_url  # Keep signature-compatible; current logic uses page source + brand slug.
    try:
        try:
            soup = BeautifulSoup(driver.page_source, "html.parser")
            mss_state = extract_mss_product_state(soup)
            brand_info = mss_state.get("brandInfo") if isinstance(mss_state, dict) else None
            if isinstance(brand_info, dict):
                direct_en = str(brand_info.get("brandEnglishName", "")).strip()
                if direct_en:
                    return direct_en
            direct_slug = str(mss_state.get("brand", "")).strip() if isinstance(mss_state, dict) else ""
            if direct_slug:
                return direct_slug.upper().replace("-", " ")
        except Exception:
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        slug = ""
        for anchor in soup.select('a[href*="/brand/"]'):
            href = anchor.get("href") or ""
            match = re.search(r"/brand/([a-z0-9_-]+)", href)
            if match:
                slug = match.group(1)
                break
        if not slug:
            return ""

        brand_url = f"https://www.musinsa.com/brand/{slug}"
        try:
            req = urllib.request.Request(brand_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            m_og = re.search(
                r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if m_og:
                og_title = m_og.group(1).strip()
                m_en = re.search(r"\(([A-Za-z0-9\s&\-\.'/]+)\)", og_title)
                if m_en:
                    return re.sub(r"\s+", " ", m_en.group(1)).strip()
        except Exception:
            pass

        return slug.upper().replace("-", " ")
    except Exception:
        return ""
