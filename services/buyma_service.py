"""BUYMA parsing, matching, and credential helper functions."""

import os
import re
import time
import urllib.parse
from typing import Dict, List

from app.security.credential_store import KeyringCredentialStore
from bs4 import BeautifulSoup
try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except Exception:  # pragma: no cover - allows tests without selenium runtime.
    By = None  # type: ignore[assignment]
    EC = None  # type: ignore[assignment]
    WebDriverWait = None  # type: ignore[assignment]


class BuymaCredentialService:
    """Persist BUYMA login credentials outside the UI layer."""

    def __init__(self, credentials_path: str) -> None:
        self.credentials_path = credentials_path
        self.store = KeyringCredentialStore(credentials_path)

    def save(self, email: str, password: str) -> None:
        self.store.save(email=email, password=password)

    def load_email(self) -> str:
        return self.store.load_email()

    def exists(self) -> bool:
        return self.store.exists()


def normalize_price(text: str) -> str:
    """Normalize KRW-like price text into digits with comma."""
    if not text:
        return "가격 미확인"
    match = re.search(r"(\d{1,3}(?:,\d{3})*)\s*원", text)
    if match:
        return f"{int(match.group(1).replace(',', '')):,}"
    digits = "".join(filter(str.isdigit, text))
    if digits:
        return f"{int(digits):,}"
    return "가격 미확인"


def format_price(price_value: object) -> str:
    """Format numeric/string price into normalized text."""
    if isinstance(price_value, (int, float)):
        return f"{int(price_value):,}"
    if isinstance(price_value, str):
        return normalize_price(price_value)
    return "가격 미확인"


def extract_discounted_product_price(soup: BeautifulSoup) -> str:
    """Extract Musinsa product price with priority: coupon > discounted > original."""
    if soup is None:
        return "?? ???"

    def _to_prices(text: str) -> List[int]:
        values: List[int] = []
        for raw in re.findall(r"(\d{1,3}(?:,\d{3})*|\d{3,})", text or ""):
            try:
                value = int(str(raw).replace(",", ""))
            except ValueError:
                continue
            if 1000 <= value <= 100000000:
                values.append(value)
        return values

    def _extract_by_patterns(text: str, patterns: List[str]) -> List[int]:
        values: List[int] = []
        for pattern in patterns:
            for raw in re.findall(pattern, text or "", re.IGNORECASE):
                try:
                    value = int(str(raw).replace(",", ""))
                except ValueError:
                    continue
                if 1000 <= value <= 100000000:
                    values.append(value)
        return values

    selectors = [
        '[class*="CurrentPrice"]',
        '[class*="CalculatedPrice"]',
        '[class*="PriceTotalWrap"]',
        '[class*="DiscountWrap"]',
        '[class*="sale_price"]',
        '[class*="price"]',
    ]
    selector_texts: List[str] = []
    for selector in selectors:
        for tag in soup.select(selector):
            text = tag.get_text(" ", strip=True)
            if text:
                selector_texts.append(text)

    page_text = soup.get_text(" ", strip=True)
    all_text = " ".join(selector_texts + [page_text])

    coupon_patterns = [
        r"(?:\ucfe0\ud3f0\s*\uc801\uc6a9\uac00|\ucfe0\ud3f0\uac00|\ucfe0\ud3f0\s*\ud560\uc778\uac00|coupon\s*price)[^0-9]{0,20}(\d{1,3}(?:,\d{3})*|\d{3,})",
        r"(\d{1,3}(?:,\d{3})*|\d{3,})[^0-9]{0,20}(?:\ucfe0\ud3f0\s*\uc801\uc6a9\uac00|\ucfe0\ud3f0\uac00|\ucfe0\ud3f0\s*\ud560\uc778\uac00|coupon\s*price)",
    ]
    coupon_candidates = _extract_by_patterns(all_text, coupon_patterns)
    if coupon_candidates:
        return f"{min(coupon_candidates):,}"

    discount_patterns = [
        r"(?:\ud560\uc778\uac00|\uc138\uc77c\uac00|sale\s*price|discount(?:ed)?\s*price|\ud310\ub9e4\uac00|\ud604\uc7ac\uac00)[^0-9]{0,20}(\d{1,3}(?:,\d{3})*|\d{3,})",
        r"(\d{1,3}(?:,\d{3})*|\d{3,})[^0-9]{0,20}(?:\ud560\uc778|\uc138\uc77c|sale|discount)",
    ]
    discount_candidates = _extract_by_patterns(all_text, discount_patterns)
    if discount_candidates:
        return f"{min(discount_candidates):,}"

    original_patterns = [
        r"(?:\uc815\uac00|\uc6d0\uac00|\uc18c\ube44\uc790\uac00|regular\s*price|original\s*price|list\s*price)[^0-9]{0,20}(\d{1,3}(?:,\d{3})*|\d{3,})",
    ]
    original_candidates = _extract_by_patterns(all_text, original_patterns)
    if original_candidates:
        return f"{min(original_candidates):,}"

    fallback_candidates: List[int] = []
    for text in selector_texts:
        fallback_candidates.extend(_to_prices(text))
    if not fallback_candidates:
        fallback_candidates = _to_prices(page_text)
    if fallback_candidates:
        return f"{min(fallback_candidates):,}"
    return "?? ???"

