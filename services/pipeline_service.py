"""Pipeline/status decision helpers."""

import time
import re
from typing import Any, Dict, List, Tuple

from constants.status import STATUS_UPLOADING
from models.product_model import product_from_sheet_row, product_to_sheet_field_map


def _column_index_to_letter(index: int) -> str:
    """Convert 0-based column index to A1 letters."""
    letters = ""
    n = index + 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _build_header_cell_range(
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_name: str,
) -> str | None:
    """Build A1 range for one header cell."""
    col_index = header_map.get(header_name)
    if col_index is None:
        return None
    return f"'{sheet_name}'!{_column_index_to_letter(col_index)}{row_num}"


def _enqueue_update(updates_buffer: List[Dict[str, object]], range_a1: str | None, value: str) -> None:
    """Append a range/value pair into batch buffer."""
    if not range_a1:
        return
    updates_buffer.append({"range": range_a1, "values": [[value]]})


def _flush_updates_buffer(
    service,
    api: Dict[str, Any],
    updates_buffer: List[Dict[str, object]],
    reason: str,
) -> None:
    """Flush buffered updates with per-row fallback on failure."""
    if not updates_buffer:
        return

    batch_size = len(updates_buffer)
    print(f"[batch] buffer size={batch_size}")
    print(f"[batch] flush start: {reason}")

    success = False
    try:
        success = bool(api["batch_update_values"](service, updates_buffer))
    except Exception as exc:
        print(f"[batch] flush failure: {reason} error={exc}")

    if success:
        print(f"[batch] flush success: {reason} ({batch_size} updates)")
        updates_buffer.clear()
        return

    print(f"[batch] flush failure: {reason} -> fallback per-row update")
    fallback_ok = 0
    for update in list(updates_buffer):
        range_a1 = str(update.get("range", "") or "")
        values = update.get("values") or []
        value = ""
        if values and isinstance(values, list) and values[0]:
            value = str(values[0][0])
        try:
            if api["update_value_by_range"](service, range_a1, value):
                fallback_ok += 1
        except Exception as exc:
            print(f"[batch] fallback row failure: {range_a1} error={exc}")
    print(f"[batch] flush success: fallback {fallback_ok}/{batch_size}")
    updates_buffer.clear()


