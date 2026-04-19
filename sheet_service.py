"""Google Sheets read/write helper functions."""

import re
from typing import Dict, List, Tuple


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


def get_sheet_name_by_gid(service, spreadsheet_id: str, gid: int) -> str:
    """GID로 시트 이름을 찾는다."""
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("sheetId") == gid:
                return props.get("title")
    except Exception as e:
        print(f" 시트 메타데이터 조회 실패: {e}")
    return ""


def get_target_sheet_names(
    service,
    spreadsheet_id: str,
    sheet_gids: List[int],
    fallback_sheet_name: str,
) -> List[str]:
    """GID 목록으로 시트명을 찾고 실패 시 기본 시트명을 반환한다."""
    sheet_names: List[str] = []
    for gid in sheet_gids:
        title = get_sheet_name_by_gid(service, spreadsheet_id, gid)
        if title:
            sheet_names.append(title)
        else:
            print(f" GID {gid}에 해당하는 시트 이름을 찾을 수 없습니다")

    if not sheet_names:
        sheet_names = [fallback_sheet_name]
        print(f" GID 기반 시트 이름 찾기에 실패했습니다. 기본 시트 이름 '{fallback_sheet_name}'을(를) 사용합니다.")
    return sheet_names


def is_url_cell(value: str) -> bool:
    """셀값이 URL인지 감지한다."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    return value.startswith("http://") or value.startswith("https://")


def read_urls_from_sheet(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    url_column: str,
    row_start: int,
) -> List[Tuple[int, str]]:
    """Google Sheets에서 URL을 읽어 row 번호와 URL 목록을 반환한다."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!{url_column}{row_start}:{url_column}1000",
        ).execute()
        values = result.get("values", [])
        rows: List[Tuple[int, str]] = []
        for index, row in enumerate(values, start=row_start):
            if row and row[0].strip():
                url = row[0].strip()
                if is_url_cell(url):
                    rows.append((index, url))
        return rows
    except Exception as e:
        print(f" URL read failed ({sheet_name}): {e}")
        return []


def get_existing_row_values(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_num: int,
    sequence_column: str,
    url_column: str,
    brand_column: str,
    brand_en_column: str,
    product_name_kr_column: str,
    product_name_en_column: str,
    musinsa_sku_column: str,
    color_kr_column: str,
    color_en_column: str,
    size_column: str,
    actual_size_column: str,
    price_column: str,
    buyma_sell_price_column: str,
    image_paths_column: str,
    shipping_cost_column: str,
    category_large_column: str,
    category_middle_column: str,
    category_small_column: str,
) -> Dict[str, str]:
    """Read one row (A~Y) and map selected columns."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A{row_num}:Y{row_num}",
        ).execute()
        rows = result.get("values", [])
        row = rows[0] if rows else []

        return {
            sequence_column: row[0] if len(row) > 0 else "",
            url_column: row[1] if len(row) > 1 else "",
            brand_column: row[2] if len(row) > 2 else "",
            brand_en_column: row[3] if len(row) > 3 else "",
            product_name_kr_column: row[4] if len(row) > 4 else "",
            product_name_en_column: row[5] if len(row) > 5 else "",
            musinsa_sku_column: row[6] if len(row) > 6 else "",
            color_kr_column: row[7] if len(row) > 7 else "",
            color_en_column: row[8] if len(row) > 8 else "",
            size_column: row[9] if len(row) > 9 else "",
            actual_size_column: row[10] if len(row) > 10 else "",
            price_column: row[11] if len(row) > 11 else "",
            buyma_sell_price_column: row[12] if len(row) > 12 else "",
            image_paths_column: row[13] if len(row) > 13 else "",
            shipping_cost_column: row[14] if len(row) > 14 else "",
            category_large_column: row[22] if len(row) > 22 else "",
            category_middle_column: row[23] if len(row) > 23 else "",
            category_small_column: row[24] if len(row) > 24 else "",
        }
    except Exception as e:
        print(f" {sheet_name} {row_num}행 기존 데이터 조회 실패: {e}")
        return {}


def get_existing_rows_bulk(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_numbers: List[int],
    sequence_column: str,
    url_column: str,
    brand_column: str,
    brand_en_column: str,
    product_name_kr_column: str,
    product_name_en_column: str,
    musinsa_sku_column: str,
    color_kr_column: str,
    color_en_column: str,
    size_column: str,
    actual_size_column: str,
    price_column: str,
    buyma_sell_price_column: str,
    image_paths_column: str,
    shipping_cost_column: str,
    category_large_column: str,
    category_middle_column: str,
    category_small_column: str,
) -> Dict[int, Dict[str, str]]:
    """Read multiple rows (A~Y) in one request and map selected columns."""
    if not row_numbers:
        return {}

    min_row = min(row_numbers)
    max_row = max(row_numbers)
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A{min_row}:Y{max_row}",
        ).execute()
        values = result.get("values", [])

        row_map: Dict[int, Dict[str, str]] = {}
        for offset, row_num in enumerate(range(min_row, max_row + 1)):
            row_values = values[offset] if offset < len(values) else []
            mapped = {
                sequence_column: row_values[0] if len(row_values) > 0 else "",
                url_column: row_values[1] if len(row_values) > 1 else "",
                brand_column: row_values[2] if len(row_values) > 2 else "",
                brand_en_column: row_values[3] if len(row_values) > 3 else "",
                product_name_kr_column: row_values[4] if len(row_values) > 4 else "",
                product_name_en_column: row_values[5] if len(row_values) > 5 else "",
                musinsa_sku_column: row_values[6] if len(row_values) > 6 else "",
                color_kr_column: row_values[7] if len(row_values) > 7 else "",
                color_en_column: row_values[8] if len(row_values) > 8 else "",
                size_column: row_values[9] if len(row_values) > 9 else "",
                actual_size_column: row_values[10] if len(row_values) > 10 else "",
                price_column: row_values[11] if len(row_values) > 11 else "",
                buyma_sell_price_column: row_values[12] if len(row_values) > 12 else "",
                image_paths_column: row_values[13] if len(row_values) > 13 else "",
                shipping_cost_column: row_values[14] if len(row_values) > 14 else "",
                category_large_column: row_values[22] if len(row_values) > 22 else "",
                category_middle_column: row_values[23] if len(row_values) > 23 else "",
                category_small_column: row_values[24] if len(row_values) > 24 else "",
            }
            row_map[row_num] = mapped
        return row_map
    except Exception as e:
        print(f" {sheet_name} 기존 데이터 일괄 조회 실패: {e}")
        return {}


def update_value_by_range(
    service,
    spreadsheet_id: str,
    range_a1: str,
    value: str,
    value_input_option: str = "USER_ENTERED",
) -> bool:
    """Update one cell/range value by A1 range."""
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_a1,
            valueInputOption=value_input_option,
            body={"values": [[value]]},
        ).execute()
        return True
    except Exception as e:
        print(f" range update failed ({range_a1}): {e}")
        return False


def batch_update_values(
    service,
    spreadsheet_id: str,
    updates: List[Dict[str, object]],
    value_input_option: str = "USER_ENTERED",
) -> bool:
    """Batch update values with `[{range, values}]` payload."""
    if not updates:
        return True

    try:
        body = {
            "valueInputOption": value_input_option,
            "data": updates,
        }
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body,
        ).execute()
        return True
    except Exception as e:
        print(f" batch update failed: {e}")
        return False