def extract_yen_values(text: str) -> List[int]:
    """Extract JPY amount candidates from text."""
    if not text:
        return []
    matches = re.findall(r"[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})", text)
    values: List[int] = []
    for raw in matches:
        try:
            value = int(raw.replace(",", ""))
        except ValueError:
            continue
        if 500 <= value <= 10000000:
            values.append(value)
    return values


def extract_buyma_listing_prices(soup: BeautifulSoup) -> List[int]:
    """Extract listing prices from BUYMA search page."""
    prices: List[int] = []

    action_blocks = soup.select('[item-url*="/item/"]')
    for action in action_blocks:
        container = action
        price_tags = []
        for _ in range(5):
            if not container:
                break
            price_tags = container.select("span.Price_Txt")
            if price_tags:
                break
            container = container.parent

        for tag in price_tags:
            prices.extend(extract_yen_values(tag.get_text(" ", strip=True)))

    if prices:
        return prices

    item_links = soup.select('a[href*="/item/"]')
    for link in item_links:
        href = link.get("href", "")
        if not re.search(r"/item/\d+/?", href):
            continue

        container = link
        price_tags = []
        for _ in range(6):
            if not container:
                break
            price_tags = container.select("span.Price_Txt")
            if price_tags:
                break
            container = container.parent

        for tag in price_tags:
            prices.extend(extract_yen_values(tag.get_text(" ", strip=True)))

    return prices


def extract_buyma_listing_entries(soup: BeautifulSoup) -> List[Dict[str, object]]:
    """Extract title/price/url entries from BUYMA search page."""
    entries: List[Dict[str, object]] = []
    seen_urls = set()

    result_count = None
    page_text = soup.get_text(" ", strip=True)
    count_match = re.search(r"該当件数\s*([0-9]+)件", page_text)
    if count_match:
        try:
            result_count = int(count_match.group(1))
        except ValueError:
            result_count = None

    for link in soup.select('a[href*="/item/"]'):
        href = link.get("href", "").strip()
        if not re.search(r"/item/\d+/?", href):
            continue

        full_url = href if href.startswith("http") else f"https://www.buyma.com{href}"
        full_url = full_url.split("?")[0]
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        container = link
        title_text = link.get_text(" ", strip=True)
        price_values: List[int] = []

        for _ in range(6):
            if not container:
                break
            if not title_text:
                title_tag = container.select_one('a[href*="/item/"], h3, [class*="title"], [class*="name"]')
                if title_tag:
                    title_text = title_tag.get_text(" ", strip=True)

            price_tag = container.select_one('span.Price_Txt, [class*="price"], [class*="Price"]')
            if price_tag:
                price_values = extract_yen_values(price_tag.get_text(" ", strip=True))
                price_values = [p for p in price_values if p >= 3000]
                if price_values:
                    break

            context_text = container.get_text(" ", strip=True)
            text_prices = extract_yen_values(context_text)
            text_prices = [p for p in text_prices if p >= 3000]
            if text_prices:
                price_values = text_prices
                break
            container = container.parent

        if not price_values:
            continue

        entries.append({"url": full_url, "title": title_text, "price": min(price_values)})

    if result_count is not None and result_count > 0 and len(entries) > result_count:
        entries = entries[:result_count]
    return entries


