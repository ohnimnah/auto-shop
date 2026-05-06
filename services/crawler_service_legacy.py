"""Crawler helper functions for Musinsa extraction/parsing."""

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup
try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except Exception:  # pragma: no cover
    By = None  # type: ignore[assignment]
    EC = None  # type: ignore[assignment]
    WebDriverWait = None  # type: ignore[assignment]

from models.product_model import Product


_COLOR_NAME_MAP: Dict[str, str] | None = None
_EN_COLOR_WORDS = {
    "black",
    "blue",
    "brown",
    "beige",
    "cream",
    "charcoal",
    "gray",
    "grey",
    "green",
    "ivory",
    "khaki",
    "navy",
    "orange",
    "pink",
    "purple",
    "red",
    "silver",
    "white",
    "yellow",
    "melange",
    "natural",
    "oatmeal",
}
_EN_COLOR_MODIFIERS = {"light", "dark", "deep", "pale", "heather", "m", "l"}
_KR_COLOR_WORDS = {
    "검정",
    "검정색",
    "블랙",
    "흑청",
    "화이트",
    "흰색",
    "아이보리",
    "크림",
    "베이지",
    "브라운",
    "갈색",
    "카멜",
    "그레이",
    "그레",
    "회색",
    "차콜",
    "멜란지",
    "네이비",
    "남색",
    "블루",
    "파랑",
    "파란색",
    "청색",
    "연청",
    "중청",
    "진청",
    "인디고",
    "스카이블루",
    "라이트블루",
    "그린",
    "초록",
    "초록색",
    "카키",
    "올리브",
    "레드",
    "빨강",
    "빨간색",
    "버건디",
    "와인",
    "핑크",
    "분홍",
    "퍼플",
    "보라",
    "옐로우",
    "노랑",
    "오렌지",
    "실버",
}
_KR_COLOR_MODIFIERS = {"라이트", "다크", "딥", "연", "진", "멜란지"}


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


