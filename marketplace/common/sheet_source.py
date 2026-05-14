"""Google Sheets helpers shared across marketplace upload flows."""

from __future__ import annotations

import os
import re
from collections import Counter
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


def column_letter_to_index(letter: str) -> int:
    """Convert Google Sheets column letters to a 0-based index."""
    value = (letter or "").strip().upper()
    if not value or not value.isalpha():
        raise ValueError(f"유효한 열 글자가 아닙니다: {letter}")
    index = 0
    for char in value:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


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


def normalize_sheet_status(value: str) -> str:
    """Normalize status text for matching, including hidden whitespace."""
    text = str(value or "").strip()
    return re.sub(r"[\s\u200b\u200c\u200d\ufeff]+", "", text)


def _status_display(value: str) -> str:
    text = str(value or "").strip()
    return text if text else "(빈값)"


def _is_upload_ready_status(
    status: str,
    *,
    status_completed: str,
    status_upload_ready: str,
    status_thumbnails_done: str,
) -> bool:
    normalized = normalize_sheet_status(status)
    if normalized == normalize_sheet_status(status_completed):
        return False
    if normalized in {normalize_sheet_status("업로드중"), "UPLOADING"}:
        return False
    return normalized in {
        normalize_sheet_status(status_upload_ready),
        normalize_sheet_status(status_thumbnails_done),
        "THUMBNAILS_DONE",
        normalize_sheet_status("업로드진행대기"),
    }


def _read_range_values(service, spreadsheet_id: str, range_a1: str) -> List[List[str]]:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
    ).execute()
    return result.get("values", [])


def _read_upload_rows_legacy(
    service,
    *,
    spreadsheet_id: str,
    sheet_name: str,
    row_start: int,
    last_col_letter: str,
) -> List[List[str]]:
    return _read_range_values(
        service,
        spreadsheet_id,
        f"'{sheet_name}'!A{row_start}:{last_col_letter}",
    )


