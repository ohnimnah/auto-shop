"""Google Sheets read/write helper functions."""

import re
from typing import Dict, List, Tuple


def column_index_to_letter(index: int) -> str:
    """Convert 0-based column index to Google Sheets column letter."""
    if index < 0:
        raise ValueError("index must be >= 0")
    result = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def column_letter_to_index(column: str) -> int:
    """Convert a Google Sheets column letter to 0-based index."""
    value = (column or "").strip().upper()
    if not re.fullmatch(r"[A-Z]+", value):
        return -1
    result = 0
    for char in value:
        result = result * 26 + (ord(char) - 64)
    return result - 1


def max_column_letter(*columns: str) -> str:
    indexes = [column_letter_to_index(column) for column in columns]
    return column_index_to_letter(max([idx for idx in indexes if idx >= 0] or [24]))


def get_sheet_header_map(service, spreadsheet_id: str, sheet_name: str, header_row: int) -> Dict[str, int]:
    """Read header row and return header-name -> column-index map."""
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
        print(f" header lookup failed ({sheet_name}): {e}")
        return {}


def get_row_dynamic_values(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_names: List[str],
) -> Dict[str, str]:
    """Read dynamic column values for one row by header names."""
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
        print(f" {sheet_name} {row_num} dynamic column read failed: {e}")
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
    """Read dynamic column values for multiple rows in one request."""
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
        print(f" {sheet_name} dynamic column bulk read failed: {e}")
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
    """Update one cell by header name."""
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
        print(f" {sheet_name} {row_num} {header_name} update failed: {e}")
        return False


def parse_margin_rate(value: str) -> float | None:
    """Parse margin-rate string to percentage float."""
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
    """Resolve sheet title by gid."""
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("sheetId") == gid:
                return props.get("title")
    except Exception as e:
        print(f" sheet metadata lookup failed: {e}")
    return ""


def get_target_sheet_names(
    service,
    spreadsheet_id: str,
    sheet_gids: List[int],
    fallback_sheet_name: str,
) -> List[str]:
    """Resolve target sheet names from gids with fallback."""
    sheet_names: List[str] = []
    for gid in sheet_gids:
        title = get_sheet_name_by_gid(service, spreadsheet_id, gid)
        if title:
            sheet_names.append(title)
        else:
            print(f" could not resolve sheet name for gid {gid}")

    if not sheet_names:
        sheet_names = [fallback_sheet_name]
        print(f" gid-based sheet resolve failed. using fallback '{fallback_sheet_name}'")
    return sheet_names


def is_url_cell(value: str) -> bool:
    """Return True if value looks like URL."""
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
    """Read URL column and return (row_num, url) list."""
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
    columns = [
        sequence_column, url_column, brand_column, brand_en_column, product_name_kr_column, product_name_en_column,
        musinsa_sku_column, color_kr_column, color_en_column, size_column, actual_size_column, price_column,
        buyma_sell_price_column, image_paths_column, shipping_cost_column, category_large_column,
        category_middle_column, category_small_column,
    ]
    last_column = max_column_letter(*columns)
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A{row_num}:{last_column}{row_num}",
        ).execute()
        rows = result.get("values", [])
        row = rows[0] if rows else []
        def cell(column: str) -> str:
            index = column_letter_to_index(column)
            return row[index] if 0 <= index < len(row) else ""
        return {
            sequence_column: cell(sequence_column),
            url_column: cell(url_column),
            brand_column: cell(brand_column),
            brand_en_column: cell(brand_en_column),
            product_name_kr_column: cell(product_name_kr_column),
            product_name_en_column: cell(product_name_en_column),
            musinsa_sku_column: cell(musinsa_sku_column),
            color_kr_column: cell(color_kr_column),
            color_en_column: cell(color_en_column),
            size_column: cell(size_column),
            actual_size_column: cell(actual_size_column),
            price_column: cell(price_column),
            buyma_sell_price_column: cell(buyma_sell_price_column),
            image_paths_column: cell(image_paths_column),
            shipping_cost_column: cell(shipping_cost_column),
            category_large_column: cell(category_large_column),
            category_middle_column: cell(category_middle_column),
            category_small_column: cell(category_small_column),
        }
    except Exception as e:
        print(f" {sheet_name} {row_num} existing row read failed: {e}")
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
    columns = [
        sequence_column, url_column, brand_column, brand_en_column, product_name_kr_column, product_name_en_column,
        musinsa_sku_column, color_kr_column, color_en_column, size_column, actual_size_column, price_column,
        buyma_sell_price_column, image_paths_column, shipping_cost_column, category_large_column,
        category_middle_column, category_small_column,
    ]
    last_column = max_column_letter(*columns)
    min_row = min(row_numbers)
    max_row = max(row_numbers)
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A{min_row}:{last_column}{max_row}",
        ).execute()
        values = result.get("values", [])
        row_map: Dict[int, Dict[str, str]] = {}
        for offset, row_num in enumerate(range(min_row, max_row + 1)):
            row_values = values[offset] if offset < len(values) else []
            def cell(column: str, row=row_values) -> str:
                index = column_letter_to_index(column)
                return row[index] if 0 <= index < len(row) else ""
            row_map[row_num] = {
                sequence_column: cell(sequence_column),
                url_column: cell(url_column),
                brand_column: cell(brand_column),
                brand_en_column: cell(brand_en_column),
                product_name_kr_column: cell(product_name_kr_column),
                product_name_en_column: cell(product_name_en_column),
                musinsa_sku_column: cell(musinsa_sku_column),
                color_kr_column: cell(color_kr_column),
                color_en_column: cell(color_en_column),
                size_column: cell(size_column),
                actual_size_column: cell(actual_size_column),
                price_column: cell(price_column),
                buyma_sell_price_column: cell(buyma_sell_price_column),
                image_paths_column: cell(image_paths_column),
                shipping_cost_column: cell(shipping_cost_column),
                category_large_column: cell(category_large_column),
                category_middle_column: cell(category_middle_column),
                category_small_column: cell(category_small_column),
            }
        return row_map
    except Exception as e:
        print(f" {sheet_name} existing rows bulk read failed: {e}")
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
    """Batch update values with '[{range, values}]' payload."""
    if not updates:
        return True
    try:
        body = {"valueInputOption": value_input_option, "data": updates}
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body,
        ).execute()
        return True
    except Exception as e:
        print(f" batch update failed: {e}")
        return False