def find_product_price_candidates_from_state(data) -> List[int]:
    """Recursively collect effective product price candidates from mss_state.

    When Musinsa exposes a discount amount, use ``base price - discount``.
    For example: salePrice 38,000 and couponDcPrice 3,800 -> 34,200.
    """
    key_priority = (
        "saleprice",
        "goodsprice",
        "discountprice",
        "currentprice",
        "normalprice",
        "listprice",
    )
    excluded_key_tokens = (
        "dcprice",
        "discountamount",
        "discountamt",
        "discountrate",
        "couponprice",
        "couponappliedprice",
        "couponapplyprice",
        "benefitprice",
        "maxbenefitprice",
    )
    discount_key_tokens = (
        "dcprice",
        "discountamount",
        "discountamt",
        "coupondiscountamount",
        "coupondiscountprice",
    )
    found = []
    all_base_prices: List[int] = []
    all_discount_amounts: List[int] = []

    def _numeric(value) -> int | None:
        if isinstance(value, (int, float)):
            iv = int(value)
            return iv if iv >= 0 else None
        return None

    def _collect_dict_values(obj: dict, tokens: tuple[str, ...], *, excluded: tuple[str, ...] = ()) -> List[int]:
        values: List[int] = []
        for key, value in obj.items():
            lk = str(key).lower().replace("_", "")
            if excluded and any(token in lk for token in excluded):
                continue
            if any(token in lk for token in tokens):
                iv = _numeric(value)
                if iv is not None:
                    values.append(iv)
        return values

    def walk(obj):
        if isinstance(obj, dict):
            base_prices = _collect_dict_values(obj, key_priority, excluded=excluded_key_tokens)
            discount_amounts = _collect_dict_values(obj, discount_key_tokens)
            for base_price in base_prices:
                for discount_amount in discount_amounts:
                    effective_price = base_price - discount_amount
                    if 1000 <= effective_price <= base_price:
                        found.append((-1, effective_price))
            all_base_prices.extend([value for value in base_prices if value >= 1000])
            all_discount_amounts.extend([value for value in discount_amounts if value > 0])

            for k, v in obj.items():
                lk = str(k).lower().replace("_", "")
                if any(token in lk for token in excluded_key_tokens):
                    iv = _numeric(v)
                    if iv is not None and any(token in lk for token in discount_key_tokens):
                        all_discount_amounts.append(iv)
                    walk(v)
                    continue
                iv = _numeric(v)
                if iv is not None:
                    if iv >= 1000:
                        for idx, key in enumerate(key_priority):
                            if key in lk:
                                found.append((idx, iv))
                                break
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    for base_price in all_base_prices:
        for discount_amount in all_discount_amounts:
            effective_price = base_price - discount_amount
            if 1000 <= effective_price <= base_price:
                found.append((-1, effective_price))
    found.sort(key=lambda x: (x[0], x[1]))
    return [v for _, v in found]


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
    cleaned = remove_trailing_product_name_suffix(cleaned)
    cleaned = re.sub(r"\s+(?:M|W|K|FREE|O/S|OS)$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or "상품명 미확인"


def is_likely_color_suffix(text: str) -> bool:
    """Return whether a product-name suffix looks like a color name."""
    candidate = (text or "").strip(" \t\r\n-_/[](){}")
    if not candidate or is_color_count_placeholder(candidate):
        return False

    normalized = re.sub(r"[/_,:+]", " ", candidate)
    normalized = re.sub(r"\s*-\s*", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized or len(normalized) > 40:
        return False

    if has_hangul(normalized):
        tokens = [token.strip() for token in normalized.split() if token.strip()]
        if not tokens:
            return False
        color_hits = 0
        for token in tokens:
            if token in _KR_COLOR_MODIFIERS:
                continue
            if token in _KR_COLOR_WORDS or (token.endswith("색") and len(token) > 1):
                color_hits += 1
                continue
            return False
        return color_hits > 0

    tokens = re.findall(r"[a-z]+", normalized.lower())
    if not tokens:
        return False
    color_hits = 0
    for token in tokens:
        if token in _EN_COLOR_MODIFIERS:
            continue
        if token in _EN_COLOR_WORDS:
            color_hits += 1
            continue
        return False
    return color_hits > 0


def is_removable_product_name_suffix(text: str) -> bool:
    """Return whether a trailing product-name marker should be removed."""
    return is_color_count_placeholder(text) or is_likely_color_suffix(text) or is_likely_sku_suffix(text)


def is_likely_sku_suffix(text: str) -> bool:
    """Return whether text looks like a trailing product code."""
    candidate = (text or "").strip(" \t\r\n-_/[](){}")
    if not candidate or has_hangul(candidate):
        return False
    if len(candidate) < 5 or len(candidate) > 32:
        return False
    if " " in candidate:
        return False
    if not re.search(r"[A-Za-z]", candidate) or not re.search(r"\d", candidate):
        return False
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]", candidate):
        return False
    if re.fullmatch(r"\d+(?:COLOR|COLORS|COLOUR|COLOURS)", candidate, re.IGNORECASE):
        return False
    return True


def remove_trailing_product_name_suffix(name: str) -> str:
    """Remove trailing color/count/sku markers from a product name."""
    cleaned = (name or "").strip()
    if not cleaned:
        return ""

    separator_match = re.match(r"^(?P<base>.+?)\s+-\s+(?P<suffix>[^-]+)$", cleaned)
    if separator_match and is_removable_product_name_suffix(separator_match.group("suffix")):
        return separator_match.group("base").strip()

    bracket_match = re.match(r"^(?P<base>.+?)\s*[\[\(](?P<suffix>[^\[\]\(\)]{1,50})[\]\)]\s*$", cleaned)
    if bracket_match and is_removable_product_name_suffix(bracket_match.group("suffix")):
        return bracket_match.group("base").strip()

    words = cleaned.split()
    for count in range(min(3, len(words) - 1), 0, -1):
        suffix = " ".join(words[-count:])
        if is_removable_product_name_suffix(suffix):
            return " ".join(words[:-count]).strip()
    return cleaned


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
    cleaned = re.sub(r"_[A-Z0-9-]{4,}$", "", cleaned).strip()
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
            and (
                any(token in candidate for token in ["/", ",", "-", ":"])
                or has_hangul(candidate)
                or re.fullmatch(r"[A-Z][A-Z0-9\s/-]{1,30}", candidate.upper()) is not None
            )
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


def extract_musinsa_categories(soup: BeautifulSoup, mss_state: Dict[str, object]) -> Tuple[str, str, str]:
    """Extract Musinsa category large/middle/small from state or breadcrumb."""
    key_candidates = [
        ("categoryDepth1Name", "categoryDepth2Name", "categoryDepth3Name"),
        ("dispCatNm1", "dispCatNm2", "dispCatNm3"),
        ("itemCategoryDepth1Name", "itemCategoryDepth2Name", "itemCategoryDepth3Name"),
    ]
    for k1, k2, k3 in key_candidates:
        v1 = str(mss_state.get(k1, "")).strip()
        v2 = str(mss_state.get(k2, "")).strip()
        v3 = str(mss_state.get(k3, "")).strip()
        if v1 or v2 or v3:
            return v1, v2, v3

    for container_key in ("category", "categoryInfo", "itemCategory", "displayCategory"):
        container = mss_state.get(container_key)
        if not isinstance(container, dict):
            continue
        for k1, k2, k3 in key_candidates:
            v1 = str(container.get(k1, "")).strip()
            v2 = str(container.get(k2, "")).strip()
            v3 = str(container.get(k3, "")).strip()
            if v1 or v2 or v3:
                return v1, v2, v3

        v1 = str(container.get("depth1Name", "")).strip()
        v2 = str(container.get("depth2Name", "")).strip()
        v3 = str(container.get("depth3Name", "")).strip()
        if v1 or v2 or v3:
            return v1, v2, v3

    texts: List[str] = []
    selectors = [
        'nav[aria-label*="breadcrumb"] a',
        'nav[aria-label*="Breadcrumb"] a',
        ".breadcrumb a",
        '[class*="breadcrumb"] a',
    ]
    for selector in selectors:
        tags = soup.select(selector)
        if tags:
            texts = [t.get_text(strip=True) for t in tags if t.get_text(strip=True)]
            break

    if not texts:
        return "", "", ""

    blacklist = {"홈", "HOME", "무신사", "MUSINSA"}
    cleaned = [x for x in texts if x and x not in blacklist]
    if not cleaned:
        cleaned = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw_text = script.get_text(strip=True)
            if not raw_text:
                continue
            try:
                payload = json.loads(raw_text)
            except Exception:
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                if candidate.get("@type") != "BreadcrumbList":
                    continue
                items = candidate.get("itemListElement") or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    if name and name not in blacklist:
                        cleaned.append(name)
        if not cleaned:
            return "", "", ""

    cats = cleaned[-3:]
    while len(cats) < 3:
        cats.insert(0, "")
    return cats[0], cats[1], cats[2]


def normalize_gender_label(raw_value: str) -> str:
    """Normalize gender-like values into '남성'/'여성'."""
    value = (raw_value or "").strip().lower()
    if not value:
        return ""

    male_tokens = ("남", "남성", "male", "man", "men", "mens", "m")
    female_tokens = ("여", "여성", "female", "woman", "women", "womens", "w")

    if value in male_tokens:
        return "남성"
    if value in female_tokens:
        return "여성"
    if any(t in value for t in ("남성", "male", "mens", " men")):
        return "남성"
    if any(t in value for t in ("여성", "female", "womens", " women")):
        return "여성"
    if value.startswith("m_") or value.endswith("_m"):
        return "남성"
    if value.startswith("w_") or value.endswith("_w"):
        return "여성"
    return ""


def extract_musinsa_gender_large(
    mss_state: Dict[str, object],
    cat_large: str = "",
    cat_middle: str = "",
    cat_small: str = "",
) -> str:
    """Extract gender large category from mss state/category values."""
    keys = (
        "sex",
        "gender",
        "goodsSex",
        "goodsGender",
        "targetSex",
        "targetGender",
        "displaySex",
        "sexCd",
        "genderCd",
        "sexCode",
        "genderCode",
    )

    values: List[str] = []
    for k in keys:
        values.append(str(mss_state.get(k, "")).strip())

    for container_key in ("category", "categoryInfo", "itemCategory", "displayCategory", "goods"):
        container = mss_state.get(container_key)
        if not isinstance(container, dict):
            continue
        for k in keys:
            values.append(str(container.get(k, "")).strip())

    values.extend([cat_large, cat_middle, cat_small])
    for value in values:
        label = normalize_gender_label(value)
        if label:
            return label
    return ""


def remap_categories_with_gender(
    gender_large: str,
    cat_large: str,
    cat_middle: str,
    cat_small: str,
) -> Tuple[str, str, str]:
    """Use gender as large category and shift remaining values."""
    if not gender_large:
        return cat_large, cat_middle, cat_small

    rest: List[str] = []
    for value in (cat_large, cat_middle, cat_small):
        text = (value or "").strip()
        if not text:
            continue
        if normalize_gender_label(text):
            continue
        rest.append(text)

    new_middle = rest[0] if len(rest) > 0 else ""
    new_small = rest[1] if len(rest) > 1 else ""
    return gender_large, new_middle, new_small


def find_longest_step_sequence(values: List[int], allowed_steps: Tuple[int, ...]) -> List[int]:
    """Find the longest sequence where each step is in allowed_steps."""
    if not values:
        return []

    sorted_values = sorted(set(values))
    best_sequence: List[int] = []
    current_sequence = [sorted_values[0]]

    for value in sorted_values[1:]:
        step = value - current_sequence[-1]
        if step in allowed_steps:
            current_sequence.append(value)
        else:
            if len(current_sequence) > len(best_sequence):
                best_sequence = current_sequence[:]
            current_sequence = [value]

    if len(current_sequence) > len(best_sequence):
        best_sequence = current_sequence[:]
    return best_sequence


def classify_size_token(token: str) -> str:
    """Return size token type: numeric, english, korean, mixed, other."""
    value = token.strip()
    if not value:
        return "other"
    if value.isdigit():
        return "numeric"
    if re.fullmatch(r"[A-Za-z0-9/\-+ ]+", value):
        return "english"
    if has_hangul(value):
        english_present = bool(re.search(r"[A-Za-z]", value))
        digit_present = bool(re.search(r"\d", value))
        if english_present or digit_present:
            return "mixed"
        return "korean"
    return "other"


def is_date_like_size_token(token: str) -> bool:
    """Filter date-like strings that should not be treated as sizes."""
    value = (token or "").strip()
    if not value:
        return False
    if re.fullmatch(r"(?:19|20)\d{2}[./-]\d{1,2}(?:[./-]\d{1,2})?", value):
        return True
    if re.fullmatch(r"(?:19|20)\d{6}", value):
        return True
    if re.search(r"(?:19|20)\d{2}\s*\ub144", value):
        return True
    if re.search(r"\d{1,2}\s*\uc6d4\s*\d{1,2}\s*\uc77c", value):
        return True
    return False


def normalize_size_tokens(tokens: List[str], option_kind: str = "") -> List[str]:
    """Normalize size tokens to one dominant type."""
    cleaned: List[str] = []
    seen = set()
    for token in tokens:
        value = re.sub(r"\s+", " ", str(token)).strip(" ,")
        if not value or value in seen:
            continue
        if is_date_like_size_token(value):
            continue
        seen.add(value)
        cleaned.append(value)

    if not cleaned:
        return []

    groups = {"numeric": [], "english": [], "korean": [], "mixed": []}
    for token in cleaned:
        token_type = classify_size_token(token)
        if token_type in groups:
            groups[token_type].append(token)

    option_kind = option_kind.upper()
    if groups["numeric"]:
        return groups["numeric"]
    if option_kind == "SHOES" and groups["english"]:
        return groups["english"]
    if groups["english"]:
        return groups["english"]
    if groups["korean"]:
        return groups["korean"]
    if groups["mixed"]:
        return groups["mixed"]
    return cleaned


def extract_color_from_api(goods_options: Dict[str, object]) -> str:
    """Extract and normalize colors from options API payload."""
    if not goods_options:
        return ""

    option_value_colors: List[str] = []
    for item in goods_options.get("optionItems", []):
        for option_value in item.get("optionValues", []):
            axis = str(option_value.get("optionName", "")).strip().upper()
            if axis not in {"C", "COLOR", "CLR", "COL"}:
                continue
            value = str(option_value.get("name", "")).strip() or str(option_value.get("code", "")).strip()
            if not value:
                continue
            if re.fullmatch(r"\d+", value):
                continue
            value = value.lower() if re.fullmatch(r"[A-Za-z0-9._-]{1,8}", value) else value
            if value not in option_value_colors and not is_color_count_placeholder(value):
                option_value_colors.append(value)

    if option_value_colors:
        return normalize_korean_color(", ".join(option_value_colors))

    color_map = get_color_name_map()
    color_names: List[str] = []
    for item in goods_options.get("optionItems", []):
        for color in item.get("colors", []):
            color_code = str(color.get("colorCode", "")).strip()
            color_id = str(color.get("colorId", "")).strip()
            color_name = str(color.get("colorName", "")).strip() or str(color.get("name", "")).strip()
            if not color_name:
                if color_code:
                    color_name = color_map.get(color_code, "").strip()
                if not color_name and color_id:
                    color_name = color_map.get(color_id, "").strip()
            if not color_name:
                color_name = color_code or color_id
            if color_name and not is_color_count_placeholder(color_name) and color_name not in color_names:
                color_names.append(color_name)

    return normalize_korean_color(", ".join(color_names))


def split_color_size_tokens(tokens: List[str]) -> Tuple[List[str], List[str]]:
    """Split 'KoreanColor EnglishSize' tokens into color list and size list."""
    pattern = re.compile(r"^([가-힣]+)\s+([A-Za-z0-9/+\-]+)$")
    colors: List[str] = []
    sizes: List[str] = []
    matched = 0
    for token in tokens:
        m = pattern.match(token.strip())
        if m:
            matched += 1
            color = m.group(1)
            size = m.group(2).upper()
            if color not in colors:
                colors.append(color)
            if size not in sizes:
                sizes.append(size)
    if tokens and matched >= len(tokens) * 0.5:
        return colors, sizes
    return [], list(tokens)


def extract_sizes_from_api(goods_no: str, goods_sale_type: str, opt_kind_cd: str) -> Tuple[str, str]:
    """Extract sizes/colors from options API and actual-size API."""
    option_kind = (opt_kind_cd or "").upper()
    options_data = fetch_goods_options(goods_no, goods_sale_type, opt_kind_cd)

    option_tokens: List[str] = []
    basic_options = options_data.get("basic", [])
    size_options = []
    for option in basic_options:
        option_name = str(option.get("name", "")).strip().lower()
        if option_name in {"\uc0ac\uc774\uc988", "size"}:
            size_options.append(option)

    source_options = size_options if size_options else basic_options
    for option in source_options:
        for value in option.get("optionValues", []):
            token = str(value.get("name", "")).strip()
            if token:
                option_tokens.append(token)

    detected_colors, pure_size_tokens = split_color_size_tokens(option_tokens)
    if detected_colors:
        color_str = normalize_korean_color(", ".join(detected_colors))
        normalized_sizes = normalize_size_tokens(pure_size_tokens, option_kind)
        size_str = ", ".join(normalized_sizes) if normalized_sizes else ""
        return size_str, color_str

    normalized_option_tokens = normalize_size_tokens(option_tokens, option_kind)
    if normalized_option_tokens:
        return ", ".join(normalized_option_tokens), ""

    actual_size = fetch_actual_size(goods_no)
    actual_tokens = [str(item.get("name", "")).strip() for item in actual_size.get("sizes", []) if item.get("name")]
    normalized_actual_tokens = normalize_size_tokens(actual_tokens, option_kind)
    if normalized_actual_tokens:
        return ", ".join(normalized_actual_tokens), ""
    return "", ""


def extract_sizes_from_table(soup: BeautifulSoup, option_kind: str = "") -> List[str]:
    """Extract sizes from table cells."""
    size_values: List[str] = []
    valid_text_sizes = {
        "FREE",
        "O/S",
        "OS",
        "ONE SIZE",
        "XXS",
        "XS",
        "S",
        "M",
        "L",
        "XL",
        "XXL",
        "XXXL",
        "\ud504\ub9ac",
        "\uc6d0\uc0ac\uc774\uc988",
        "\uc2a4\ubab0",
        "\ubbf8\ub514\uc6c0",
        "\ub77c\uc9c0",
        "\uc5d1\uc2a4\ub77c\uc9c0",
        "\ud22c\uc5d1\uc2a4\ub77c\uc9c0",
    }
    option_kind = option_kind.upper()

    for cell in soup.select('td[class*="StandardSizeTable"], th[class*="StandardSizeTable"]'):
        text = cell.get_text(" ", strip=True)
        if not text:
            continue
        upper_text = text.upper()
        if upper_text in valid_text_sizes or text in valid_text_sizes:
            if text not in size_values:
                size_values.append(text)
            continue
        if text.isdigit():
            number = int(text)
            if option_kind == "SHOES":
                if 200 <= number <= 300 and number % 5 == 0 and text not in size_values:
                    size_values.append(text)
            else:
                if 40 <= number <= 130 and text not in size_values:
                    size_values.append(text)

    return normalize_size_tokens(size_values, option_kind)


def extract_sizes_from_review_options(soup: BeautifulSoup, option_kind: str = "") -> List[int]:
    """Extract size candidates from review option labels."""
    option_kind = option_kind.upper()
    values: List[int] = []
    for tag in soup.select('span[class*="text-body_13px_reg"][class*="text-black"]'):
        text = tag.get_text(" ", strip=True)
        if not text.isdigit():
            continue
        number = int(text)
        if option_kind == "SHOES":
            if 200 <= number <= 300 and number % 5 == 0:
                values.append(number)
        else:
            if 40 <= number <= 130:
                values.append(number)
    return sorted(set(values))


def extract_sizes(soup: BeautifulSoup, option_kind: str = "") -> str:
    """Extract available size candidates from page."""
    text_candidates: List[str] = []
    numeric_candidates: List[int] = []
    text_sizes = {
        "FREE",
        "O/S",
        "OS",
        "ONE SIZE",
        "XXS",
        "XS",
        "S",
        "M",
        "L",
        "XL",
        "XXL",
        "XXXL",
        "\ud504\ub9ac",
        "\uc6d0\uc0ac\uc774\uc988",
        "\uc2a4\ubab0",
        "\ubbf8\ub514\uc6c0",
        "\ub77c\uc9c0",
        "\uc5d1\uc2a4\ub77c\uc9c0",
        "\ud22c\uc5d1\uc2a4\ub77c\uc9c0",
    }
    numeric_sizes = {
        44,
        55,
        66,
        77,
        88,
        90,
        95,
        100,
        105,
        110,
        115,
        120,
        130,
        135,
        140,
        145,
        150,
        155,
        160,
        200,
        205,
        210,
        215,
        220,
        225,
        230,
        235,
        240,
        245,
        250,
        255,
        260,
        265,
        270,
        275,
        280,
        285,
        290,
        295,
        300,
    }

    table_sizes = extract_sizes_from_table(soup, option_kind)
    review_sizes = extract_sizes_from_review_options(soup, option_kind)

    if review_sizes:
        if table_sizes:
            table_numbers = [int(x) for x in table_sizes if x.isdigit()]
            if table_numbers:
                low, high = min(review_sizes), max(review_sizes)
                narrowed = [n for n in table_numbers if low <= n <= high]
                narrowed = find_longest_step_sequence(narrowed, (5, 10))
                if narrowed:
                    return ", ".join(str(n) for n in narrowed)
        return ", ".join(str(n) for n in review_sizes)

    if table_sizes:
        if all(item.isdigit() for item in table_sizes):
            numeric = [int(item) for item in table_sizes]
            numeric = find_longest_step_sequence(numeric, (5, 10))
            if option_kind.upper() == "SHOES" and len(numeric) >= 4:
                return ", ".join(str(n) for n in numeric)
            if option_kind.upper() != "SHOES" and len(numeric) >= 2:
                return ", ".join(str(n) for n in numeric)
            return ""
        if len(table_sizes) >= 2:
            return ", ".join(table_sizes)
        return ""

    for text in soup.stripped_strings:
        value = text.strip()
        upper_value = value.upper()

        if upper_value in text_sizes or value in text_sizes:
            if value not in text_candidates:
                text_candidates.append(value)
        if has_hangul(value) and value in text_sizes and value not in text_candidates:
            text_candidates.append(value)
        if value.isdigit() and int(value) in numeric_sizes:
            numeric_candidates.append(int(value))

    option_kind = option_kind.upper()
    if option_kind == "SHOES" or any(number >= 200 for number in numeric_candidates):
        size_numbers = [number for number in numeric_candidates if 200 <= number <= 300]
        numeric_sequence = find_longest_step_sequence(size_numbers, (5,))
    else:
        size_numbers = [number for number in numeric_candidates if number < 200]
        numeric_sequence = find_longest_step_sequence(size_numbers, (5, 10))

    formatted_numeric = [str(number) for number in numeric_sequence]
    if option_kind.upper() == "SHOES" and len(formatted_numeric) >= 4:
        return ", ".join(formatted_numeric)
    if option_kind.upper() != "SHOES" and len(formatted_numeric) >= 2:
        return ", ".join(formatted_numeric)
    if text_candidates:
        normalized_text = normalize_size_tokens(text_candidates[:12], option_kind)
        return ", ".join(normalized_text)
    return ""


def extract_musinsa_sku(
    raw_product_name: str,
    product_name: str,
    mss_state: Dict[str, object],
    product_json: Dict[str, object] = None,
    soup: object = None,
) -> str:
    """Extract Musinsa SKU/model code from multiple sources."""
    raw_text = (raw_product_name or "").strip()

    suffix_match = re.search(r"/\s*([A-Z0-9-]{4,})\s*$", raw_text)
    if suffix_match:
        return suffix_match.group(1)

    if isinstance(mss_state, dict):
        for field in ("styleNo", "modelNo", "articleNo", "modelNm", "referenceNo"):
            val = str(mss_state.get(field, "")).strip()
            if val and re.fullmatch(r"[A-Z0-9-]{4,}", val, re.IGNORECASE):
                return val.upper()
        # Fallback: use Musinsa goodsNo when style/model code is unavailable.
        goods_no = str(mss_state.get("goodsNo", "")).strip()
        if goods_no.isdigit() and len(goods_no) >= 4:
            return goods_no

    if isinstance(product_json, dict):
        for field in ("mpn", "sku", "model", "productID"):
            val = str(product_json.get(field, "")).strip()
            if val and re.fullmatch(r"[A-Z0-9-]{4,}", val, re.IGNORECASE):
                return val.upper()

    if soup is not None:
        page_text = soup.get_text(separator=" ")
        label_match = re.search(
            r"(?:품번|스타일\s*번호|Style\s*No\.?|Model\s*No\.?|모델번호)\s*[:\s]+([A-Z0-9][A-Z0-9-]{3,})",
            page_text,
            re.IGNORECASE,
        )
        if label_match:
            return label_match.group(1).upper()

        for tag in soup.select('th, td, li, dt, dd, span[class*="info"], span[class*="detail"]'):
            text = tag.get_text(strip=True)
            sku_cell = re.search(
                r"(?:품번|스타일번호|모델번호)[\s:：]+([A-Z0-9][A-Z0-9-]{3,})",
                text,
                re.IGNORECASE,
            )
            if sku_cell:
                return sku_cell.group(1).upper()

    base_text = f"{raw_text} {product_name or ''}".strip()
    sku_patterns = [
        r"\b([A-Z]{2,}[0-9]{2,}[A-Z0-9-]*)\b",
        r"\b([A-Z][0-9]{2,}[A-Z][A-Z0-9-]{2,})\b",
        r"\b([A-Z0-9]{2,}-[A-Z0-9]{2,}(?:-[A-Z0-9]+)*)\b",
        r"\b([0-9]{3,}[A-Z]{2,}[A-Z0-9-]*)\b",
    ]
    for pattern in sku_patterns:
        m = re.search(pattern, base_text)
        if m:
            candidate = m.group(1)
            if re.search(r"[A-Z]", candidate) and re.search(r"[0-9]", candidate):
                return candidate
    return ""


def extract_actual_size_table_text(soup: BeautifulSoup, option_kind: str = "") -> str:
    """Read actual-size table from page and flatten into one-line text."""
    if soup is None:
        return ""

    size_labels = {
        "FREE",
        "O/S",
        "OS",
        "ONE SIZE",
        "XXS",
        "XS",
        "S",
        "M",
        "L",
        "XL",
        "XXL",
        "XXXL",
        "\ud504\ub9ac",
        "\uc6d0\uc0ac\uc774\uc988",
        "\uc2a4\ubab0",
        "\ubbf8\ub514\uc6c0",
        "\ub77c\uc9c0",
        "\uc5d1\uc2a4\ub77c\uc9c0",
        "\ud22c\uc5d1\uc2a4\ub77c\uc9c0",
    }
    option_kind = (option_kind or "").upper()
    result_rows: List[str] = []

    for table in soup.select("table"):
        rows = table.select("tr")
        if len(rows) < 2:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        if len(header_cells) < 2:
            continue

        headers = [cell.get_text(" ", strip=True) for cell in header_cells]
        if len([header for header in headers[1:] if header]) < 2:
            continue

        table_rows: List[str] = []
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            raw_size = cells[0].get_text(" ", strip=True)
            normalized_size = normalize_size_tokens([raw_size], option_kind)
            size_name = normalized_size[0] if normalized_size else raw_size.strip()
            upper_size_name = size_name.upper()
            if not size_name:
                continue

            if (
                upper_size_name not in size_labels
                and not size_name.isdigit()
                and not normalize_size_tokens([size_name], option_kind)
            ):
                continue

            parts: List[str] = []
            for header, cell in zip(headers[1:], cells[1:]):
                header_text = str(header).strip()
                value_text = cell.get_text(" ", strip=True)
                if not header_text or not value_text or value_text in {"-", "--", "—"}:
                    continue
                parts.append(f"{header_text} {value_text}")

            if len(parts) >= 2:
                table_rows.append(f"{size_name}: {', '.join(parts)}")

        if len(table_rows) >= 1:
            result_rows.extend(table_rows)
            break

    return " | ".join(result_rows)


def extract_size_from_fit_info_block(soup: BeautifulSoup, option_kind: str = "") -> str:
    """Extract size from '내 사이즈 ...' text block."""
    if soup is None:
        return ""

    option_kind = (option_kind or "").upper()
    pattern = re.compile(
        r"\ub0b4\s*\uc0ac\uc774\uc988\s*([A-Za-z][A-Za-z/\s-]*[A-Za-z]|\d{2,3})(?:\s*\[\d+\])?",
        re.IGNORECASE,
    )

    for tag in soup.select("div, span, li, p"):
        text = tag.get_text(" ", strip=True)
        if not text or "\ub0b4 \uc0ac\uc774\uc988" not in text:
            continue

        match = pattern.search(text)
        if not match:
            continue

        raw_size = match.group(1).strip().upper()
        normalized = normalize_size_tokens([raw_size], option_kind)
        if normalized:
            return ", ".join(normalized)
    return ""


def extract_sizes_from_option_ui(soup: BeautifulSoup, option_kind: str = "") -> str:
    """Extract size candidates directly from option UI texts."""
    option_kind = (option_kind or "").upper()
    collected_tokens: List[str] = []
    selectors = [
        '[data-option-name*="size" i]',
        '[data-option-name*="사이즈" i]',
        '[data-name*="size" i]',
        '[data-name*="사이즈" i]',
        '[aria-label*="size" i]',
        '[aria-label*="사이즈" i]',
        '[class*="option" i]',
        '[class*="select" i]',
        '[class*="dropdown" i]',
        '[class*="size" i]',
        '[id*="option" i]',
        '[id*="size" i]',
        '[role="option"]',
        "select option",
        "button",
        "li",
    ]

    seen_texts = set()
    for tag in soup.select(", ".join(selectors)):
        text = tag.get_text(" ", strip=True)
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)

        attrs_text = " ".join(
            str(value)
            for key, value in tag.attrs.items()
            if key in {"class", "id", "aria-label", "data-name", "data-option-name", "name"}
        )
        context = f"{attrs_text} {text}".lower()
        if not any(keyword in context for keyword in ("size", "사이즈", "option", "옵션", "select", "선택")):
            continue

        parts = re.split(r"[\s,/|]+", text)
        for part in parts:
            token = part.strip()
            if token:
                collected_tokens.append(token)

        if len(text) <= 40:
            collected_tokens.append(text.strip())

    normalized_tokens = normalize_size_tokens(collected_tokens, option_kind)
    if not normalized_tokens:
        return ""

    if all(token.isdigit() for token in normalized_tokens):
        numeric = [int(token) for token in normalized_tokens]
        steps = (5,) if option_kind == "SHOES" else (5, 10)
        narrowed = find_longest_step_sequence(sorted(set(numeric)), steps)
        if option_kind == "SHOES" and len(narrowed) >= 2:
            return ", ".join(str(number) for number in narrowed)
        if option_kind != "SHOES" and len(narrowed) >= 2:
            return ", ".join(str(number) for number in narrowed)
        return ""

    unique_tokens: List[str] = []
    for token in normalized_tokens:
        if token not in unique_tokens:
            unique_tokens.append(token)
    return ", ".join(unique_tokens)


