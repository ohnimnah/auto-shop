"""Standalone runner for BUYMA category support layer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from browser_service import setup_chrome_driver
from buyma_category_collector import (
    collect_buyma_category_hierarchy_with_stats,
    rows_to_dicts,
)
from buyma_category_repository import (
    load_category_json,
    merge_deduplicated,
    save_category_json,
    save_rows_to_google_sheet,
)
from marketplace.buyma.login import setup_visible_chrome_driver
from marketplace.buyma.selectors import BUYMA_SELL_URL
from marketplace.common import sheet_source as common_sheet_source_mod


def _parse_bool(value: str) -> bool:
    text = (value or "").strip().lower()
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def _load_runtime_sheet_id() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return ""
    cfg_path = os.path.join(local_app_data, "auto_shop", "sheets_config.json")
    if not os.path.exists(cfg_path):
        return ""
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return ""
        return common_sheet_source_mod.extract_spreadsheet_id(cfg.get("spreadsheet_id") or "")
    except Exception:
        return ""


def _safe_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _build_summary(
    rows: List[Dict[str, str]],
    duplicate_skipped_count: int,
    blank_category_id_count: int,
    selector_failure_count: int,
) -> Dict[str, int]:
    parent_set = set()
    middle_set = set()
    child_set = set()
    unique_category_set = set()

    for row in rows:
        parent = (row.get("parent_category") or "").strip()
        middle = (row.get("middle_category") or "").strip()
        child = (row.get("child_category") or "").strip()

        if parent:
            parent_set.add(parent)
        if middle:
            middle_set.add((parent, middle))
        if child:
            child_set.add((parent, middle, child))

        unique_category_set.add((parent, middle, child))

    return {
        "total_collected_rows": len(rows),
        "rows_with_blank_category_id": blank_category_id_count,
        "rows_skipped_as_duplicates": duplicate_skipped_count,
        "selector_failure_warnings": selector_failure_count,
        "unique_category_count": len(unique_category_set),
        "parent_count": len(parent_set),
        "middle_count": len(middle_set),
        "child_count": len(child_set),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect BUYMA category hierarchy into reusable data")
    parser.add_argument("--page-url", default=BUYMA_SELL_URL, help="BUYMA page URL containing category selectors")
    parser.add_argument("--output-json", default="_debug/buyma_categories.json", help="output JSON file path")
    parser.add_argument("--sheet-name", default="buyma_categories_raw", help="Google Sheet tab name to save rows")
    parser.add_argument("--spreadsheet-id", default="", help="Google Spreadsheet ID (optional if runtime config exists)")
    parser.add_argument("--overwrite", type=_parse_bool, default=True, help="true=overwrite, false=append/merge")
    parser.add_argument(
        "--headless",
        type=_parse_bool,
        default=False,
        help="run browser in headless mode (default false for login/session reliability)",
    )
    args = parser.parse_args()

    driver = setup_chrome_driver(headless=True) if args.headless else setup_visible_chrome_driver()
    try:
        driver.get(args.page_url)
        if not args.headless:
            _safe_input("BUYMA 로그인 상태를 확인한 뒤 Enter를 누르세요...")
            if "/login" in (driver.current_url or "").lower():
                print("[warn] 로그인 페이지가 열려 있습니다. 계정 상태에 따라 카테고리 가시성이 제한될 수 있습니다.")

        collected_rows, collect_stats = collect_buyma_category_hierarchy_with_stats(
            driver,
            page_url="",
        )
    finally:
        driver.quit()

    incoming_dicts = rows_to_dicts(collected_rows)
    json_path = os.path.abspath(args.output_json)

    if args.overwrite:
        final_rows = incoming_dicts
    else:
        existing = load_category_json(json_path)
        final_rows = merge_deduplicated(existing, incoming_dicts)
    save_category_json(json_path, final_rows)

    if args.sheet_name:
        spreadsheet_id = (args.spreadsheet_id or "").strip() or _load_runtime_sheet_id()
        if not spreadsheet_id:
            raise RuntimeError("sheet-name is set but spreadsheet-id could not be resolved")
        credentials_path = common_sheet_source_mod.get_credentials_path(ROOT_DIR)
        service = common_sheet_source_mod.get_sheets_service(credentials_path)
        save_rows_to_google_sheet(
            service=service,
            spreadsheet_id=spreadsheet_id,
            sheet_name=args.sheet_name,
            rows=final_rows if args.overwrite else incoming_dicts,
            overwrite=args.overwrite,
        )

    summary = _build_summary(
        incoming_dicts,
        int(collect_stats.get("duplicate_skipped_count", 0)),
        int(collect_stats.get("blank_category_id_count", 0)),
        int(collect_stats.get("selector_failure_count", 0)),
    )
    warnings = [str(x) for x in (collect_stats.get("warnings") or []) if str(x).strip()]

    print("\n=== BUYMA Category Collection Summary ===")
    print(f"total rows: {summary['total_collected_rows']}")
    print(f"rows with blank category_id: {summary['rows_with_blank_category_id']}")
    print(f"rows skipped as duplicates: {summary['rows_skipped_as_duplicates']}")
    print(f"selector failure warnings: {summary['selector_failure_warnings']}")
    print(f"unique category count: {summary['unique_category_count']}")
    print(f"parent count: {summary['parent_count']}")
    print(f"middle count: {summary['middle_count']}")
    print(f"child count: {summary['child_count']}")
    print(f"saved json: {json_path}")
    if args.sheet_name:
        print(f"saved sheet: {args.sheet_name}")

    if warnings:
        print("\nWarnings:")
        for warn in warnings:
            print(f"- {warn}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
