"""Google Sheets helpers shared across marketplace upload flows."""

from __future__ import annotations

import os
import re
from typing import Dict, List

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from marketplace.common.runtime import get_runtime_data_dir


def get_credentials_path(base_dir: str) -> str:
    """Return credentials.json path from runtime dir first, then project dir."""
    cred = os.path.join(get_runtime_data_dir(), "credentials.json")
    if os.path.exists(cred):
        return cred
    fallback = os.path.join(base_dir, "credentials.json")
    if os.path.exists(fallback):
        return fallback
    raise FileNotFoundError("credentials.json 파일을 찾을 수 없습니다")


def get_sheets_service(credentials_path: str):
    """Create Google Sheets API service."""
    creds = Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def resolve_sheet_name(service, spreadsheet_id: str, sheet_gids: List[int], default_sheet_name: str) -> str:
    """Find sheet title from configured GID, falling back to default name."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    target_gid = sheet_gids[0] if sheet_gids else None
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("sheetId") == target_gid:
            return props.get("title") or default_sheet_name
    return default_sheet_name


def column_index_to_letter(index: int) -> str:
    """Convert 0-based column index to Google Sheets column letters."""
    if index < 0:
        raise ValueError("열 인덱스는 0 이상이어야 합니다.")
    result = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_sheet_header_map(service, spreadsheet_id: str, sheet_name: str, header_row: int) -> Dict[str, int]:
    """Read header row and return header name -> 0-based column index map."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!{header_row}:{header_row}",
        ).execute()
        header_row_values = result.get("values", [[]])[0] if result.get("values") else []
        header_map: Dict[str, int] = {}
        for idx, value in enumerate(header_row_values):
            header = (value or "").strip()
            if header:
                header_map[header] = idx
        return header_map
    except Exception as exc:
        print(f"헤더 조회 실패: {exc}")
        return {}


def update_cell_by_header(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_name: str,
    value: str,
) -> bool:
    """Update a cell value by header name."""
    col_index = header_map.get(header_name)
    if col_index is None:
        return False

    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!{column_index_to_letter(col_index)}{row_num}",
            valueInputOption="USER_ENTERED",
            body={"values": [[value]]},
        ).execute()
        return True
    except Exception as exc:
        print(f"  {row_num}행 {header_name} 업데이트 실패: {exc}")
        return False


def read_upload_rows(
    service,
    *,
    spreadsheet_id: str,
    sheet_name: str,
    row_start: int,
    header_row: int,
    col_map: Dict[str, int],
    progress_status_header: str,
    status_completed: str,
    status_upload_ready: str,
    status_thumbnails_done: str,
    specific_row: int = 0,
) -> List[Dict[str, str]]:
    """Read upload target rows from sheet. Only rows with BUYMA price are included."""
    header_map = get_sheet_header_map(service, spreadsheet_id, sheet_name, header_row)
    status_index = header_map.get(progress_status_header)
    last_index = max(col_map["Y"], status_index if status_index is not None else col_map["Y"])
    last_col_letter = column_index_to_letter(last_index)

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A{row_start}:{last_col_letter}1000",
        ).execute()
    except Exception as exc:
        print(f"시트 읽기 실패: {exc}")
        return []

    rows_data: List[Dict[str, str]] = []
    for idx, row in enumerate(result.get("values", []), start=row_start):
        if specific_row and idx != specific_row:
            continue

        def cell(col_letter: str) -> str:
            col_index = col_map[col_letter]
            return row[col_index].strip() if col_index < len(row) and row[col_index] else ""

        def cell_by_index(index: int | None) -> str:
            if index is None:
                return ""
            return row[index].strip() if index < len(row) and row[index] else ""

        url = cell("B")
        product_name = cell("E")
        buyma_price = cell("M")

        if not url or not product_name or not buyma_price:
            if specific_row and idx == specific_row:
                missing = []
                if not url:
                    missing.append("URL(B열)")
                if not product_name:
                    missing.append("상품명(E열)")
                if not buyma_price:
                    missing.append("바이마판매가(M열)")
                print(f"  {idx}행 제외: 필수값 누락 -> {', '.join(missing)}")
            continue

        progress_status = cell_by_index(status_index)
        normalized_status = (progress_status or "").strip()
        if not specific_row:
            if normalized_status == status_completed:
                print(f"  {idx}행 건너뜀 (진행상태: {progress_status})")
                continue

            if normalized_status in {"업로드중", "UPLOADING"}:
                continue

            if status_index is not None and normalized_status not in {
                status_upload_ready,
                status_thumbnails_done,
                "THUMBNAILS_DONE",
                "업로드진행대기",
            }:
                continue

        v_cat = cell("V")
        w_cat = cell("W")
        x_cat = cell("X")
        y_cat = cell("Y")

        if w_cat or x_cat or y_cat:
            cat_large, cat_middle, cat_small = w_cat, x_cat, y_cat
        else:
            cat_large, cat_middle, cat_small = v_cat, w_cat, x_cat

        rows_data.append(
            {
                "row_num": idx,
                "url": url,
                "brand": cell("C"),
                "brand_en": cell("D"),
                "product_name_kr": product_name,
                "product_name_en": cell("F"),
                "musinsa_sku": cell("G"),
                "color_kr": cell("H"),
                "color_en": cell("I"),
                "size": cell("J"),
                "actual_size": cell("K"),
                "price_krw": cell("L"),
                "buyma_price": buyma_price,
                "image_paths": cell("N"),
                "shipping_cost": cell("O"),
                "musinsa_category_large": cat_large,
                "musinsa_category_middle": cat_middle,
                "musinsa_category_small": cat_small,
                "progress_status": progress_status,
            }
        )

    return rows_data


def extract_spreadsheet_id(raw_value: str) -> str:
    """Normalize spreadsheet id from either raw id or full Google Sheets URL."""
    sid = (raw_value or "").strip()
    if not sid:
        return ""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sid)
    if match:
        return match.group(1)
    match = re.search(r"(?:^|/)d/([a-zA-Z0-9-_]+)", sid)
    if match:
        return match.group(1)
    return sid
