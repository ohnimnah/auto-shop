"""BUYMA parsing, matching, and credential helper functions."""

import json
import os
import re
import statistics
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


BUYMA_NO_RESULTS_TEXT = "お探しの条件にあてはまる商品は見つかりませんでした。"


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


def extract_buyma_listing_entries(soup: BeautifulSoup) -> List[Dict[str, object]]:
    """Extract title/price/url entries from BUYMA search page."""
    entries: List[Dict[str, object]] = []
    seen_urls = set()

    def _item_urls_in(container) -> set:
        urls = set()
        if not container:
            return urls
        for item_link in container.select('a[href*="/item/"]'):
            item_href = item_link.get("href", "").strip()
            if re.search(r"/item/\d+/?", item_href):
                urls.add(item_href.split("?")[0])
        return urls

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
            container_item_urls = _item_urls_in(container)
            if len(container_item_urls) > 1:
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


def count_buyma_item_links(soup: BeautifulSoup) -> int:
    """Return the number of unique BUYMA item links found on a search page."""
    urls = set()
    for link in soup.select('a[href*="/item/"]'):
        href = link.get("href", "").strip()
        if re.search(r"/item/\d+/?", href):
            urls.add(href.split("?")[0])
    return len(urls)


def is_buyma_no_results_page(soup: BeautifulSoup) -> bool:
    """Return True when BUYMA explicitly says the search has no matching items."""
    page_text = soup.get_text(" ", strip=True)
    return BUYMA_NO_RESULTS_TEXT in page_text


def _wait_for_buyma_search_ready(driver, timeout_seconds: float = 2.0) -> None:
    """Wait briefly until BUYMA search content is parseable."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        if is_buyma_no_results_page(soup) or count_buyma_item_links(soup) > 0:
            return
        time.sleep(0.2)


def _wait_for_buyma_detail_ready(driver, timeout_seconds: float = 0.8) -> None:
    """Wait briefly until a BUYMA item detail page has title or price text."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        if soup.select_one("h1") or extract_buyma_item_page_price(soup) > 0:
            return
        time.sleep(0.2)


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


