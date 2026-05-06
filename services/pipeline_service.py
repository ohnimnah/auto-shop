"""Pipeline/status decision helpers."""

import time
from dataclasses import dataclass
from typing import Any, Dict, List

from constants.status import STATUS_UPLOADING
from models.product_model import product_from_sheet_row, product_to_sheet_field_map
from utils.logger import get_logger


LOGGER = get_logger("auto_shop.pipeline")


@dataclass(frozen=True)
class WatchPolicy:
    """Operational rules for foreground watch and team watch workers.

    Single watch allows one foreground process. Team watch ignores duplicate
    starts while a worker is alive, restarts only after the worker exits, and
    pauses after repeated non-zero exits.
    """

    max_failures_before_pause: int = 3

    def should_count_failure(self, return_code: int, enabled: bool) -> bool:
        return enabled and return_code != 0

    def should_pause_after_failure(self, failure_count: int) -> bool:
        return failure_count >= self.max_failures_before_pause


class LauncherPipelineService:
    """Pipeline decisions for the launcher control panel.

    ActionRunner calls this service for stage mapping so orchestration stays
    separate from UI labels and subprocess log parsing rules.
    """

    team_watch_actions = {
        "assets": "watch-images",
        "design": "watch-thumbnails",
        "sales": "watch-upload",
    }

    def __init__(self, watch_policy: WatchPolicy | None = None) -> None:
        self.watch_policy = watch_policy or WatchPolicy()

    def stage_for_action(self, action: str) -> str:
        if action in {"run", "watch", "collect-listings"}:
            return "scout"
        if action in {"save-images", "watch-images"}:
            return "assets"
        if action in {"thumbnail-create", "watch-thumbnails"}:
            return "design"
        if action in {"upload-review", "upload-auto", "watch-upload"}:
            return "sales"
        return ""

    def stage_from_log(self, message: str) -> str:
        text = (message or "").lower()
        if not text:
            return ""
        if "main.py" in text and "--download-images" in text:
            return "assets"
        if "main.py" in text and "--make-thumbnails" in text:
            return "design"
        if "make_thumbnails.py" in text:
            return "design"
        if "buyma_upload.py" in text:
            return "sales"
        return ""

    def team_done_status(self, enabled: bool) -> str:
        return "감시중" if enabled else "대기"


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
    buyma_meta_column: str,
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
        (buyma_meta_column, product_map.get("buyma_meta", "")),
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