def read_upload_rows(
    service,
    *,
    spreadsheet_id: str,
    sheet_name: str,
    row_start: int,
    header_row: int,
    max_data_column: str,
    upload_columns: Dict[str, str],
    progress_status_header: str,
    status_completed: str,
    status_upload_ready: str,
    status_thumbnails_done: str,
    specific_row: int = 0,
) -> List[Dict[str, str]]:
    """Read upload target rows from sheet. Only rows with BUYMA price are included."""
    header_map = get_sheet_header_map(service, spreadsheet_id, sheet_name, header_row)
    status_index = header_map.get(progress_status_header)
    configured_indexes = [column_letter_to_index(max_data_column)]
    for letter in upload_columns.values():
        try:
            configured_indexes.append(column_letter_to_index(letter))
        except ValueError:
            pass
    max_data_index = max(configured_indexes)
    last_index = max(max_data_index, status_index if status_index is not None else max_data_index)
    last_col_letter = column_index_to_letter(last_index)
    if status_index is None:
        print(f"업로드 후보 없음: '{progress_status_header}' 헤더를 찾지 못해 안전상 업로드를 중단합니다.")
        return []

    def build_rows_data(detailed_rows: List[tuple[int, List[str]]]) -> List[Dict[str, str]]:
        rows_data: List[Dict[str, str]] = []
        for idx, row in detailed_rows:
            if specific_row and idx != specific_row:
                continue

            def cell(col_letter: str) -> str:
                col_index = column_letter_to_index(col_letter)
                return row[col_index].strip() if col_index < len(row) and row[col_index] else ""

            def field_cell(field_name: str) -> str:
                col_letter = upload_columns.get(field_name, "")
                return cell(col_letter) if col_letter else ""

            def field_label(field_name: str, fallback_label: str) -> str:
                col_letter = upload_columns.get(field_name, "")
                return f"{fallback_label}({col_letter}열)" if col_letter else fallback_label

            def cell_by_index(index: int | None) -> str:
                if index is None:
                    return ""
                return row[index].strip() if index < len(row) and row[index] else ""

            url = field_cell("url")
            product_name = field_cell("product_name_kr")
            buyma_price = field_cell("buyma_price")

            progress_status = cell_by_index(status_index)
            ready_status = _is_upload_ready_status(
                progress_status,
                status_completed=status_completed,
                status_upload_ready=status_upload_ready,
                status_thumbnails_done=status_thumbnails_done,
            )

            if not url or not product_name or not buyma_price:
                if (specific_row and idx == specific_row) or ready_status:
                    missing = []
                    if not url:
                        missing.append(field_label("url", "URL"))
                    if not product_name:
                        missing.append(field_label("product_name_kr", "상품명"))
                    if not buyma_price:
                        missing.append(field_label("buyma_price", "바이마판매가"))
                    print(f"  {idx}행 제외: 필수값 누락 -> {', '.join(missing)}")
                continue

            if normalize_sheet_status(progress_status) == normalize_sheet_status(status_completed):
                print(f"  {idx}행 건너뜀 (진행상태: {progress_status})")
                continue
            if not ready_status:
                if specific_row and idx == specific_row:
                    print(f"  {idx}행 제외: 업로드 대상 상태가 아닙니다 -> {progress_status or '(빈값)'}")
                continue

            cat_large = field_cell("musinsa_category_large")
            cat_middle = field_cell("musinsa_category_middle")
            cat_small = field_cell("musinsa_category_small")

            if not (cat_large or cat_middle or cat_small):
                cat_large = field_cell("category_legacy_large")
                cat_middle = field_cell("category_legacy_middle")
                cat_small = field_cell("category_legacy_small")

            rows_data.append(
                {
                    "row_num": idx,
                    "url": url,
                    "brand": field_cell("brand"),
                    "brand_en": field_cell("brand_en"),
                    "product_name_kr": product_name,
                    "product_name_jp": field_cell("product_name_jp"),
                    "product_name_en": field_cell("product_name_en"),
                    "musinsa_sku": field_cell("musinsa_sku"),
                    "color_kr": field_cell("color_kr"),
                    "color_en": field_cell("color_en"),
                    "size": field_cell("size"),
                    "actual_size": field_cell("actual_size"),
                    "price_krw": field_cell("price_krw"),
                    "buyma_price": buyma_price,
                    "image_paths": field_cell("image_paths"),
                    "shipping_cost": field_cell("shipping_cost"),
                    "musinsa_category_large": cat_large,
                    "musinsa_category_middle": cat_middle,
                    "musinsa_category_small": cat_small,
                    "progress_status": progress_status,
                }
            )
        return rows_data

    try:
        if specific_row:
            rows = _read_range_values(
                service,
                spreadsheet_id,
                f"'{sheet_name}'!A{specific_row}:{last_col_letter}{specific_row}",
            )
            return build_rows_data([(specific_row, rows[0] if rows else [])])

        candidate_rows: List[int] = []
        status_col = column_index_to_letter(status_index)
        status_rows = _read_range_values(
            service,
            spreadsheet_id,
            f"'{sheet_name}'!{status_col}{row_start}:{status_col}",
        )
        status_counts = Counter()
        for offset, row in enumerate(status_rows):
            progress_status = row[0] if row else ""
            normalized_status = normalize_sheet_status(progress_status)
            if normalized_status:
                status_counts[_status_display(progress_status)] += 1
            if _is_upload_ready_status(
                progress_status,
                status_completed=status_completed,
                status_upload_ready=status_upload_ready,
                status_thumbnails_done=status_thumbnails_done,
            ):
                candidate_rows.append(row_start + offset)
        if candidate_rows:
            print(f"업로드 후보 진행상태: {len(candidate_rows)}행 ({status_col}열)")
            preview = ", ".join(str(row_num) for row_num in candidate_rows[:20])
            suffix = "..." if len(candidate_rows) > 20 else ""
            print(f"업로드 후보 행: {preview}{suffix}")
        else:
            summary = ", ".join(f"{name}:{count}" for name, count in status_counts.most_common(6)) or "읽힌 상태값 없음"
            print(f"업로드 후보 없음: 진행상태 {status_col}열에서 대상 상태를 찾지 못했습니다. 상태 분포: {summary}")

        detailed_rows: List[tuple[int, List[str]]] = []
        chunk_size = 80
        for start in range(0, len(candidate_rows), chunk_size):
            chunk = candidate_rows[start:start + chunk_size]
            detail_ranges = [f"'{sheet_name}'!A{row_num}:{last_col_letter}{row_num}" for row_num in chunk]
            detail_batch = service.spreadsheets().values().batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=detail_ranges,
            ).execute()
            for row_num, item in zip(chunk, detail_batch.get("valueRanges", [])):
                values = item.get("values", [])
                detailed_rows.append((row_num, values[0] if values else []))
        return build_rows_data(detailed_rows)
    except Exception as exc:
        print(f"빠른 시트 읽기 실패, 전체 범위 읽기로 전환: {exc}")
        try:
            values = _read_upload_rows_legacy(
                service,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                row_start=row_start,
                last_col_letter=last_col_letter,
            )
            return build_rows_data([(idx, row) for idx, row in enumerate(values, start=row_start)])
        except Exception as fallback_exc:
            print(f"시트 읽기 실패: {fallback_exc}")
            return []


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
