"""Listing-page queue collection helpers (safe additive feature).

Queue sheet fixed columns:
페이지URL | 상품ID | 상품URL | 수집일시 | 수집상태 | 상세크롤링상태 | 비고
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException

QUEUE_HEADERS = [
    "페이지URL",
    "상품ID",
    "상품URL",
    "수집일시",
    "수집상태",
    "상세크롤링상태",
    "비고",
]

NOTE_DUPLICATE = "중복"
NOTE_NO_PRODUCT = "상품없음"
NOTE_CRAWL_FAILED = "크롤링실패"
NOTE_TIMEOUT = "타임아웃"
NOTE_STRUCTURE_CHANGED = "구조변경"
NOTE_DATA_MISSING = "데이터누락"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


SEED_READY_STATUSES = {"", "대기", "pending", "new"}


def _col_letter(index: int) -> str:
    if index < 0:
        raise ValueError("index must be >= 0")
    result = ""
    current = index + 1
    while current:
        current, rem = divmod(current - 1, 26)
        result = chr(65 + rem) + result
    return result


def extract_spreadsheet_id_from_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    if m:
        return m.group(1)
    m = re.search(r"(?:^|/)d/([a-zA-Z0-9-_]+)", value)
    if m:
        return m.group(1)
    return ""


def extract_gid_from_url(raw: str) -> int | None:
    value = (raw or "").strip()
    if not value:
        return None
    m = re.search(r"[#?&]gid=(\d+)", value)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def resolve_listing_queue_target(
    service,
    default_spreadsheet_id: str,
    queue_sheet_name: str,
    queue_sheet_url: str,
    get_sheet_name_by_gid_fn,
) -> Tuple[str, str]:
    """Resolve queue target by URL first, then fallback to sheet name."""
    target_spreadsheet_id = default_spreadsheet_id
    target_sheet_name = queue_sheet_name

    url = (queue_sheet_url or "").strip()
    if not url:
        return target_spreadsheet_id, target_sheet_name

    sid = extract_spreadsheet_id_from_url(url)
    if sid:
        target_spreadsheet_id = sid

    gid = extract_gid_from_url(url)
    if gid is not None:
        resolved = get_sheet_name_by_gid_fn(service, target_spreadsheet_id, gid)
        if resolved:
            target_sheet_name = resolved
            print(f"[queue] URL 기반 탭 해석: gid={gid} -> '{target_sheet_name}'")
        else:
            print(f"[queue] URL gid={gid} 탭명 해석 실패. --queue-sheet-name '{target_sheet_name}' 사용")
    else:
        print(f"[queue] queue-sheet-url에 gid가 없어 --queue-sheet-name '{target_sheet_name}' 사용")

    return target_spreadsheet_id, target_sheet_name


def _is_http_url(value: str) -> bool:
    text = (value or "").strip()
    return text.startswith("http://") or text.startswith("https://")


def _extract_musinsa_product_id_and_url(href: str) -> Tuple[str, str]:
    text = (href or "").strip()
    if not text:
        return "", ""
    match = re.search(r"/products/(\d+)", text)
    if not match:
        match = re.search(r"/app/goods/(\d+)", text)
    if not match:
        match = re.search(r"[?&]goodsNo=(\d+)", text)
    if not match:
        return "", ""
    product_id = match.group(1)
    product_url = f"https://www.musinsa.com/products/{product_id}"
    return product_id, product_url


def _normalize_page_url(url: str) -> str:
    p = urlparse((url or "").strip())
    if not p.scheme or not p.netloc:
        return (url or "").strip()
    # fragment 제거, query 정렬
    query_items = parse_qs(p.query, keep_blank_values=True)
    query = urlencode(sorted((k, v) for k, vals in query_items.items() for v in vals))
    return urlunparse((p.scheme, p.netloc, p.path, p.params, query, ""))


def _discover_pagination_urls(page_url: str, soup: BeautifulSoup) -> List[str]:
    base = urlparse(page_url)
    page_urls: List[str] = []
    seen = set()
    for a_tag in soup.select("a[href]"):
        href = (a_tag.get("href") or "").strip()
        if not href:
            continue
        anchor_text = (a_tag.get_text(" ", strip=True) or "").strip().lower()
        full_url = _normalize_page_url(urljoin(page_url, href))
        parsed = urlparse(full_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc != base.netloc:
            continue
        if parsed.path != base.path:
            continue
        q = parse_qs(parsed.query)
        has_page_like = any(k in q for k in ("page", "p", "pg", "pageNo", "pageNum", "start", "offset"))
        numeric_anchor = anchor_text.isdigit() or anchor_text in {"다음", "next", ">", "›", "»"}
        if not has_page_like and not numeric_anchor:
            continue
        if full_url in seen:
            continue
        seen.add(full_url)
        page_urls.append(full_url)
    # page 번호 오름차순 정렬
    def _page_num(url: str) -> int:
        try:
            return int((parse_qs(urlparse(url).query).get("page") or ["1"])[0])
        except Exception:
            return 1
    page_urls.sort(key=_page_num)
    return page_urls


def _build_forced_page_url(base_url: str, page_num: int) -> str:
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["page"] = [str(page_num)]
    query = urlencode(sorted((k, v) for k, vals in qs.items() for v in vals))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, ""))


def _build_forced_page_url_by_key(base_url: str, key: str, page_num: int) -> str:
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs[key] = [str(page_num)]
    query = urlencode(sorted((k, v) for k, vals in qs.items() for v in vals))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, ""))


def _extract_page_num_from_url(url: str) -> int | None:
    try:
        qs = parse_qs(urlparse(url).query)
    except Exception:
        return None
    for key in ("page", "pageNo", "pageNum", "p", "pg"):
        values = qs.get(key) or []
        if not values:
            continue
        try:
            num = int(str(values[0]).strip())
            if num >= 1:
                return num
        except Exception:
            continue
    return None


def _collect_products_from_single_page(
    driver,
    target_url: str,
) -> Tuple[List[Tuple[str, str]], int, int, int]:
    """Return (products, href_candidate_count, malformed_count, expected_total)."""

    def _capture_product_hrefs() -> List[str]:
        return list(
            driver.execute_script(
                """
                const out = [];
                const origin = window.location.origin || '';
                const links = Array.from(document.querySelectorAll('a[href]'));
                for (const a of links) {
                    const raw = (a.getAttribute('href') || '').trim();
                    if (!raw) continue;
                    if (!(raw.includes('/products/') || raw.includes('/app/goods/') || raw.includes('goodsNo='))) continue;
                    let full = raw;
                    if (raw.startsWith('//')) full = window.location.protocol + raw;
                    else if (raw.startsWith('/')) full = origin + raw;
                    out.push(full);
                }
                return Array.from(new Set(out));
                """
            )
        )

    driver.get(target_url)
    time.sleep(1.2)
    collected_hrefs = set(_capture_product_hrefs())

    def _detect_total_expected() -> int:
        text = str(driver.execute_script("return document.body ? document.body.innerText : ''") or "")
        m = re.search(r"?\s*([0-9,]+)\s*?", text)
        if not m:
            m = re.search(r"([0-9,]+)\s*?", text)
        if not m:
            return 0
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            return 0

    expected_total = _detect_total_expected()

    def _count_product_link_candidates() -> int:
        return int(
            driver.execute_script(
                """
                const links = Array.from(document.querySelectorAll('a[href]'));
                const seen = new Set();
                for (const a of links) {
                    const href = (a.getAttribute('href') || '');
                    if (!href) continue;
                    if (href.includes('/products/') || href.includes('/app/goods/') || href.includes('goodsNo=')) {
                        seen.add(href);
                    }
                }
                return seen.size;
                """
            )
        )

    prev_count = -1
    stable_rounds = 0
    for _ in range(40):
        for href in _capture_product_hrefs():
            collected_hrefs.add(href)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        driver.execute_script("window.dispatchEvent(new Event('scroll'));")
        time.sleep(0.65)

        driver.execute_script("window.scrollBy(0, -320);")
        driver.execute_script("window.scrollBy(0, 460);")
        time.sleep(0.35)

        current_count = _count_product_link_candidates()
        if current_count > prev_count:
            prev_count = current_count
            stable_rounds = 0
        else:
            stable_rounds += 1

        if expected_total > 0 and len(collected_hrefs) >= expected_total:
            break
        if stable_rounds >= 6:
            break

    for _ in range(8):
        for href in _capture_product_hrefs():
            collected_hrefs.add(href)
        clicked = driver.execute_script(
            """
            const candidates = Array.from(document.querySelectorAll('button, a[role="button"], a'));
            for (const el of candidates) {
                const txt = (el.textContent || '').trim().toLowerCase();
                if (!txt) continue;
                if (txt.includes('???') || txt.includes('more')) {
                    el.click();
                    return true;
                }
            }
            return false;
            """
        )
        if not clicked:
            break
        time.sleep(0.6)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.35)

    prev_count = -1
    stable_rounds = 0
    for _ in range(24):
        for href in _capture_product_hrefs():
            collected_hrefs.add(href)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        driver.execute_script("window.dispatchEvent(new Event('scroll'));")
        time.sleep(0.6)
        current_count = _count_product_link_candidates()
        if current_count > prev_count:
            prev_count = current_count
            stable_rounds = 0
        else:
            stable_rounds += 1
        if expected_total > 0 and len(collected_hrefs) >= expected_total:
            break
        if stable_rounds >= 5:
            break

    for href in _capture_product_hrefs():
        collected_hrefs.add(href)

    if expected_total > 0 and len(collected_hrefs) < expected_total:
        prev_size = len(collected_hrefs)
        stable_rounds = 0
        for _ in range(16):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            driver.execute_script("window.dispatchEvent(new Event('scroll'));")
            time.sleep(0.9)
            for href in _capture_product_hrefs():
                collected_hrefs.add(href)
            cur_size = len(collected_hrefs)
            if cur_size <= prev_size:
                stable_rounds += 1
            else:
                stable_rounds = 0
            prev_size = cur_size
            if len(collected_hrefs) >= expected_total:
                break
            if stable_rounds >= 4:
                break

    products: List[Tuple[str, str]] = []
    seen = set()
    malformed_count = 0
    href_candidate_count = len(collected_hrefs)

    for href in sorted(collected_hrefs):
        full_href = urljoin(target_url, href)
        product_id, product_url = _extract_musinsa_product_id_and_url(full_href)
        if not product_id or not product_url:
            malformed_count += 1
            continue
        if product_id in seen:
            continue
        seen.add(product_id)
        products.append((product_id, product_url))

    print(
        f"[queue] page collect snapshot: expected={expected_total or '-'} "
        f"captured_hrefs={len(collected_hrefs)} unique_products={len(products)}"
    )
    return products, href_candidate_count, malformed_count, expected_total

def _collect_products_from_listing_page(
    driver,
    page_url: str,
    max_pages: int = 30,
) -> Tuple[List[Tuple[str, str]], int, int, Dict[str, int | bool]]:
    """Collect products from first listing page + pagination pages."""

    first_products, first_href_cnt, first_malformed, first_expected_total = _collect_products_from_single_page(driver, page_url)
    first_soup = BeautifulSoup(driver.page_source, "html.parser")
    page_urls = _discover_pagination_urls(page_url, first_soup)

    all_products: List[Tuple[str, str]] = []
    seen_ids = set()
    total_href_candidates = first_href_cnt
    total_malformed = first_malformed

    for pid, purl in first_products:
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        all_products.append((pid, purl))

    expected_total = int(first_expected_total or 0)
    if expected_total <= 0:
        try:
            body_text = str(driver.execute_script("return document.body ? document.body.innerText : ''") or "")
            m = re.search(r"?\s*([0-9,]+)\s*?", body_text)
            if not m:
                m = re.search(r"([0-9,]+)\s*?", body_text)
            if m:
                expected_total = int(m.group(1).replace(",", ""))
        except Exception:
            expected_total = 0

    plateau_detected = False
    plateau_rounds = 0
    last_snapshot = (expected_total, first_href_cnt, len(first_products))

    def _check_plateau(expected_local: int, href_cnt: int, products: List[Tuple[str, str]], new_count: int, source: str) -> bool:
        nonlocal plateau_detected, plateau_rounds, last_snapshot
        snapshot = (expected_local or expected_total, href_cnt, len(products))
        if (
            new_count == 0
            and snapshot == last_snapshot
            and snapshot[0] > 0
            and snapshot[2] < snapshot[0]
        ):
            plateau_rounds += 1
        else:
            plateau_rounds = 0
        last_snapshot = snapshot
        if plateau_rounds >= 2:
            plateau_detected = True
            print(
                f"[queue] plateau detected at {source}: expected={snapshot[0]} "
                f"captured_hrefs={snapshot[1]} unique_products={snapshot[2]}"
            )
            return True
        return False

    traversed = 1
    tried_page_numbers = set([1])
    for next_url in page_urls:
        if traversed >= max_pages:
            break
        detected_page_num = _extract_page_num_from_url(next_url)
        if detected_page_num is not None and detected_page_num in tried_page_numbers:
            continue
        products, href_cnt, malformed_cnt, local_expected = _collect_products_from_single_page(driver, next_url)
        traversed += 1
        if detected_page_num is not None:
            tried_page_numbers.add(detected_page_num)
        total_href_candidates += href_cnt
        total_malformed += malformed_cnt

        new_count = 0
        for pid, purl in products:
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            all_products.append((pid, purl))
            new_count += 1

        if _check_plateau(local_expected, href_cnt, products, new_count, f"pagination:{next_url}"):
            break
        if expected_total > 0 and len(seen_ids) >= expected_total:
            break

    consecutive_empty = 0
    for page_num in range(2, max_pages + 1):
        if page_num in tried_page_numbers:
            continue
        forced_url = _build_forced_page_url(page_url, page_num)
        products, href_cnt, malformed_cnt, local_expected = _collect_products_from_single_page(driver, forced_url)
        total_href_candidates += href_cnt
        total_malformed += malformed_cnt

        new_count = 0
        for pid, purl in products:
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            all_products.append((pid, purl))
            new_count += 1

        if _check_plateau(local_expected, href_cnt, products, new_count, f"forced-page:{page_num}"):
            break

        if new_count == 0:
            consecutive_empty += 1
        else:
            consecutive_empty = 0

        if consecutive_empty >= 2:
            break
        if expected_total > 0 and len(seen_ids) >= expected_total:
            break

    if expected_total > 0 and len(seen_ids) < expected_total and not plateau_detected:
        page_keys = ("page", "pageNo", "pageNum", "p", "pg")
        max_needed_page = min(max_pages, max(2, (expected_total + 9) // 10 + 2))
        for key in page_keys:
            before_key_count = len(seen_ids)
            for page_num in range(2, max_needed_page + 1):
                forced_url = _build_forced_page_url_by_key(page_url, key, page_num)
                products, href_cnt, malformed_cnt, local_expected = _collect_products_from_single_page(driver, forced_url)
                total_href_candidates += href_cnt
                total_malformed += malformed_cnt

                new_count = 0
                for pid, purl in products:
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    all_products.append((pid, purl))
                    new_count += 1

                if _check_plateau(local_expected, href_cnt, products, new_count, f"forced-key:{key}:{page_num}"):
                    break
                if expected_total > 0 and len(seen_ids) >= expected_total:
                    break

            if expected_total > 0 and len(seen_ids) >= expected_total:
                break
            if len(seen_ids) == before_key_count:
                continue

    def _try_click_next_page() -> bool:
        try:
            return bool(
                driver.execute_script(
                    """
                    function isVisible(el) {
                      if (!el) return false;
                      const s = window.getComputedStyle(el);
                      if (!s || s.display === 'none' || s.visibility === 'hidden') return false;
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    }
                    function isDisabled(el) {
                      const a = (el.getAttribute('aria-disabled') || '').toLowerCase();
                      if (a === 'true') return true;
                      if (el.disabled) return true;
                      const c = (el.className || '').toString().toLowerCase();
                      return c.includes('disabled');
                    }
                    const nodes = Array.from(document.querySelectorAll('a,button,[role="button"]'));
                    const scored = [];
                    for (const el of nodes) {
                      if (!isVisible(el) || isDisabled(el)) continue;
                      const txt = (el.textContent || '').trim().toLowerCase();
                      const cls = (el.className || '').toString().toLowerCase();
                      const rel = (el.getAttribute('rel') || '').toLowerCase();
                      const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                      const title = (el.getAttribute('title') || '').toLowerCase();
                      const href = (el.getAttribute('href') || '').toLowerCase();
                      let score = 0;
                      if (txt.includes('??') || txt.includes('next')) score += 8;
                      if (aria.includes('??') || aria.includes('next')) score += 8;
                      if (title.includes('??') || title.includes('next')) score += 6;
                      if (rel === 'next') score += 10;
                      if (href.includes('page=')) score += 3;
                      if (cls.includes('page') || cls.includes('pager') || cls.includes('pagination')) score += 3;
                      if (score > 0) scored.push([score, el]);
                    }
                    scored.sort((a, b) => b[0] - a[0]);
                    if (!scored.length) return false;
                    scored[0][1].click();
                    return true;
                    """
                )
            )
        except Exception:
            return False

    unchanged_rounds = 0
    for _ in range(8):
        before = len(seen_ids)
        if not _try_click_next_page():
            break
        time.sleep(1.1)
        products, href_cnt, malformed_cnt, local_expected = _collect_products_from_single_page(driver, driver.current_url)
        total_href_candidates += href_cnt
        total_malformed += malformed_cnt

        new_count = 0
        for pid, purl in products:
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            all_products.append((pid, purl))
            new_count += 1

        if _check_plateau(local_expected, href_cnt, products, new_count, "next-click"):
            break

        after = len(seen_ids)
        if after == before:
            unchanged_rounds += 1
        else:
            unchanged_rounds = 0
        if unchanged_rounds >= 2:
            break

    meta = {
        'plateau_detected': bool(plateau_detected),
        'expected_total': int(expected_total or 0),
        'captured_total': int(len(seen_ids)),
    }
    return all_products, total_href_candidates, total_malformed, meta

def _read_all_queue_rows(
    service,
    spreadsheet_id: str,
    queue_sheet_name: str,
    header_map: Dict[str, int],
    row_start: int = 2,
    row_end: int = 5000,
) -> List[Tuple[int, Dict[str, str]]]:
    last_col_index = max(header_map.values()) if header_map else 6
    last_col_letter = _col_letter(last_col_index)
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{queue_sheet_name}'!A{row_start}:{last_col_letter}{row_end}",
    ).execute()
    values = result.get("values", [])

    rows: List[Tuple[int, Dict[str, str]]] = []
    for offset, row in enumerate(values):
        row_num = row_start + offset
        mapped: Dict[str, str] = {}
        for header, col_index in header_map.items():
            mapped[header] = row[col_index].strip() if col_index < len(row) and row[col_index] else ""
        rows.append((row_num, mapped))
    return rows




def _read_seed_urls_from_seed_sheet(
    service,
    spreadsheet_id: str,
    seed_sheet_name: str,
    row_start: int = 2,
    row_end: int = 5000,
) -> List[Tuple[int, str]]:
    """Read seed URLs from seed-only tab (A=url, C=status)."""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{seed_sheet_name}'!A{row_start}:D{row_end}",
    ).execute()
    values = result.get('values', [])

    rows: List[Tuple[int, str]] = []
    for offset, row in enumerate(values):
        row_num = row_start + offset
        page_url = (row[0] if len(row) > 0 else '').strip()
        collect_status = (row[2] if len(row) > 2 else '').strip().lower()
        if collect_status and collect_status not in SEED_READY_STATUSES:
            continue
        if page_url and _is_http_url(page_url):
            rows.append((row_num, page_url))
    return rows


def _update_seed_row_simple(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_num: int,
    status: str,
    note: str,
) -> None:
    """Update seed-only tab row (B=????, C=????, D=??)."""
    now = _now_text()
    data = [
        {'range': f"'{sheet_name}'!B{row_num}", 'values': [[now]]},
        {'range': f"'{sheet_name}'!C{row_num}", 'values': [[status]]},
        {'range': f"'{sheet_name}'!D{row_num}", 'values': [[note]]},
    ]
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={'valueInputOption': 'USER_ENTERED', 'data': data},
    ).execute()

def _update_seed_row(service, spreadsheet_id: str, sheet_name: str, row_num: int, header_map: Dict[str, int], status: str, note: str) -> None:
    now = _now_text()
    updates = [
        ("수집일시", now),
        ("수집상태", status),
        ("비고", note),
    ]
    data = []
    for header, value in updates:
        col_idx = header_map[header]
        col_letter = _col_letter(col_idx)
        data.append(
            {
                "range": f"'{sheet_name}'!{col_letter}{row_num}",
                "values": [[value]],
            }
        )
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()


def _classify_exception(exc: Exception) -> str:
    if isinstance(exc, TimeoutException):
        return NOTE_TIMEOUT
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return NOTE_TIMEOUT
    if any(token in message for token in ["selector", "xpath", "no such element", "stale element"]):
        return NOTE_STRUCTURE_CHANGED
    if any(token in message for token in ["header", "column", "missing", "keyerror"]):
        return NOTE_DATA_MISSING
    if isinstance(exc, WebDriverException):
        return NOTE_CRAWL_FAILED
    return NOTE_CRAWL_FAILED


def collect_listing_queue_once(
    service,
    driver,
    spreadsheet_id: str,
    queue_sheet_name: str,
    seed_sheet_name: str,
    get_sheet_header_map_fn,
) -> Dict[str, int]:
    """Collect product URLs/IDs from listing page seed sheet into queue sheet."""
    header_map = get_sheet_header_map_fn(service, queue_sheet_name)
    missing_headers = [h for h in QUEUE_HEADERS if h not in header_map]
    if missing_headers:
        raise RuntimeError(f"? ?? ?? ??: {', '.join(missing_headers)}")

    rows = _read_all_queue_rows(service, spreadsheet_id, queue_sheet_name, header_map)

    existing_ids = set()
    for _row_num, row in rows:
        product_id = row.get(QUEUE_HEADERS[1], '').strip()
        if product_id:
            existing_ids.add(product_id)

    use_seed_sheet = bool(seed_sheet_name and seed_sheet_name != queue_sheet_name)
    if use_seed_sheet:
        seed_rows = _read_seed_urls_from_seed_sheet(
            service=service,
            spreadsheet_id=spreadsheet_id,
            seed_sheet_name=seed_sheet_name,
        )
        print(f"[queue] seed ?? ?? ??: '{seed_sheet_name}'")
    else:
        seed_rows: List[Tuple[int, str]] = []
        page_url_header = QUEUE_HEADERS[0]
        product_id_header = QUEUE_HEADERS[1]
        collect_status_header = QUEUE_HEADERS[4]
        for row_num, row in rows:
            page_url = row.get(page_url_header, '').strip()
            product_id = row.get(product_id_header, '').strip()
            collect_status = row.get(collect_status_header, '').strip().lower()
            if collect_status not in SEED_READY_STATUSES:
                continue
            if page_url and not product_id and _is_http_url(page_url):
                seed_rows.append((row_num, page_url))

    summary = {'seed_rows': len(seed_rows), 'new_rows': 0, 'duplicate_rows': 0, 'error_rows': 0}

    if not seed_rows:
        print(f"[queue] '{queue_sheet_name}' ??: ??? ???URL(seed row)? ????.")
        return summary

    print(f"[queue] '{queue_sheet_name}' ??: ???URL {len(seed_rows)}? ?? ??")

    for row_num, page_url in seed_rows:
        try:
            collected, href_candidates, malformed_count, collect_meta = _collect_products_from_listing_page(driver, page_url)
            append_values: List[List[str]] = []
            duplicate_count = 0

            for product_id, product_url in collected:
                if product_id in existing_ids:
                    duplicate_count += 1
                    continue
                existing_ids.add(product_id)
                append_values.append([
                    "",
                    product_id,
                    product_url,
                    _now_text(),
                    '????',
                    '??',
                    '',
                ])

            if append_values:
                service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{queue_sheet_name}'!A:G",
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body={'values': append_values},
                ).execute()
                summary['new_rows'] += len(append_values)

            summary['duplicate_rows'] += duplicate_count

            plateau_detected = bool((collect_meta or {}).get("plateau_detected"))
            expected_total = int((collect_meta or {}).get("expected_total") or 0)
            captured_total = int((collect_meta or {}).get("captured_total") or 0)
            if plateau_detected and expected_total > 0 and captured_total < expected_total:
                note = NOTE_DATA_MISSING
                print(
                    f"[queue] plateau summary: expected={expected_total} "
                    f"captured={captured_total} -> note={NOTE_DATA_MISSING}"
                )
            elif len(append_values) > 0:
                note = NOTE_DUPLICATE if duplicate_count > 0 else ''
            else:
                if href_candidates == 0:
                    note = NOTE_NO_PRODUCT
                elif malformed_count > 0:
                    note = NOTE_DATA_MISSING
                elif duplicate_count > 0:
                    note = NOTE_DUPLICATE
                else:
                    note = NOTE_NO_PRODUCT

            if use_seed_sheet:
                _update_seed_row_simple(
                    service=service,
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=seed_sheet_name,
                    row_num=row_num,
                    status='????',
                    note=note,
                )
            else:
                _update_seed_row(
                    service=service,
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=queue_sheet_name,
                    row_num=row_num,
                    header_map=header_map,
                    status='????',
                    note=note,
                )
            print(f"[queue] {row_num}? ??: ?? {len(append_values)}? / ?? {duplicate_count}? / ?? {note or '-'}")
        except Exception as exc:
            summary['error_rows'] += 1
            note = _classify_exception(exc)
            try:
                if use_seed_sheet:
                    _update_seed_row_simple(
                        service=service,
                        spreadsheet_id=spreadsheet_id,
                        sheet_name=seed_sheet_name,
                        row_num=row_num,
                        status='??',
                        note=note,
                    )
                else:
                    _update_seed_row(
                        service=service,
                        spreadsheet_id=spreadsheet_id,
                        sheet_name=queue_sheet_name,
                        row_num=row_num,
                        header_map=header_map,
                        status='??',
                        note=note,
                    )
            except Exception:
                pass
            print(f"[queue] {row_num}? ??: {note} ({exc})")

    print(
        f"[queue] ?? ??: seed={summary['seed_rows']} ??={summary['new_rows']} "
        f"??={summary['duplicate_rows']} ??={summary['error_rows']}"
    )
    return summary