def extract_buyma_shipping_included_prices(soup: BeautifulSoup) -> List[int]:
    """Extract 'shipping included' prices from search text."""
    text = soup.get_text(" ", strip=True)
    patterns = [
        r"[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})\s*送料込",
        r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})\s*円\s*送料込",
    ]

    prices: List[int] = []
    for pattern in patterns:
        for raw in re.findall(pattern, text):
            try:
                value = int(raw.replace(",", ""))
            except ValueError:
                continue
            if 3000 <= value <= 10000000:
                prices.append(value)
    return prices


def extract_buyma_item_page_price(soup: BeautifulSoup) -> int:
    """Extract item-page sell price from BUYMA item page."""
    page_text = soup.get_text(" ", strip=True)

    def clean_price_context(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text)
        cleaned = re.sub(
            r"参考価格\s*[¥￥]?\s*[0-9]{1,3}(?:,[0-9]{3})+|参考価格\s*[¥￥]?\s*[0-9]{3,}",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"あなただけの特別価格\s*[¥￥]?\s*[0-9]{1,3}(?:,[0-9]{3})+|あなただけの特別価格\s*[¥￥]?\s*[0-9]{3,}",
            " ",
            cleaned,
        )
        return cleaned

    price_texts: List[str] = []
    selectors = ['[class*="price"]', '[class*="Price"]', ".product_price", ".Price_Txt"]
    for selector in selectors:
        for tag in soup.select(selector):
            text = tag.get_text(" ", strip=True)
            if text:
                price_texts.append(text)

    cleaned_texts = [clean_price_context(text) for text in price_texts]

    sale_candidates: List[int] = []
    for text in cleaned_texts:
        for raw in re.findall(r"タイムセール.*?[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})", text):
            try:
                sale_candidates.append(int(raw.replace(",", "")))
            except ValueError:
                continue
    sale_candidates = [p for p in sale_candidates if p >= 3000]
    if sale_candidates:
        return min(sale_candidates)

    direct_candidates: List[int] = []
    for text in cleaned_texts:
        for raw in re.findall(r"(?:^|\s)価格[^\d¥￥]{0,20}[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})", text):
            try:
                direct_candidates.append(int(raw.replace(",", "")))
            except ValueError:
                continue
    direct_candidates = [p for p in direct_candidates if p >= 3000]
    if direct_candidates:
        return min(direct_candidates)

    price_candidates: List[int] = []
    for text in cleaned_texts:
        price_candidates.extend(extract_yen_values(text))
    price_candidates = [p for p in price_candidates if p >= 3000]
    if price_candidates:
        return min(price_candidates)

    cleaned_page_text = clean_price_context(page_text)
    fallback_candidates = extract_yen_values(cleaned_page_text)
    fallback_candidates = [p for p in fallback_candidates if p >= 3000]
    if fallback_candidates:
        return min(fallback_candidates)
    return 0


