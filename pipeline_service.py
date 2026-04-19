"""Pipeline/status decision helpers."""

from typing import Dict, List


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
