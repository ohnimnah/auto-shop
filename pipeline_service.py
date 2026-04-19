"""Pipeline/status decision helpers."""

import time
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Tuple


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
    product_info: Dict[str, str],
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
    sequence = f"{row_num - row_start + 1:03d}"
    candidates = [
        (sequence_column, sequence),
        (brand_column, product_info.get("brand", "")),
        (brand_en_column, product_info.get("brand_en", "")),
        (product_name_kr_column, product_info.get("product_name_kr", "")),
        (musinsa_sku_column, product_info.get("musinsa_sku", "")),
        (color_kr_column, product_info.get("color_kr", "")),
        (size_column, product_info.get("size", "")),
        (actual_size_column, product_info.get("actual_size", "")),
        (price_column, product_info.get("price", "")),
        (buyma_sell_price_column, product_info.get("buyma_price", "")),
        (image_paths_column, product_info.get("image_paths", "")),
        (shipping_cost_column, product_info.get("shipping_cost", "")),
        (category_large_column, product_info.get("musinsa_category_large", "")),
        (category_middle_column, product_info.get("musinsa_category_middle", "")),
        (category_small_column, product_info.get("musinsa_category_small", "")),
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
    if product_info is None:
        return {}
    if isinstance(product_info, dict):
        return product_info
    if is_dataclass(product_info):
        return asdict(product_info)
    if hasattr(product_info, "to_dict"):
        return product_info.to_dict()
    return {}


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
    print(f"'{sheet_name}' 시트에서 B열 링크를 읽는 중...")
    rows = api["read_urls_from_sheet"](service, sheet_name)
    if not rows:
        print(f"'{sheet_name}' 시트의 B열에 처리할 URL이 없습니다.")
        return

    header_map = api["get_sheet_header_map"](service, sheet_name)
    has_margin_header = cfg["MARGIN_RATE_HEADER"] in header_map
    has_status_header = cfg["PROGRESS_STATUS_HEADER"] in header_map
    if not has_margin_header:
        print(f"'{sheet_name}' 시트: '{cfg['MARGIN_RATE_HEADER']}' 헤더를 찾지 못했습니다.")
    if not has_status_header:
        print(f"'{sheet_name}' 시트: '{cfg['PROGRESS_STATUS_HEADER']}' 헤더를 찾지 못했습니다.")

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
                "업로드중",
            }
            if (api["is_crawler_ready_status"](current_status) and needs_update) or should_backfill_shipping:
                target_rows.append((row_num, url))

    if not target_rows:
        print(f"'{sheet_name}' 시트: 신규 작성 대상이 없습니다.")
        return

    print(f"'{sheet_name}' 시트: {len(target_rows)}개 행을 처리합니다.")

    if make_thumbnails:
        print(f"'{sheet_name}' 시트: 썸네일 자동 생성 모드로 처리합니다.")
        for idx, _url in target_rows:
            print(f"[{sheet_name}] {idx}행 썸네일 생성 중")
            existing_values_for_row = existing_rows_map.get(idx, {})
            folder_path = api["resolve_image_folder_from_paths"](existing_values_for_row.get(cfg["IMAGE_PATHS_COLUMN"], ""))
            brand = api["build_thumbnail_brand"](existing_values_for_row)
            if has_status_header:
                api["update_cell_by_header"](
                    service, sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"], cfg["STATUS_THUMBNAILING"]
                )
            if api["create_thumbnail_for_folder"](folder_path, brand):
                if has_status_header:
                    if api["update_cell_by_header"](
                        service, sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"], cfg["STATUS_THUMBNAILS_DONE"]
                    ):
                        print(f" {sheet_name} {idx}행 상태 업데이트: {cfg['STATUS_THUMBNAILS_DONE']}")
            elif has_status_header:
                if api["update_cell_by_header"](
                    service, sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"], cfg["STATUS_ERROR"]
                ):
                    print(f" {sheet_name} {idx}행 상태 업데이트: {cfg['STATUS_ERROR']}")
            time.sleep(cfg["THUMB_ROW_DELAY_SECONDS"])
        return

    if download_images:
        print(f"'{sheet_name}' 시트: 이미지 저장 모드(N열 기준)로 처리합니다.")
        for idx, url in target_rows:
            print(f"[{sheet_name}] {idx}행 이미지 저장 중: {url}")
            existing_values_for_row = existing_rows_map.get(idx, {})
            sheet_sku = existing_values_for_row.get(cfg["MUSINSA_SKU_COLUMN"], "")
            if has_status_header:
                api["update_cell_by_header"](
                    service, sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"], cfg["STATUS_DOWNLOADING"]
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
            api["write_image_paths_only"](
                service,
                sheet_name,
                idx,
                product_info.get("image_paths", ""),
                existing_values_for_row,
            )
            logo_url = (product_info.get("brand_logo_url") or "").strip()
            if logo_url and product_info.get("image_paths", ""):
                folder_name = api["build_image_folder_name"](idx, product_info.get("product_name_kr", ""))
                api["download_brand_logo"](logo_url, folder_name, product_info.get("image_paths", ""))
            if product_info.get("image_paths", "") and has_status_header:
                if api["update_cell_by_header"](
                    service, sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"], cfg["STATUS_IMAGES_SAVED"]
                ):
                    print(f" {sheet_name} {idx}행 상태 업데이트: {cfg['STATUS_IMAGES_SAVED']}")
            time.sleep(cfg["IMAGE_ROW_DELAY_SECONDS"])
        return

    shipping_table = api["read_shipping_table"](service, sheet_name)
    if not shipping_table:
        print(f"'{sheet_name}' 시트: 배송비 기준표(Z/AA/AB)를 읽지 못해 O열 배송비는 비워집니다.")

    for idx, url in target_rows:
        print(f"[{sheet_name}] {idx}행 처리 중: {url}")
        existing_values_for_row = existing_rows_map.get(idx, {})
        sheet_sku = existing_values_for_row.get(cfg["MUSINSA_SKU_COLUMN"], "")
        if has_status_header:
            api["update_cell_by_header"](
                service, sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"], cfg["STATUS_CRAWLING"]
            )
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
            print(f"    배송비 산출: 추정 {estimated_weight}kg -> KRW {shipping_cost}")
        else:
            print(f"    배송비 산출 실패: 기준표/무게 매칭을 확인하세요 (추정 {estimated_weight}kg)")

        api["write_to_sheet"](service, sheet_name, idx, product_info, existing_rows_map.get(idx, {}))
        if has_status_header:
            dynamic_values = api["get_row_dynamic_values"](
                service,
                sheet_name,
                idx,
                header_map,
                [cfg["MARGIN_RATE_HEADER"], cfg["PROGRESS_STATUS_HEADER"]],
            )
            margin_rate = api["parse_margin_rate"](dynamic_values.get(cfg["MARGIN_RATE_HEADER"], ""))
            current_status = dynamic_values.get(cfg["PROGRESS_STATUS_HEADER"], "")
            next_status = api["determine_progress_status"](margin_rate)

            if next_status != cfg["STATUS_HOLD"]:
                refreshed_values = api["get_existing_row_values"](service, sheet_name, idx)
                if not api["row_needs_update"](refreshed_values, require_image_paths=False):
                    next_status = cfg["STATUS_CRAWLED"]

            if current_status != next_status:
                if api["update_cell_by_header"](
                    service, sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"], next_status
                ):
                    if margin_rate is None:
                        print(f" {sheet_name} {idx}행 상태 업데이트: {next_status} (마진률 미확인)")
                    else:
                        print(f" {sheet_name} {idx}행 상태 업데이트: {next_status} (마진률 {margin_rate:.2f}%)")
        time.sleep(cfg["CRAWLER_ROW_DELAY_SECONDS"])