def is_relevant_buyma_item(
    soup: BeautifulSoup,
    musinsa_sku: str,
    english_name: str,
    brand: str,
) -> bool:
    """Judge whether BUYMA detail page is relevant to the target item."""
    title_tag = soup.select_one("h1")
    title_text = title_tag.get_text(" ", strip=True) if title_tag else ""
    page_text = soup.get_text(" ", strip=True)
    haystack = f"{title_text} {page_text[:3000]}".lower()
    full_haystack = f"{title_text} {page_text}".lower()

    sku = (musinsa_sku or "").strip().lower()
    if sku:
        if sku in full_haystack:
            return True
        if len(sku) >= 6 and sku[:6] in full_haystack:
            return True

    english = re.sub(r"\s+", " ", (english_name or "").strip()).lower()
    tokens = [
        t
        for t in re.findall(r"[a-z0-9]{4,}", english)
        if t not in {"with", "from", "size", "color", "shoes", "black", "white"}
    ]

    if tokens:
        hits = sum(1 for token in tokens if token in haystack)
        if hits >= 2:
            return True

    brand_text = (brand or "").strip().lower()
    if brand_text and brand_text in haystack and tokens:
        hits = sum(1 for token in tokens[:3] if token in haystack)
        if hits >= 1:
            return True
    return False


def is_relevant_buyma_listing_entry(
    title: str,
    musinsa_sku: str,
    english_name: str,
    brand: str,
) -> bool:
    """Judge whether BUYMA search entry title is relevant."""
    title_lower = re.sub(r"\s+", " ", (title or "").strip()).lower()
    if not title_lower:
        return False

    sku = (musinsa_sku or "").strip().lower()
    if sku:
        if sku in title_lower:
            return True
        if len(sku) >= 6 and sku[:6] in title_lower:
            return True

    english = re.sub(r"\s+", " ", (english_name or "").strip()).lower()
    tokens = [
        t
        for t in re.findall(r"[a-z0-9]{4,}", english)
        if t not in {"with", "from", "size", "color", "shoes", "black", "white"}
    ]
    brand_text = (brand or "").strip().lower()
    if brand_text and brand_text not in title_lower:
        return False

    if tokens:
        hits = sum(1 for token in tokens if token in title_lower)
        if hits >= 2:
            return True
    return False


def normalize_buyma_query(product_name: str, brand: str) -> List[str]:
    """Build prioritized BUYMA query candidates."""
    cleaned_name = re.sub(r"\s+", " ", (product_name or "").strip())
    cleaned_name = re.sub(r"[\[\](){}]", " ", cleaned_name)
    cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()
    cleaned_brand = re.sub(r"\s+", " ", (brand or "").strip())

    sku_match = re.search(r"\b([A-Z]{2,}[0-9]{2,}[A-Z0-9]*|[0-9]{4,})\b", cleaned_name)
    sku_candidates = [sku_match.group(1)] if sku_match else []

    english_parts = re.findall(r"[A-Za-z0-9\s\-/]+", cleaned_name)
    english_name = " ".join(english_parts)
    english_name = re.sub(r"\s+", " ", english_name).strip()

    candidates = [*sku_candidates, f"{cleaned_brand} {english_name}".strip(), english_name, cleaned_brand]

    normalized: List[str] = []
    seen = set()
    for query in candidates:
        query = query[:80].strip()
        if len(query) < 2 or query in seen:
            continue
        seen.add(query)
        normalized.append(query)
    return normalized