def row_crawl_outputs_complete(
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
    buyma_meta_column: str,
    shipping_cost_column: str,
) -> bool:
    """Return True when one crawl pass has finished, including a BUYMA attempt."""
    required_columns = [
        brand_column,
        brand_en_column,
        product_name_kr_column,
        musinsa_sku_column,
        color_kr_column,
        size_column,
        actual_size_column,
        price_column,
        shipping_cost_column,
    ]
    for column in required_columns:
        if is_empty_cell(existing_values.get(column, "")):
            return False
    return not is_empty_cell(existing_values.get(buyma_sell_price_column, "")) or not is_empty_cell(
        existing_values.get(buyma_meta_column, "")
    )


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
        "product_name_jp": str(cfg.get("PRODUCT_NAME_JP_COLUMN", "") or ""),
        "product_name_en": str(cfg.get("PRODUCT_NAME_EN_COLUMN", "") or ""),
        "musinsa_sku": str(cfg.get("MUSINSA_SKU_COLUMN", "") or ""),
        "color_kr": str(cfg.get("COLOR_KR_COLUMN", "") or ""),
        "size": str(cfg.get("SIZE_COLUMN", "") or ""),
        "actual_size": str(cfg.get("ACTUAL_SIZE_COLUMN", "") or ""),
        "price": str(cfg.get("PRICE_COLUMN", "") or ""),
        "buyma_price": str(cfg.get("BUYMA_SELL_PRICE_COLUMN", "") or ""),
        "buyma_meta": str(cfg.get("BUYMA_META_COLUMN", "") or ""),
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
    print(f"'{sheet_name}' 시트에서 B열 링크를 읽는 중...")
    rows = api["read_urls_from_sheet"](service, sheet_name)
    if not rows:
        print(f"'{sheet_name}' 시트 B열에 처리할 URL이 없습니다.")
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
                cfg["STATUS_CRAWLED"],
                cfg["STATUS_COMPLETED"],
                cfg["STATUS_UPLOAD_READY"],
                STATUS_UPLOADING,
            }
            if (api["is_crawler_ready_status"](current_status) and needs_update) or should_backfill_shipping:
                target_rows.append((row_num, url))

    if not target_rows:
        print(f"'{sheet_name}' 시트: 신규 작성 대상이 없습니다.")
        return

    print(f"'{sheet_name}' 시트: {len(target_rows)}개 행을 처리합니다.")

    updates_buffer: List[Dict[str, object]] = []
    flush_size = int(cfg.get("BATCH_FLUSH_SIZE", 60))
    sheet_product_columns = _sheet_product_column_map(cfg)

    if make_thumbnails:
        print(f"'{sheet_name}' thumbnail mode start")
        for idx, _url in target_rows:
            print(f"[{sheet_name}] row {idx} thumbnail processing")
            LOGGER.info("[START] SKU=- ROW=%s", idx)
            LOGGER.info("[THUMBNAIL START] ROW=%s", idx)
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
                    LOGGER.info("[THUMBNAIL DONE] ROW=%s", idx)
                    LOGGER.info("[DONE] ROW=%s", idx)
            elif has_status_header:
                _enqueue_update(
                    updates_buffer,
                    _build_header_cell_range(sheet_name, idx, header_map, cfg["PROGRESS_STATUS_HEADER"]),
                    cfg["STATUS_ERROR"],
                )
                print(f" {sheet_name} row {idx} status -> {cfg['STATUS_ERROR']}")
                LOGGER.error("[ERROR] SKU=- ROW=%s - thumbnail failed", idx)
            if len(updates_buffer) >= flush_size:
                _flush_updates_buffer(service, api, updates_buffer, f"thumbnail-row-{idx}")
            time.sleep(cfg["THUMB_ROW_DELAY_SECONDS"])
        _flush_updates_buffer(service, api, updates_buffer, "thumbnail-final")
        LOGGER.info("[DONE] sheet=%s mode=thumbnail total_rows=%s", sheet_name, len(target_rows))
        return

    if download_images:
        print(f"'{sheet_name}' image download mode start")
        for idx, url in target_rows:
            print(f"[{sheet_name}] row {idx} image processing: {url}")
            existing_values_for_row = existing_rows_map.get(idx, {})
            existing_product_for_row = product_from_sheet_row(existing_values_for_row, sheet_product_columns)
            sheet_sku = existing_product_for_row.musinsa_sku
            sheet_product_name_jp = existing_product_for_row.product_name_jp
            sheet_product_name_en = existing_product_for_row.product_name_en
            sheet_brand_en = existing_product_for_row.brand_en
            LOGGER.info("[START] SKU=%s ROW=%s", sheet_sku or "-", idx)
            LOGGER.info("[IMAGE START] SKU=%s ROW=%s", sheet_sku or "-", idx)
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
                existing_product_name_jp=sheet_product_name_jp,
                existing_product_name_en=sheet_product_name_en,
                existing_brand_en=sheet_brand_en,
                download_images=True,
                images_only=True,
            )
            product_info = _product_to_dict(product)

            image_paths = product_info.get("image_paths", "")
            if is_empty_cell(image_paths):
                print(f" {sheet_name} row {idx}: skip {cfg['IMAGE_PATHS_COLUMN']} update (empty image paths)")
            elif not is_empty_cell(existing_values_for_row.get(cfg["IMAGE_PATHS_COLUMN"], "")):
                print(f" {sheet_name} row {idx}: skip {cfg['IMAGE_PATHS_COLUMN']} update (already filled)")
            else:
                _enqueue_update(
                    updates_buffer,
                    f"'{sheet_name}'!{cfg['IMAGE_PATHS_COLUMN']}{idx}",
                    image_paths,
                )
                print(f" {sheet_name} row {idx}: queue {cfg['IMAGE_PATHS_COLUMN']}(image_paths) update")

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
                LOGGER.info("[IMAGE DONE] SKU=%s ROW=%s", sheet_sku or "-", idx)
                LOGGER.info("[DONE] SKU=%s ROW=%s", sheet_sku or "-", idx)
            if len(updates_buffer) >= flush_size:
                _flush_updates_buffer(service, api, updates_buffer, f"image-row-{idx}")
            time.sleep(cfg["IMAGE_ROW_DELAY_SECONDS"])
        _flush_updates_buffer(service, api, updates_buffer, "image-final")
        LOGGER.info("[DONE] sheet=%s mode=image total_rows=%s", sheet_name, len(target_rows))
        return

    shipping_table = api["read_shipping_table"](service, sheet_name)
    if not shipping_table:
        print(f"'{sheet_name}' 배송표 없음: Z/AA/AB 기준 배송비 계산을 건너뜁니다.")

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
            if not api["row_needs_update"](refreshed_values, require_image_paths=False) or api[
                "row_crawl_outputs_complete"
            ](
                refreshed_values,
                cfg["BRAND_COLUMN"],
                cfg["BRAND_EN_COLUMN"],
                cfg["PRODUCT_NAME_KR_COLUMN"],
                cfg["MUSINSA_SKU_COLUMN"],
                cfg["COLOR_KR_COLUMN"],
                cfg["SIZE_COLUMN"],
                cfg["ACTUAL_SIZE_COLUMN"],
                cfg["PRICE_COLUMN"],
                cfg["BUYMA_SELL_PRICE_COLUMN"],
                cfg["BUYMA_META_COLUMN"],
                cfg["SHIPPING_COST_COLUMN"],
            ):
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
                print(f" {sheet_name} {row_num}행 진행상태: {next_status} (마진률 없음)")
            else:
                print(f" {sheet_name} {row_num}행 진행상태: {next_status} (마진률 {margin_rate:.2f}%)")

    try:
        for idx, url in target_rows:
            print(f"[{sheet_name}] {idx}행 처리: {url}")
            existing_values_for_row = existing_rows_map.get(idx, {})
            existing_product_for_row = product_from_sheet_row(existing_values_for_row, sheet_product_columns)
            sheet_sku = existing_product_for_row.musinsa_sku
            LOGGER.info("[START] SKU=%s ROW=%s", sheet_sku or "-", idx)
            if has_status_header:
                api["update_cell_by_header"](
                    service,
                    sheet_name,
                    idx,
                    header_map,
                    cfg["PROGRESS_STATUS_HEADER"],
                    cfg["STATUS_CRAWLING"],
                )

            product = None
            try:
                LOGGER.info("[CRAWL START] SKU=%s ROW=%s", sheet_sku or "-", idx)
                product = api["scrape_musinsa_product"](
                    driver,
                    url,
                    idx,
                    existing_sku=sheet_sku,
                    existing_product_name_jp=existing_product_for_row.product_name_jp,
                    existing_product_name_en=existing_product_for_row.product_name_en,
                    existing_brand_en=existing_product_for_row.brand_en,
                    download_images=download_images,
                    fetch_buyma=False,
                )
                product_info = _product_to_dict(product)
                estimated_weight = api["estimate_weight"](
                    product_info.get("product_name_kr", ""),
                    product_info.get("opt_kind_cd", ""),
                )
                shipping_cost = api["lookup_shipping_cost"](shipping_table, estimated_weight)
                if shipping_cost:
                    product_info["shipping_cost"] = shipping_cost
                    print(f"    배송비 계산: 예상 {estimated_weight}kg -> KRW {shipping_cost}")
                else:
                    print(f"    배송비 계산 실패: 배송표에서 구간을 찾지 못했습니다 (예상 {estimated_weight}kg)")

                row_updates = api["write_to_sheet"](
                    service,
                    sheet_name,
                    idx,
                    product_info,
                    existing_rows_map.get(idx, {}),
                    return_updates_only=True,
                )
                if row_updates:
                    print(f"[batch][row] base payload prepared row={idx} cells={len(row_updates)}")
                    api["batch_update_values"](service, row_updates)
                    time.sleep(1.0)

                refreshed_values_for_buyma = api["get_existing_row_values"](service, sheet_name, idx)
                refreshed_product_for_buyma = product_from_sheet_row(
                    refreshed_values_for_buyma,
                    sheet_product_columns,
                )
                buyma_price_existing = refreshed_values_for_buyma.get(cfg["BUYMA_SELL_PRICE_COLUMN"], "")
                if api["is_empty_cell"](buyma_price_existing) and api.get("fetch_buyma_lowest_price"):
                    buyma_search_brand = (
                        refreshed_product_for_buyma.brand_en
                        or product_info.get("brand_en", "")
                        or refreshed_product_for_buyma.brand
                        or product_info.get("brand", "")
                    )
                    buyma_result = api["fetch_buyma_lowest_price"](
                        driver,
                        product_info.get("product_name_kr", ""),
                        buyma_search_brand,
                        product_info.get("musinsa_sku", ""),
                        refreshed_product_for_buyma.product_name_jp,
                        product_info.get("price", ""),
                        refreshed_product_for_buyma.product_name_en,
                    )
                    buyma_updates: List[Dict[str, object]] = []
                    buyma_price = str(buyma_result.get("buyma_price") or "") if isinstance(buyma_result, dict) else str(buyma_result or "")
                    buyma_meta = str(buyma_result.get("buyma_meta") or "") if isinstance(buyma_result, dict) else ""
                    if buyma_price:
                        buyma_updates.append(
                            {
                                "range": f"'{sheet_name}'!{cfg['BUYMA_SELL_PRICE_COLUMN']}{idx}",
                                "values": [[buyma_price]],
                            }
                        )
                    if buyma_meta and api["is_empty_cell"](refreshed_values_for_buyma.get(cfg["BUYMA_META_COLUMN"], "")):
                        buyma_updates.append(
                            {
                                "range": f"'{sheet_name}'!{cfg['BUYMA_META_COLUMN']}{idx}",
                                "values": [[buyma_meta]],
                            }
                        )
                if buyma_updates:
                    print(f"[batch][row] buyma payload prepared row={idx} cells={len(buyma_updates)}")
                    api["batch_update_values"](service, buyma_updates)
                _write_status_for_row(idx)
                LOGGER.info("[CRAWL DONE] SKU=%s ROW=%s", sheet_sku or "-", idx)
            except Exception as row_exc:
                print(f" {sheet_name} {idx}행 처리 오류: {row_exc}")
                if product is not None:
                    try:
                        product.error_message = str(row_exc)
                    except Exception:
                        pass
                LOGGER.error("[ERROR] SKU=%s ROW=%s - %s", sheet_sku or "-", idx, row_exc)
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
            time.sleep(cfg["CRAWLER_ROW_DELAY_SECONDS"])
    finally:
        LOGGER.info("[DONE] sheet=%s mode=crawl total_rows=%s", sheet_name, len(target_rows))