def _extract_row_from_a1(range_a1: str) -> int | None:
    """Extract trailing row number from an A1 range."""
    match = re.search(r"(\d+)$", str(range_a1 or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _collect_row_spans(updates: List[Dict[str, object]]) -> Tuple[int, int, int]:
    """Return (row_count, first_row, last_row) from update list."""
    row_set = set()
    for update in updates:
        row_num = _extract_row_from_a1(str(update.get("range", "") or ""))
        if row_num is not None:
            row_set.add(row_num)
    if not row_set:
        return 0, -1, -1
    return len(row_set), min(row_set), max(row_set)


def _flush_multi_row_buffer(
    service,
    api: Dict[str, Any],
    updates_buffer: List[Dict[str, object]],
    reason: str,
) -> List[int]:
    """Flush multi-row buffer with row-batch and per-range fallbacks."""
    if not updates_buffer:
        return []

    row_count, first_row, last_row = _collect_row_spans(updates_buffer)
    cell_count = len(updates_buffer)
    all_rows = sorted({
        row_num
        for row_num in (_extract_row_from_a1(str(update.get("range", "") or "")) for update in updates_buffer)
        if row_num is not None
    })
    print(
        f"[batch][multi] flush start: {reason} rows={row_count} cells={cell_count} "
        f"first_row={first_row} last_row={last_row}"
    )

    success = False
    try:
        success = bool(api["batch_update_values"](service, updates_buffer))
    except Exception as exc:
        print(f"[batch][multi] flush failure: {reason} error={exc}")

    if success:
        print(f"[batch][multi] flush success: {reason} rows={row_count} cells={cell_count}")
        updates_buffer.clear()
        return all_rows

    per_row_groups: Dict[int, List[Dict[str, object]]] = {}
    for update in updates_buffer:
        row_num = _extract_row_from_a1(str(update.get("range", "") or ""))
        if row_num is None:
            continue
        per_row_groups.setdefault(row_num, []).append(update)

    print(f"[batch][multi] fallback start: row-batch ({len(per_row_groups)} rows)")
    row_batch_ok = 0
    range_fallback_ok = 0
    total_range_fallback = 0
    for row_num in sorted(per_row_groups):
        row_updates = per_row_groups[row_num]
        try:
            row_success = bool(api["batch_update_values"](service, row_updates))
        except Exception as exc:
            row_success = False
            print(f"[batch][multi] row-batch failure row={row_num} error={exc}")

        if row_success:
            row_batch_ok += 1
            continue

        # Final fallback: per-range updates for this row.
        total_range_fallback += len(row_updates)
        for update in row_updates:
            range_a1 = str(update.get("range", "") or "")
            values = update.get("values") or []
            value = ""
            if values and isinstance(values, list) and values[0]:
                value = str(values[0][0])
            try:
                if api["update_value_by_range"](service, range_a1, value):
                    range_fallback_ok += 1
            except Exception as exc:
                print(f"[batch][multi] per-range failure range={range_a1} error={exc}")

    print(
        f"[batch][multi] fallback result: row_batch_ok={row_batch_ok}/{len(per_row_groups)} "
        f"per_range_ok={range_fallback_ok}/{total_range_fallback}"
    )
    updates_buffer.clear()
    return sorted(per_row_groups.keys())


def determine_progress_status(
    margin_rate: float | None,
    margin_threshold_percent: float,
    status_hold: str,
    status_crawled: str,
) -> str:
    """Compute next progress status from margin rate."""
    if margin_rate is not None and margin_rate < margin_threshold_percent:
        return status_hold
    return status_crawled


def is_crawler_ready_status(status: str, status_waiting: str, status_new: str) -> bool:
    """Return whether crawler worker can pick this row."""
    normalized = (status or "").strip()
    return normalized in {"", status_waiting, status_new, "NEW"}


def is_image_ready_status(status: str, status_crawled: str, status_image_ready: str) -> bool:
    """Return whether image worker can pick this row."""
    normalized = (status or "").strip()
    return normalized in {status_crawled, "CRAWLED", status_image_ready}


def is_thumbnail_ready_status(
    status: str,
    status_images_saved: str,
    status_thumbnail_ready: str,
) -> bool:
    """Return whether thumbnail worker can pick this row."""
    normalized = (status or "").strip()
    return normalized in {status_images_saved, "IMAGES_SAVED", status_thumbnail_ready}


def is_empty_cell(value: str) -> bool:
    """Return True when the value should be considered empty."""
    return str(value or "").strip() == ""


def build_incremental_payload(
    sheet_name: str,
    row_num: int,
    row_start: int,
    product_info: Any,
    existing_values: Dict[str, str],
    sequence_column: str,
    brand_column: str,
    brand_en_column: str,
    product_name_kr_column: str,
    musinsa_sku_column: str,
    color_kr_column: str,
    size_column: str,
    actual_size_column: str,
    price_column: str,
    buyma_sell_price_column: str,
    image_paths_column: str,
    shipping_cost_column: str,
    category_large_column: str,
    category_middle_column: str,
    category_small_column: str,
) -> List[Dict[str, object]]:
    """Build update payload for only empty target cells."""
    product_map = product_to_sheet_field_map(product_info)
    sequence = f"{row_num - row_start + 1:03d}"
    candidates = [
        (sequence_column, sequence),
        (brand_column, product_map.get("brand", "")),
        (brand_en_column, product_map.get("brand_en", "")),
        (product_name_kr_column, product_map.get("product_name_kr", "")),
        (musinsa_sku_column, product_map.get("musinsa_sku", "")),
        (color_kr_column, product_map.get("color_kr", "")),
        (size_column, product_map.get("size", "")),
        (actual_size_column, product_map.get("actual_size", "")),
        (price_column, product_map.get("price", "")),
        (buyma_sell_price_column, product_map.get("buyma_price", "")),
        (image_paths_column, product_map.get("image_paths", "")),
        (shipping_cost_column, product_map.get("shipping_cost", "")),
        (category_large_column, product_map.get("musinsa_category_large", "")),
        (category_middle_column, product_map.get("musinsa_category_middle", "")),
        (category_small_column, product_map.get("musinsa_category_small", "")),
    ]

    updates: List[Dict[str, object]] = []
    for column, new_value in candidates:
        if is_empty_cell(new_value):
            continue

        current_value = existing_values.get(column, "")
        if is_empty_cell(current_value):
            updates.append(
                {
                    "range": f"'{sheet_name}'!{column}{row_num}",
                    "values": [[new_value]],
                }
            )
    return updates


def row_needs_update(
    existing_values: Dict[str, str],
    require_image_paths: bool,
    brand_column: str,
    brand_en_column: str,
    product_name_kr_column: str,
    musinsa_sku_column: str,
    color_kr_column: str,
    size_column: str,
    actual_size_column: str,
    price_column: str,
    buyma_sell_price_column: str,
    shipping_cost_column: str,
    image_paths_column: str,
) -> bool:
    """Return True if any required output column is still empty."""
    target_columns = [
        brand_column,
        brand_en_column,
        product_name_kr_column,
        musinsa_sku_column,
        color_kr_column,
        size_column,
        actual_size_column,
        price_column,
        buyma_sell_price_column,
        shipping_cost_column,
    ]
    if require_image_paths:
        target_columns.append(image_paths_column)

    for column in target_columns:
        if is_empty_cell(existing_values.get(column, "")):
            return True
    return False


def row_has_existing_output(
    existing_values: Dict[str, str],
    brand_column: str,
    brand_en_column: str,
    product_name_kr_column: str,
    musinsa_sku_column: str,
    color_kr_column: str,
    size_column: str,
    actual_size_column: str,
    price_column: str,
    buyma_sell_price_column: str,
    image_paths_column: str,
    shipping_cost_column: str,
) -> bool:
    """Return True if any output column already has a value."""
    target_columns = [
        brand_column,
        brand_en_column,
        product_name_kr_column,
        musinsa_sku_column,
        color_kr_column,
        size_column,
        actual_size_column,
        price_column,
        buyma_sell_price_column,
        image_paths_column,
        shipping_cost_column,
    ]
    for column in target_columns:
        if not is_empty_cell(existing_values.get(column, "")):
            return True
    return False


def row_needs_image_download(existing_values: Dict[str, str], image_paths_column: str) -> bool:
    """Return True when image paths column is empty."""
    return is_empty_cell(existing_values.get(image_paths_column, ""))


def _product_to_dict(product_info: Any) -> Dict[str, str]:
    return product_to_sheet_field_map(product_info)


def _sheet_product_column_map(cfg: Dict[str, Any]) -> Dict[str, str]:
    """Map Product fields to sheet column letters from cfg."""
    return {
        "brand": str(cfg.get("BRAND_COLUMN", "") or ""),
        "brand_en": str(cfg.get("BRAND_EN_COLUMN", "") or ""),
        "product_name_kr": str(cfg.get("PRODUCT_NAME_KR_COLUMN", "") or ""),
        "musinsa_sku": str(cfg.get("MUSINSA_SKU_COLUMN", "") or ""),
        "color_kr": str(cfg.get("COLOR_KR_COLUMN", "") or ""),
        "size": str(cfg.get("SIZE_COLUMN", "") or ""),
        "actual_size": str(cfg.get("ACTUAL_SIZE_COLUMN", "") or ""),
        "price": str(cfg.get("PRICE_COLUMN", "") or ""),
        "buyma_price": str(cfg.get("BUYMA_SELL_PRICE_COLUMN", "") or ""),
        "image_paths": str(cfg.get("IMAGE_PATHS_COLUMN", "") or ""),
        "shipping_cost": str(cfg.get("SHIPPING_COST_COLUMN", "") or ""),
        "musinsa_category_large": str(cfg.get("CATEGORY_LARGE_COLUMN", "") or ""),
        "musinsa_category_middle": str(cfg.get("CATEGORY_MIDDLE_COLUMN", "") or ""),
        "musinsa_category_small": str(cfg.get("CATEGORY_SMALL_COLUMN", "") or ""),
    }


def process_sheet_once(
    service,
    driver,
    sheet_name: str,
    watch_mode: bool,
    download_images: bool,
    make_thumbnails: bool,
    api: Dict[str, Any],
    cfg: Dict[str, Any],
) -> None:
    """Run one sheet scan cycle using injected APIs/config."""
    print(f"'{sheet_name}' ?쒗듃?먯꽌 B??留곹겕瑜??쎈뒗 以?..")
    rows = api["read_urls_from_sheet"](service, sheet_name)
    if not rows:
        print(f"'{sheet_name}' ?쒗듃??B?댁뿉 泥섎━??URL???놁뒿?덈떎.")
        return

    header_map = api["get_sheet_header_map"](service, sheet_name)
    has_margin_header = cfg["MARGIN_RATE_HEADER"] in header_map
    has_status_header = cfg["PROGRESS_STATUS_HEADER"] in header_map
    if not has_margin_header:
        print(f"'{sheet_name}' ?쒗듃: '{cfg['MARGIN_RATE_HEADER']}' ?ㅻ뜑瑜?李얠? 紐삵뻽?듬땲??")
    if not has_status_header:
        print(f"'{sheet_name}' ?쒗듃: '{cfg['PROGRESS_STATUS_HEADER']}' ?ㅻ뜑瑜?李얠? 紐삵뻽?듬땲??")

    row_numbers = [row_num for row_num, _ in rows]
    existing_rows_map = api["get_existing_rows_bulk"](service, sheet_name, row_numbers)
    dynamic_rows_map = api["get_rows_dynamic_values_bulk"](
        service,
        sheet_name,
        row_numbers,
        header_map,
        [cfg["MARGIN_RATE_HEADER"], cfg["PROGRESS_STATUS_HEADER"]],
    )

    target_rows: List[Tuple[int, str]] = []
    for row_num, url in rows:
        existing_values = existing_rows_map.get(row_num, {})
        dynamic_values = dynamic_rows_map.get(row_num, {})
        margin_rate = api["parse_margin_rate"](dynamic_values.get(cfg["MARGIN_RATE_HEADER"], ""))
        current_status = dynamic_values.get(cfg["PROGRESS_STATUS_HEADER"], "")

        if make_thumbnails:
            if api["is_thumbnail_ready_status"](current_status):
                target_rows.append((row_num, url))
        elif download_images:
            if api["is_image_ready_status"](current_status) and api["row_needs_image_download"](existing_values):
                target_rows.append((row_num, url))
        else:
            needs_update = api["row_needs_update"](existing_values, require_image_paths=False)
            shipping_missing = api["is_empty_cell"](existing_values.get(cfg["SHIPPING_COST_COLUMN"], ""))
            status_normalized = (current_status or "").strip()
            should_backfill_shipping = shipping_missing and status_normalized not in {
                cfg["STATUS_COMPLETED"],
                cfg["STATUS_UPLOAD_READY"],
                STATUS_UPLOADING,
            }
            if (api["is_crawler_ready_status"](current_status) and needs_update) or should_backfill_shipping:
                target_rows.append((row_num, url))

    if not target_rows:
        print(f"'{sheet_name}' ?쒗듃: ?좉퇋 ?묒꽦 ??곸씠 ?놁뒿?덈떎.")
        return

    print(f"'{sheet_name}' ?쒗듃: {len(target_rows)}媛??됱쓣 泥섎━?⑸땲??")

    updates_buffer: List[Dict[str, object]] = []
    flush_size = int(cfg.get("BATCH_FLUSH_SIZE", 60))
    sheet_product_columns = _sheet_product_column_map(cfg)

    if make_thumbnails:
        print(f"'{sheet_name}' thumbnail mode start")
        for idx, _url in target_rows:
            print(f"[{sheet_name}] row {idx} thumbnail processing")
            existing_values_for_row = existing_rows_map.get(idx, {})
            folder_path = api["resolve_image_folder_from_paths"](existing_values_for_row.get(cfg["IMAGE_PATHS_COLUMN"], ""))
            brand = api["build_thumbnail_brand"](existing_values_for_row)
            if has_status_header:
                _enqueue_update(
                    updates_buffer,
                    _build_header_cell_range(sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"]),
                    cfg["STATUS_THUMBNAILING"],
                )
            if api["create_thumbnail_for_folder"](folder_path, brand):
                if has_status_header:
                    _enqueue_update(
                        updates_buffer,
                        _build_header_cell_range(sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"]),
                        cfg["STATUS_THUMBNAILS_DONE"],
                    )
                    print(f" {sheet_name} row {idx} status -> {cfg['STATUS_THUMBNAILS_DONE']}")
            elif has_status_header:
                _enqueue_update(
                    updates_buffer,
                    _build_header_cell_range(sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"]),
                    cfg["STATUS_ERROR"],
                )
                print(f" {sheet_name} row {idx} status -> {cfg['STATUS_ERROR']}")
            if len(updates_buffer) >= flush_size:
                _flush_updates_buffer(service, api, updates_buffer, f"thumbnail-row-{idx}")
            time.sleep(cfg["THUMB_ROW_DELAY_SECONDS"])
        _flush_updates_buffer(service, api, updates_buffer, "thumbnail-final")
        return

    if download_images:
        print(f"'{sheet_name}' image download mode start")
        for idx, url in target_rows:
            print(f"[{sheet_name}] row {idx} image processing: {url}")
            existing_values_for_row = existing_rows_map.get(idx, {})
            existing_product_for_row = product_from_sheet_row(existing_values_for_row, sheet_product_columns)
            sheet_sku = existing_product_for_row.musinsa_sku
            if has_status_header:
                _enqueue_update(
                    updates_buffer,
                    _build_header_cell_range(sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"]),
                    cfg["STATUS_DOWNLOADING"],
                )
            product = api["scrape_musinsa_product"](
                driver,
                url,
                idx,
                existing_sku=sheet_sku,
                download_images=True,
                images_only=True,
            )
            product_info = _product_to_dict(product)

            image_paths = product_info.get("image_paths", "")
            if is_empty_cell(image_paths):
                print(f" {sheet_name} row {idx}: skip N update (empty image paths)")
            elif not is_empty_cell(existing_values_for_row.get(cfg["IMAGE_PATHS_COLUMN"], "")):
                print(f" {sheet_name} row {idx}: skip N update (already filled)")
            else:
                _enqueue_update(
                    updates_buffer,
                    f"'{sheet_name}'!{cfg['IMAGE_PATHS_COLUMN']}{idx}",
                    image_paths,
                )
                print(f" {sheet_name} row {idx}: queue N(image_paths) update")

            logo_url = (product_info.get("brand_logo_url") or "").strip()
            if logo_url and image_paths:
                folder_name = api["build_image_folder_name"](idx, product_info.get("product_name_kr", ""))
                api["download_brand_logo"](logo_url, folder_name, image_paths)
            if image_paths and has_status_header:
                _enqueue_update(
                    updates_buffer,
                    _build_header_cell_range(sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"]),
                    cfg["STATUS_IMAGES_SAVED"],
                )
                print(f" {sheet_name} row {idx} status -> {cfg['STATUS_IMAGES_SAVED']}")
            if len(updates_buffer) >= flush_size:
                _flush_updates_buffer(service, api, updates_buffer, f"image-row-{idx}")
            time.sleep(cfg["IMAGE_ROW_DELAY_SECONDS"])
        _flush_updates_buffer(service, api, updates_buffer, "image-final")
        return

    shipping_table = api["read_shipping_table"](service, sheet_name)
    if not shipping_table:
        print(f"'{sheet_name}' ???: ??????????Z/AA/AB)????? ??? O???????? ????????")

    multi_row_buffer: List[Dict[str, object]] = []
    pending_status_rows: set[int] = set()
    flush_rows_threshold = int(cfg.get("BATCH_FLUSH_ROWS", 10))
    flush_cells_threshold = int(cfg.get("BATCH_FLUSH_CELLS", 140))

    def _flush_normal_buffer(reason: str, force: bool = False) -> List[int]:
        if not multi_row_buffer:
            return []
        row_count, _, _ = _collect_row_spans(multi_row_buffer)
        cell_count = len(multi_row_buffer)
        if not force and row_count < flush_rows_threshold and cell_count < flush_cells_threshold:
            return []
        return _flush_multi_row_buffer(service, api, multi_row_buffer, reason)

    def _write_status_for_row(row_num: int) -> None:
        if not has_status_header:
            return
        dynamic_values = api["get_row_dynamic_values"](
            service,
            sheet_name,
            row_num,
            header_map,
            [cfg["MARGIN_RATE_HEADER"], cfg["PROGRESS_STATUS_HEADER"]],
        )
        margin_rate = api["parse_margin_rate"](dynamic_values.get(cfg["MARGIN_RATE_HEADER"], ""))
        current_status = dynamic_values.get(cfg["PROGRESS_STATUS_HEADER"], "")
        next_status = api["determine_progress_status"](margin_rate)

        if next_status != cfg["STATUS_HOLD"]:
            refreshed_values = api["get_existing_row_values"](service, sheet_name, row_num)
            if not api["row_needs_update"](refreshed_values, require_image_paths=False):
                next_status = cfg["STATUS_CRAWLED"]

        if current_status != next_status:
            api["update_cell_by_header"](
                service,
                sheet_name,
                row_num,
                header_map,
                cfg["PROGRESS_STATUS_HEADER"],
                next_status,
            )
            if margin_rate is None:
                print(f" {sheet_name} {row_num}????? ??????: {next_status} (??????????")
            else:
                print(f" {sheet_name} {row_num}????? ??????: {next_status} (?????{margin_rate:.2f}%)")

    try:
        for idx, url in target_rows:
            print(f"[{sheet_name}] {idx}????? ?? {url}")
            existing_values_for_row = existing_rows_map.get(idx, {})
            existing_product_for_row = product_from_sheet_row(existing_values_for_row, sheet_product_columns)
            sheet_sku = existing_product_for_row.musinsa_sku
            if has_status_header:
                api["update_cell_by_header"](
                    service,
                    sheet_name,
                    idx,
                    header_map,
                    cfg["PROGRESS_STATUS_HEADER"],
                    cfg["STATUS_CRAWLING"],
                )

            try:
                product = api["scrape_musinsa_product"](
                    driver,
                    url,
                    idx,
                    existing_sku=sheet_sku,
                    download_images=download_images,
                )
                product_info = _product_to_dict(product)
                estimated_weight = api["estimate_weight"](
                    product_info.get("product_name_kr", ""),
                    product_info.get("opt_kind_cd", ""),
                )
                shipping_cost = api["lookup_shipping_cost"](shipping_table, estimated_weight)
                if shipping_cost:
                    product_info["shipping_cost"] = shipping_cost
                    print(f"    ????????: ??? {estimated_weight}kg -> KRW {shipping_cost}")
                else:
                    print(f"    ???????? ???: ???????? ?????????????(??? {estimated_weight}kg)")

                row_updates = api["write_to_sheet"](
                    service,
                    sheet_name,
                    idx,
                    product_info,
                    existing_rows_map.get(idx, {}),
                    return_updates_only=True,
                )
                if row_updates:
                    multi_row_buffer.extend(row_updates)
                pending_status_rows.add(idx)
            except Exception as row_exc:
                print(f" {sheet_name} {idx}? ?? ??: {row_exc}")
                if has_status_header:
                    # keep critical error marking immediate for observability
                    api["update_cell_by_header"](
                        service,
                        sheet_name,
                        idx,
                        header_map,
                        cfg["PROGRESS_STATUS_HEADER"],
                        cfg["STATUS_ERROR"],
                    )

            flushed_rows = _flush_normal_buffer(f"normal-row-{idx}")
            if flushed_rows:
                for flushed_row in flushed_rows:
                    if flushed_row in pending_status_rows:
                        _write_status_for_row(flushed_row)
                        pending_status_rows.discard(flushed_row)

            time.sleep(cfg["CRAWLER_ROW_DELAY_SECONDS"])

        flushed_rows = _flush_normal_buffer("normal-loop-end-data", force=True)
        for flushed_row in flushed_rows:
            if flushed_row in pending_status_rows:
                _write_status_for_row(flushed_row)
                pending_status_rows.discard(flushed_row)
    finally:
        _flush_normal_buffer("normal-finally", force=True)