def fetch_buyma_lowest_price(driver, product_name: str, brand: str, musinsa_sku: str = "") -> str:
    """Search BUYMA and return lowest matched price."""
    print("\n>>> BUYMA 최저가 검색 시작")
    print(f"    상품명: {product_name}, 브랜드: {brand}, 품번: {musinsa_sku}")

    sku_query = re.sub(r"\s+", " ", (musinsa_sku or "").strip())
    cleaned_name = re.sub(r"\s+", " ", (product_name or "").strip())
    cleaned_brand = re.sub(r"\s+", " ", (brand or "").strip())
    english_parts = re.findall(r"[A-Za-z0-9\s\-/]+", cleaned_name)
    english_name = re.sub(r"\s+", " ", " ".join(english_parts)).strip()
    english_brand_parts = re.findall(r"[A-Za-z0-9\s\-/]+", cleaned_brand)
    english_brand = re.sub(r"\s+", " ", " ".join(english_brand_parts)).strip()

    query_candidates = [
        sku_query,
        f"{english_brand} {english_name}".strip() if english_brand and english_name else "",
        english_name,
    ]
    if not sku_query and not english_name and english_brand:
        query_candidates.append(english_brand)

    queries: List[str] = []
    seen = set()
    for candidate in query_candidates:
        query = re.sub(r"\s+", " ", (candidate or "").strip())
        if re.search(r"[\uac00-\ud7a3]", query):
            continue
        if len(query) < 2 or query in seen:
            continue
        seen.add(query)
        queries.append(query)

    if not queries:
        print("    [검색 질의 없음] 빈 값 반환")
        return ""

    print(f"    검색 시도 순서: {queries}")
    for idx, query in enumerate(queries, start=1):
        try:
            encoded = urllib.parse.quote(query)
            search_url = f"https://www.buyma.com/r/{encoded}/"
            print(f"  [{idx}/{len(queries)}] BUYMA 검색: {query}")
            print(f"    검색 URL: {search_url}")
            driver.get(search_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            entries = extract_buyma_listing_entries(soup)
            print(f"    발견된 상품카드(첫 페이지): {len(entries)}개")

            detail_prices: List[int] = []
            listing_matched_prices: List[int] = []
            candidate_entries = entries[:10]
            print(f"    상세페이지 확인 대상: {len(candidate_entries)}개")

            for entry in candidate_entries:
                if is_relevant_buyma_listing_entry(
                    str(entry.get("title", "")),
                    sku_query,
                    english_name,
                    english_brand,
                ):
                    listing_matched_prices.append(int(entry["price"]))

            for entry in candidate_entries:
                item_url = str(entry.get("url", "")).strip()
                if not item_url:
                    continue
                try:
                    driver.get(item_url)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    time.sleep(1.2)

                    item_soup = BeautifulSoup(driver.page_source, "html.parser")
                    if not is_relevant_buyma_item(item_soup, sku_query, english_name, english_brand):
                        continue

                    detail_price = extract_buyma_item_page_price(item_soup)
                    if detail_price > 0:
                        detail_prices.append(detail_price)
                except Exception as detail_error:
                    print(f"    상세페이지 스킵: {detail_error}")

            combined_prices = list(detail_prices)
            if not combined_prices:
                combined_prices.extend(listing_matched_prices)
            if not combined_prices:
                # Last-resort fallback: use visible listing card prices to avoid empty sell-price cell.
                card_prices = [int(entry["price"]) for entry in candidate_entries if int(entry.get("price", 0)) >= 3000]
                if card_prices:
                    combined_prices.extend(card_prices)
                    print(f"    [fallback] 관련도 미매칭으로 카드 최저가 사용: {min(card_prices):,}엔")

            if combined_prices:
                unique_prices = sorted(set(combined_prices))
                best_price = min(unique_prices)
                detail_min = min(detail_prices) if detail_prices else None
                listing_min = min(listing_matched_prices) if listing_matched_prices else None
                print(
                    f"    셀러가격 통합 통계: {len(unique_prices)}개, "
                    f"최저: {best_price:,}엔, 최고: {max(unique_prices):,}엔, "
                    f"상세최저: {detail_min if detail_min else 'none'}, 카드최저: {listing_min if listing_min else 'none'}"
                )
                return f"{best_price:,}"

            print("    해당 질의에서는 가격을 찾지 못함")
        except Exception as e:
            print(f"    검색 오류: {e}")

    print("  모든 검색 질의 실패 - 빈 값 반환")
    return ""
