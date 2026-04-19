"""Listing-page queue collection helpers (safe additive feature).

Queue sheet fixed columns:
페이지URL | 상품ID | 상품URL | 수집일시 | 수집상태 | 상세크롤링상태 | 비고
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Dict, List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

QUEUE_HEADERS = [
    "페이지URL",
    "상품ID",
    "상품URL",
    "수집일시",
    "수집상태",
    "상세크롤링상태",
    "비고",
]


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


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_http_url(value: str) -> bool:
    text = (value or "").strip()
    return text.startswith("http://") or text.startswith("https://")


def _extract_musinsa_product_id_and_url(href: str) -> Tuple[str, str]:
    text = (href or "").strip()
    if not text:
        return "", ""
    # Musinsa patterns
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


def _collect_products_from_listing_page(driver, page_url: str) -> List[Tuple[str, str]]:
    driver.get(page_url)
    time.sleep(1.2)

    # Simple progressive scroll for lazy-loaded listing pages
    for _ in range(4):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.6)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    seen = set()
    products: List[Tuple[str, str]] = []
    for a_tag in soup.select("a[href]"):
        href = (a_tag.get("href") or "").strip()
        if not href:
            continue
        full_href = urljoin(page_url, href)
        product_id, product_url = _extract_musinsa_product_id_and_url(full_href)
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)
        products.append((product_id, product_url))
    return products


def _read_all_queue_rows(
    service,
    spreadsheet_id: str,
    queue_sheet_name: str,
    header_map: Dict[str, int],
    row_start: int = 2,
    row_end: int = 5000,
) -> List[Tuple[int, Dict[str, str]]]:
    last_col_index = max(header_map.values()) if header_map else 6
    last_col_letter = chr(ord("A") + min(last_col_index, 25))
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


def collect_listing_queue_once(
    service,
    driver,
    spreadsheet_id: str,
    queue_sheet_name: str,
    get_sheet_header_map_fn,
) -> Dict[str, int]:
    """Collect product URLs/IDs from listing page queue sheet."""
    header_map = get_sheet_header_map_fn(service, queue_sheet_name)
    missing_headers = [h for h in QUEUE_HEADERS if h not in header_map]
    if missing_headers:
        raise RuntimeError(f"큐 시트 헤더 누락: {', '.join(missing_headers)}")

    rows = _read_all_queue_rows(service, spreadsheet_id, queue_sheet_name, header_map)

    existing_ids = set()
    seed_rows: List[Tuple[int, str]] = []
    for row_num, row in rows:
        page_url = row.get("페이지URL", "").strip()
        product_id = row.get("상품ID", "").strip()
        if product_id:
            existing_ids.add(product_id)
        if page_url and not product_id and _is_http_url(page_url):
            seed_rows.append((row_num, page_url))

    summary = {
        "seed_rows": len(seed_rows),
        "new_rows": 0,
        "duplicate_rows": 0,
        "error_rows": 0,
    }

    if not seed_rows:
        print(f"[queue] '{queue_sheet_name}' 시트: 수집할 페이지URL(seed row)이 없습니다.")
        return summary

    print(f"[queue] '{queue_sheet_name}' 시트: 페이지URL {len(seed_rows)}건 수집 시작")

    for row_num, page_url in seed_rows:
        now = _now_text()
        try:
            collected = _collect_products_from_listing_page(driver, page_url)
            append_values: List[List[str]] = []
            duplicate_count = 0

            for product_id, product_url in collected:
                if not product_id:
                    continue
                if product_id in existing_ids:
                    duplicate_count += 1
                    continue
                existing_ids.add(product_id)
                append_values.append([
                    page_url,
                    product_id,
                    product_url,
                    now,
                    "수집완료",
                    "대기",
                    "",
                ])

            if append_values:
                service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{queue_sheet_name}'!A:G",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": append_values},
                ).execute()
                summary["new_rows"] += len(append_values)

            summary["duplicate_rows"] += duplicate_count
            memo = f"신규 {len(append_values)}건, 중복 {duplicate_count}건"

            # seed row 상태/비고 업데이트
            updates = [
                ("수집일시", now),
                ("수집상태", "수집완료"),
                ("비고", memo),
            ]
            data = []
            for header, value in updates:
                col_idx = header_map[header]
                col_letter = chr(ord("A") + min(col_idx, 25))
                data.append(
                    {
                        "range": f"'{queue_sheet_name}'!{col_letter}{row_num}",
                        "values": [[value]],
                    }
                )
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data},
            ).execute()
            print(f"[queue] {row_num}행 완료: {memo}")
        except Exception as exc:
            summary["error_rows"] += 1
            reason = str(exc).replace("\n", " ").strip()[:250]
            try:
                updates = [
                    ("수집일시", now),
                    ("수집상태", "오류"),
                    ("비고", reason),
                ]
                data = []
                for header, value in updates:
                    col_idx = header_map[header]
                    col_letter = chr(ord("A") + min(col_idx, 25))
                    data.append(
                        {
                            "range": f"'{queue_sheet_name}'!{col_letter}{row_num}",
                            "values": [[value]],
                        }
                    )
                service.spreadsheets().values().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"valueInputOption": "USER_ENTERED", "data": data},
                ).execute()
            except Exception:
                pass
            print(f"[queue] {row_num}행 오류: {reason}")

    print(
        f"[queue] 수집 종료: seed={summary['seed_rows']} 신규={summary['new_rows']} "
        f"중복={summary['duplicate_rows']} 오류={summary['error_rows']}"
    )
    return summary