def normalize_sku(value: str) -> str:
    """Normalize SKU/model number for cross-marketplace comparison."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _parse_price_number(value: object) -> int:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    if not digits:
        return 0
    try:
        return int(digits)
    except ValueError:
        return 0


def _clean_sheet_text(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if text.startswith("#"):
        return ""
    return text


def _clean_english_query(value: str) -> str:
    parts = re.findall(r"[A-Za-z0-9\s\-/]+", value or "")
    value = re.sub(r"\s+", " ", " ".join(parts)).strip(" -/")
    tokens = re.findall(r"[A-Za-z0-9]+", value)
    meaningful = [token for token in tokens if len(token) >= 2]
    if len(meaningful) < 2:
        return ""
    return value


def _search_brand_text(brand: str) -> str:
    parts = re.findall(r"[A-Za-z0-9\s\-/]+", brand or "")
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _english_tokens(value: str) -> List[str]:
    stop_words = {"with", "from", "size", "color", "shoes", "black", "white"}
    return [token for token in re.findall(r"[a-z0-9]{4,}", (value or "").lower()) if token not in stop_words]


def _japanese_tokens(value: str) -> List[str]:
    tokens = re.findall(r"[\u3040-\u30ff\u3400-\u9fff]{2,}", value or "")
    if tokens:
        return tokens
    compact = re.sub(r"\s+", "", value or "")
    return [compact] if len(compact) >= 2 else []


def _score_buyma_text(
    text: str,
    *,
    musinsa_sku: str,
    english_name: str,
    brand: str,
    japanese_name: str,
) -> Dict[str, object]:
    haystack = re.sub(r"\s+", " ", (text or "").strip()).lower()
    compact_haystack = re.sub(r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff]", "", haystack)
    sku = normalize_sku(musinsa_sku)
    brand_text = (brand or "").strip().lower()
    brand_compact = re.sub(r"[^a-z0-9]", "", brand_text)
    score = 0
    matched_by: List[str] = []
    language_match: List[str] = []

    sku_prefix6 = False
    if sku:
        if sku and sku in compact_haystack:
            score += 50
            matched_by.append("sku_full")
        elif len(sku) >= 8 and any(sku[:size] in compact_haystack for size in range(min(10, len(sku)), 7, -1)):
            score += 30
            matched_by.append("sku_partial_8_10")
        elif len(sku) >= 6 and sku[:6] in compact_haystack:
            sku_prefix6 = True

    brand_match = False
    if brand_text:
        brand_match = brand_text in haystack or (bool(brand_compact) and brand_compact in compact_haystack)
        if brand_match:
            score += 20
            matched_by.append("brand")
        elif brand_compact:
            score -= 10
            matched_by.append("brand_mismatch")

    en_tokens = _english_tokens(english_name)
    en_hits = sum(1 for token in en_tokens if token in haystack)
    if en_hits >= 2:
        score += 20
        matched_by.append("en_tokens")
        language_match.append("en")

    jp_tokens = _japanese_tokens(japanese_name)
    jp_hits = sum(1 for token in jp_tokens if token and token in compact_haystack)
    if jp_hits >= 1:
        score += 10
        matched_by.append("jp_tokens")
        language_match.append("jp")
        if any(len(token) >= 4 for token in jp_tokens if token in compact_haystack):
            score += 10
            matched_by.append("jp_keyword")

    if sku_prefix6 and (brand_match or en_hits >= 2 or jp_hits >= 1):
        score += 15
        matched_by.append("sku_prefix6_with_context")

    return {
        "score": max(0, score),
        "matched_by": matched_by,
        "language_match": language_match,
    }


def build_buyma_price_search_queries(
    product_name: str,
    brand: str,
    musinsa_sku: str = "",
    product_name_jp: str = "",
    product_name_en: str = "",
) -> List[str]:
    """Build BUYMA price search queries in priority order."""
    sku_query = _clean_sheet_text(musinsa_sku)
    cleaned_name = _clean_sheet_text(product_name_en) or _clean_sheet_text(product_name)
    cleaned_brand = _clean_sheet_text(brand)
    english_name = _clean_english_query(cleaned_name)
    english_brand = _search_brand_text(cleaned_brand)
    japanese_name = _clean_sheet_text(product_name_jp)

    query_candidates = [
        sku_query,
        f"{english_brand} {sku_query}".strip() if english_brand and sku_query else "",
        f"{english_brand} {english_name}".strip() if english_brand and english_name else "",
        f"{english_brand} {japanese_name}".strip() if english_brand and japanese_name else "",
        english_name,
        japanese_name,
    ]

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
    return queries


def _filter_valid_buyma_candidates(candidates: List[Dict[str, object]], musinsa_price: int = 0) -> List[Dict[str, object]]:
    reliable = [candidate for candidate in candidates if int(candidate.get("score") or 0) >= 80 and int(candidate.get("price") or 0) > 0]
    if musinsa_price > 0:
        reliable = [candidate for candidate in reliable if int(candidate.get("price") or 0) >= int(musinsa_price * 1.1)]
    prices = [int(candidate["price"]) for candidate in reliable]
    if len(prices) >= 3:
        median_price = statistics.median(prices)
        reliable = [candidate for candidate in reliable if int(candidate["price"]) >= int(median_price * 0.6)]
    return reliable


def _detail_check_limit_for_query(query: str, *, musinsa_sku: str, brand: str) -> int:
    normalized_query = normalize_sku(query)
    sku = normalize_sku(musinsa_sku)
    if sku and normalized_query == sku:
        return 3
    if sku and sku in normalized_query and _search_brand_text(brand):
        return 5
    return 5


def _can_use_listing_without_detail(candidate: Dict[str, object], *, musinsa_sku: str) -> bool:
    if not normalize_sku(musinsa_sku):
        return False
    if int(candidate.get("score") or 0) < 90:
        return False
    matched_by = set(candidate.get("matched_by") or [])
    return "sku_full" in matched_by and bool({"brand", "en_tokens", "jp_tokens", "jp_keyword"} & matched_by)


def _should_check_detail_candidate(score_result: Dict[str, object]) -> bool:
    score = int(score_result.get("score") or 0)
    matched_by = set(score_result.get("matched_by") or [])
    return score >= 60 or bool({"sku_full", "sku_partial_8_10"} & matched_by)


def fetch_buyma_lowest_price_with_meta(
    driver,
    product_name: str,
    brand: str,
    musinsa_sku: str = "",
    product_name_jp: str = "",
    musinsa_price: object = "",
    product_name_en: str = "",
) -> Dict[str, str]:
    """Search BUYMA and return selected price plus JSON metadata."""
    print("\n>>> BUYMA 최저가 검색 시작")
    print(f"    상품명: {product_name}, 브랜드: {brand}, 품번: {musinsa_sku}")

    sku_query = _clean_sheet_text(musinsa_sku)
    cleaned_name = _clean_sheet_text(product_name_en) or _clean_sheet_text(product_name)
    cleaned_brand = _clean_sheet_text(brand)
    english_name = _clean_english_query(cleaned_name)
    english_brand = _search_brand_text(cleaned_brand)
    japanese_name = _clean_sheet_text(product_name_jp)
    queries = build_buyma_price_search_queries(product_name, brand, musinsa_sku, japanese_name, product_name_en)
    musinsa_price_value = _parse_price_number(musinsa_price)

    if not queries:
        print("    [검색 질의 없음] 빈 값 반환")
        return {"buyma_price": "", "buyma_meta": ""}

    print(f"    검색 시도 순서: {queries}")
    all_candidates: List[Dict[str, object]] = []
    checked_count = 0
    no_result_queries: List[str] = []
    for idx, query in enumerate(queries, start=1):
        try:
            encoded = urllib.parse.quote(query, safe="")
            search_url = f"https://www.buyma.com/r/{encoded}/"
            print(f"  [{idx}/{len(queries)}] BUYMA 검색: {query}")
            print(f"    검색 URL: {search_url}")
            driver.get(search_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            _wait_for_buyma_search_ready(driver)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            if is_buyma_no_results_page(soup):
                no_result_queries.append(query)
                print("    BUYMA 검색 결과 없음 문구 확인 - 다음 검색어로 이동")
                continue

            entries = extract_buyma_listing_entries(soup)
            unique_item_links = count_buyma_item_links(soup)
            print(f"    BUYMA item 링크(첫 페이지): {unique_item_links}개, 가격 후보: {len(entries)}개")

            candidate_entries = entries[:10]
            checked_count += len(candidate_entries)
            detail_check_limit = _detail_check_limit_for_query(query, musinsa_sku=sku_query, brand=english_brand)
            detail_checked = 0
            print(f"    상세페이지 확인 대상: 최대 {detail_check_limit}개")

            for entry in candidate_entries:
                title = str(entry.get("title", ""))
                item_url = str(entry.get("url", "")).strip()
                listing_score = _score_buyma_text(
                    title,
                    musinsa_sku=sku_query,
                    english_name=english_name,
                    brand=english_brand,
                    japanese_name=japanese_name,
                )
                if int(listing_score["score"]) >= 60:
                    listing_candidate = {
                        "url": item_url,
                        "title": title,
                        "price": int(entry["price"]),
                        "score": int(listing_score["score"]),
                        "matched_by": listing_score["matched_by"],
                        "language_match": listing_score["language_match"],
                        "source": "listing",
                        "search_query": query,
                    }
                    all_candidates.append(listing_candidate)
                    if _can_use_listing_without_detail(listing_candidate, musinsa_sku=sku_query):
                        print("    고신뢰 카드 가격 후보 확인 - 상세페이지 생략 가능")

                listing_score_value = int(listing_score["score"])
                if (
                    not item_url
                    or not _should_check_detail_candidate(listing_score)
                    or detail_checked >= detail_check_limit
                    or _can_use_listing_without_detail(
                        {
                            "score": listing_score_value,
                            "matched_by": listing_score["matched_by"],
                        },
                        musinsa_sku=sku_query,
                    )
                ):
                    continue
                try:
                    detail_checked += 1
                    driver.get(item_url)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    _wait_for_buyma_detail_ready(driver)

                    item_soup = BeautifulSoup(driver.page_source, "html.parser")
                    title_tag = item_soup.select_one("h1")
                    detail_title = title_tag.get_text(" ", strip=True) if title_tag else title
                    detail_text = item_soup.get_text(" ", strip=True)
                    detail_score = _score_buyma_text(
                        f"{detail_title} {detail_text[:3000]}",
                        musinsa_sku=sku_query,
                        english_name=english_name,
                        brand=english_brand,
                        japanese_name=japanese_name,
                    )
                    detail_price = extract_buyma_item_page_price(item_soup)
                    if int(detail_score["score"]) >= 60 and detail_price > 0:
                        all_candidates.append(
                            {
                                "url": item_url,
                                "title": detail_title,
                                "price": detail_price,
                                "score": int(detail_score["score"]),
                                "matched_by": detail_score["matched_by"],
                                "language_match": detail_score["language_match"],
                                "source": "detail",
                                "search_query": query,
                            }
                        )
                except Exception as detail_error:
                    print(f"    상세페이지 스킵: {detail_error}")

            valid_so_far = _filter_valid_buyma_candidates(all_candidates, musinsa_price_value)
            if any(candidate.get("source") == "detail" for candidate in valid_so_far):
                print("    신뢰 가능한 상세 가격 후보 확인 - 추가 검색 생략")
                break
            if any(_can_use_listing_without_detail(candidate, musinsa_sku=sku_query) for candidate in valid_so_far):
                print("    신뢰 가능한 카드 가격 후보 확인 - 추가 검색 생략")
                break

        except Exception as e:
            print(f"    검색 오류: {e}")

    valid_candidates = _filter_valid_buyma_candidates(all_candidates, musinsa_price_value)
    detail_candidates = [candidate for candidate in valid_candidates if candidate.get("source") == "detail"]
    selected_pool = detail_candidates or valid_candidates
    if not selected_pool:
        meta = {
            "score": 0,
            "matched_by": "",
            "source": "",
            "search_query": queries[0] if queries else "",
            "language_match": [],
            "checked_count": checked_count,
            "candidate_count": len(all_candidates),
            "selected_reason": "buyma_no_results" if no_result_queries and not all_candidates else "no_reliable_candidate",
            "no_result_queries": no_result_queries,
            "url": "",
        }
        print("  신뢰 가능한 BUYMA 가격 후보 없음 - 빈 값 반환")
        return {"buyma_price": "", "buyma_meta": json.dumps(meta, ensure_ascii=False, separators=(",", ":"))}

    selected = min(selected_pool, key=lambda item: int(item["price"]))
    meta = {
        "score": int(selected.get("score") or 0),
        "matched_by": ",".join(str(v) for v in selected.get("matched_by", []) if v),
        "source": str(selected.get("source") or ""),
        "search_query": str(selected.get("search_query") or ""),
        "language_match": selected.get("language_match") or [],
        "checked_count": checked_count,
        "candidate_count": len(valid_candidates),
        "selected_reason": "lowest_valid_price",
        "url": str(selected.get("url") or ""),
    }
    price = int(selected["price"])
    print(f"    BUYMA 선택 가격: {price:,}엔 (score={meta['score']}, source={meta['source']})")
    return {"buyma_price": f"{price:,}", "buyma_meta": json.dumps(meta, ensure_ascii=False, separators=(",", ":"))}


def fetch_buyma_lowest_price(
    driver,
    product_name: str,
    brand: str,
    musinsa_sku: str = "",
    product_name_jp: str = "",
    musinsa_price: object = "",
    product_name_en: str = "",
) -> str:
    """Search BUYMA and return selected price only for legacy callers."""
    return fetch_buyma_lowest_price_with_meta(
        driver,
        product_name,
        brand,
        musinsa_sku,
        product_name_jp,
        musinsa_price,
        product_name_en,
    ).get("buyma_price", "")
