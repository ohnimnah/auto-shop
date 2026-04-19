"""Google Sheets read/write helper functions."""

import re
from typing import Dict, List


def column_index_to_letter(index: int) -> str:
    """0-based 열 인덱스를 Google Sheets 열 문자로 변환한다."""
    if index < 0:
        raise ValueError("열 인덱스는 0 이상이어야 합니다.")
    result = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_sheet_header_map(service, spreadsheet_id: str, sheet_name: str, header_row: int) -> Dict[str, int]:
    """헤더명을 읽어 헤더명 -> 0-based 열 인덱스 맵을 반환한다."""
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
    except Exception as e:
        print(f" 헤더 조회 실패 ({sheet_name}): {e}")
        return {}


def get_row_dynamic_values(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_names: List[str],
) -> Dict[str, str]:
    """헤더명 기준으로 특정 행의 동적 컬럼 값을 읽는다."""
    target_indexes = [header_map[name] for name in header_names if name in header_map]
    if not target_indexes:
        return {}

    min_index = min(target_indexes)
    max_index = max(target_indexes)
    start_col = column_index_to_letter(min_index)
    end_col = column_index_to_letter(max_index)

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!{start_col}{row_num}:{end_col}{row_num}",
        ).execute()
        row = result.get("values", [[]])[0] if result.get("values") else []
    except Exception as e:
        print(f" {sheet_name} {row_num}행 동적 컬럼 조회 실패: {e}")
        return {}

    values: Dict[str, str] = {}
    for name in header_names:
        idx = header_map.get(name)
        if idx is None:
            continue
        offset = idx - min_index
        values[name] = row[offset].strip() if offset < len(row) and row[offset] else ""
    return values


def get_rows_dynamic_values_bulk(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_numbers: List[int],
    header_map: Dict[str, int],
    header_names: List[str],
) -> Dict[int, Dict[str, str]]:
    """헤더명 기준 동적 컬럼 값을 여러 행에서 한 번에 읽어 반환한다."""
    if not row_numbers:
        return {}

    target_indexes = [header_map[name] for name in header_names if name in header_map]
    if not target_indexes:
        return {row_num: {} for row_num in row_numbers}

    min_col_index = min(target_indexes)
    max_col_index = max(target_indexes)
    start_col = column_index_to_letter(min_col_index)
    end_col = column_index_to_letter(max_col_index)
    min_row = min(row_numbers)
    max_row = max(row_numbers)

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!{start_col}{min_row}:{end_col}{max_row}",
        ).execute()
        rows = result.get("values", [])
    except Exception as e:
        print(f" {sheet_name} 동적 컬럼 일괄 조회 실패: {e}")
        return {row_num: {} for row_num in row_numbers}

    row_set = set(row_numbers)
    values_map: Dict[int, Dict[str, str]] = {}
    for offset, row_num in enumerate(range(min_row, max_row + 1)):
        if row_num not in row_set:
            continue
        row = rows[offset] if offset < len(rows) else []
        row_values: Dict[str, str] = {}
        for name in header_names:
            idx = header_map.get(name)
            if idx is None:
                continue
            local_offset = idx - min_col_index
            row_values[name] = row[local_offset].strip() if local_offset < len(row) and row[local_offset] else ""
        values_map[row_num] = row_values

    for row_num in row_numbers:
        values_map.setdefault(row_num, {})
    return values_map


def update_cell_by_header(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_name: str,
    value: str,
) -> bool:
    """헤더명 기준으로 특정 셀 값을 업데이트한다."""
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
    except Exception as e:
        print(f" {sheet_name} {row_num}행 {header_name} 업데이트 실패: {e}")
        return False


def parse_margin_rate(value: str) -> float | None:
    """마진률 셀 문자열을 퍼센트 숫자로 변환한다."""
    text = (value or "").strip()
    if not text:
        return None

    has_percent = "%" in text
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned:
        return None

    try:
        parsed = float(cleaned)
    except ValueError:
        return None

    if has_percent:
        return parsed
    if 0 <= parsed <= 1:
        return parsed * 100
    return parsed