def scrape_musinsa_product(
    driver,
    url: str,
    row_num: int,
    existing_sku: str = "",
    existing_product_name_jp: str = "",
    existing_product_name_en: str = "",
    existing_brand_en: str = "",
    download_images: bool = False,
    images_only: bool = False,
    crawl_page_settle_seconds: float = 2.0,
    max_thumbnail_images: int = 20,
    download_images_fn=None,
    fetch_buyma_lowest_price_fn=None,
) -> Product:
    """Scrape one Musinsa product and return Product model."""
    from services.buyma_service import format_price, normalize_price, extract_discounted_product_price

    def _is_unknown_price(value: str) -> bool:
        text = (value or "").strip()
        return text in {"", "\uac00\uaca9 \ubbf8\ud655\uc778", "?? ???", "?????????"}

    try:
        print(f"    페이지 로드 중... {url}")
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(crawl_page_settle_seconds)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        title_text = soup.title.string.strip() if soup.title else ""
        product_json = extract_product_json(soup)
        brand_logo_url = ""
        try:
            from services.image_service import extract_brand_logo_url

            brand_logo_url = extract_brand_logo_url(soup, product_json)
        except Exception:
            brand_logo_url = ""
        mss_state = extract_mss_product_state(soup)
        brand_en_from_state = ""
        try:
            brand_info = mss_state.get("brandInfo") if isinstance(mss_state, dict) else None
            if isinstance(brand_info, dict):
                brand_en_from_state = str(brand_info.get("brandEnglishName", "")).strip()
            if not brand_en_from_state and isinstance(mss_state, dict):
                brand_slug = str(mss_state.get("brand", "")).strip()
                if brand_slug:
                    brand_en_from_state = brand_slug.upper().replace("-", " ")
        except Exception:
            brand_en_from_state = ""

        goods_no = str(mss_state.get("goodsNo", "")).strip()
        raw_product_name = str(mss_state.get("goodsNm") or product_json.get("name", "")).strip()
        product_name = clean_product_name(raw_product_name)
        if product_name == "상품명 미확인" and title_text:
            product_name = clean_product_name(
                re.split(r"\s*-\s*사이즈|\s*\|\s*무신사|\s*-\s*무신사", title_text)[0].strip()
            )

        if images_only:
            image_paths = ""
            if download_images and download_images_fn:
                image_urls = extract_musinsa_thumbnail_urls(
                    soup=soup,
                    product_json=product_json,
                    goods_no=goods_no,
                    max_thumbnail_images=max_thumbnail_images,
                )
                image_folder_name = build_image_folder_name(row_num, 2, product_name)
                image_paths = download_images_fn(image_urls, image_folder_name)
            return Product(
                product_name_kr=product_name,
                musinsa_sku=existing_sku.strip() if existing_sku else "",
                image_paths=image_paths,
                brand_logo_url=brand_logo_url,
            )

        goods_sale_type = str(mss_state.get("goodsSaleType", "SALE")).strip()
        opt_kind_cd = str(mss_state.get("optKindCd", "")).strip()
        goods_options = fetch_goods_options(goods_no, goods_sale_type, opt_kind_cd)

        if product_name == "상품명 미확인":
            selectors_name = [
                "h1",
                '[class*="title"]',
                ".product-detail__sc-190p98n-0",
                '[class*="product_title"]',
                'div[class*="name"]',
                ".product-title",
            ]
            for selector in selectors_name:
                tag = soup.select_one(selector)
                if tag:
                    text = tag.get_text(separator=" ", strip=True)
                    if text and len(text) > 5:
                        product_name = clean_product_name(text)
                        break

        musinsa_sku = extract_musinsa_sku(raw_product_name, product_name, mss_state, product_json, soup)
        if not musinsa_sku and existing_sku:
            print(f"    [품번 fallback] 무신사에서 품번을 못 찾아 시트 내 품번 사용: {existing_sku}")
            musinsa_sku = existing_sku.strip()

        brand = extract_brand_text(product_json, title_text)
        color_from_name = normalize_korean_color(extract_color_from_name(raw_product_name))
        color_from_api = extract_color_from_api(goods_options)
        size_text, color_from_size = extract_sizes_from_api(goods_no, goods_sale_type, opt_kind_cd)
        actual_size_text = extract_actual_size_text(goods_no)
        if not actual_size_text:
            actual_size_text = extract_actual_size_table_text(soup, opt_kind_cd)
        if not actual_size_text:
            actual_size_text = "못찾음"

        if color_from_size:
            color_kr = color_from_size
        elif color_from_api:
            color_kr = color_from_api
        else:
            color_kr = color_from_name
        if not color_kr:
            color_kr = "none"
        if not size_text:
            size_text = extract_size_from_fit_info_block(soup, opt_kind_cd)
        if not size_text:
            size_text = extract_sizes_from_option_ui(soup, opt_kind_cd)
        if not size_text:
            size_text = extract_sizes(soup, opt_kind_cd)

        # 0) structured state price (sale/list price priority; excludes discount amounts)
        state_price_candidates = find_product_price_candidates_from_state(mss_state)
        if state_price_candidates:
            price_text = format_price(state_price_candidates[0])
        else:
            # 1) rendered DOM text price parser
            discounted_price_text = extract_discounted_product_price(soup)
            if not _is_unknown_price(discounted_price_text):
                price_text = discounted_price_text
            else:
                # 2) schema offers
                offers = product_json.get("offers", {}) if isinstance(product_json, dict) else {}
                price_text = format_price(offers.get("price") if isinstance(offers, dict) else None)

        if _is_unknown_price(price_text):
            for selector in [
                '[class*="CurrentPrice"]',
                '[class*="CalculatedPrice"]',
                '[class*="DiscountWrap"]',
                '[class*="PriceTotalWrap"]',
                ".product-detail__sc-1p1ulhg-6",
                '[class*="PriceWrap"]',
                '[class*="price"]',
                '[class*="product_price"]',
                '[class*="sale_price"]',
                '[class*="original_price"]',
            ]:
                for price_tag in soup.select(selector):
                    text = price_tag.get_text(separator=" ", strip=True)
                    if "??" in text and "??" in text:
                        continue
                    normalized = normalize_price(text)
                    if not _is_unknown_price(normalized):
                        price_text = normalized
                        break
                if not _is_unknown_price(price_text):
                    break

        if _is_unknown_price(price_text):
            page_text = soup.get_text()
            matches = re.findall(r"(\d{1,3}(?:,\d{3})*)\s*?", page_text)
            if matches:
                price_text = normalize_price(matches[0])

        image_paths = ""
        if download_images and download_images_fn:
            image_urls = extract_musinsa_thumbnail_urls(
                soup=soup,
                product_json=product_json,
                goods_no=goods_no,
                max_thumbnail_images=max_thumbnail_images,
            )
            image_folder_name = build_image_folder_name(row_num, 2, product_name)
            image_paths = download_images_fn(image_urls, image_folder_name)

        buyma_price_text = ""
        buyma_meta_text = ""
        if fetch_buyma_lowest_price_fn:
            buyma_search_brand = brand_en_from_state or existing_brand_en or brand
            buyma_result = fetch_buyma_lowest_price_fn(
                driver,
                product_name,
                buyma_search_brand,
                musinsa_sku,
                existing_product_name_jp,
                price_text,
                existing_product_name_en,
            )
            if isinstance(buyma_result, dict):
                buyma_price_text = str(buyma_result.get("buyma_price") or "")
                buyma_meta_text = str(buyma_result.get("buyma_meta") or "")
            else:
                buyma_price_text = str(buyma_result or "")

        cat_large, cat_middle, cat_small = extract_musinsa_categories(soup, mss_state)
        gender_large = extract_musinsa_gender_large(mss_state, cat_large, cat_middle, cat_small)
        if gender_large:
            cat_large, cat_middle, cat_small = remap_categories_with_gender(
                gender_large, cat_large, cat_middle, cat_small
            )

        brand_en = brand_en_from_state or extract_brand_en_from_musinsa(driver, url)
        return Product(
            brand=brand,
            brand_en=brand_en,
            product_name_kr=product_name,
            color_kr=color_kr,
            size=size_text,
            actual_size=actual_size_text,
            price=price_text,
            buyma_price=buyma_price_text,
            buyma_meta=buyma_meta_text,
            musinsa_sku=musinsa_sku,
            product_name_jp=existing_product_name_jp,
            product_name_en=existing_product_name_en,
            image_paths=image_paths,
            brand_logo_url=brand_logo_url,
            opt_kind_cd=opt_kind_cd,
            musinsa_category_large=cat_large,
            musinsa_category_middle=cat_middle,
            musinsa_category_small=cat_small,
        )
    except Exception as e:
        print(f"   크롤링 오류 발생: {e}")
        return Product()
