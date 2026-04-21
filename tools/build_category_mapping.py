"""Build manual category_mapping table from buyma_categories_raw and run tests.

This script is standalone and does NOT modify upload behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from buyma_category_repository import load_category_json, save_category_json
from marketplace.common import sheet_source as common_sheet_source_mod
from standard_category_map import (
    build_common_mapping_rows_from_raw,
    mapping_rows_to_sheet_values,
    run_mapping_tests,
)


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


def _save_mapping_to_sheet(
    *,
    spreadsheet_id: str,
    sheet_name: str,
    values: List[List[str]],
    overwrite: bool,
) -> None:
    credentials_path = common_sheet_source_mod.get_credentials_path(ROOT_DIR)
    service = common_sheet_source_mod.get_sheets_service(credentials_path)
    if overwrite:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()
    else:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values[1:]},
        ).execute()


def _default_test_samples() -> List[Dict[str, str]]:
    return [
        {"product_name": "오버핏 후드티", "gender": "women"},
        {"product_name": "기모 맨투맨 스웨트셔츠", "gender": "women"},
        {"product_name": "로고 반팔 티셔츠", "gender": "women"},
        {"product_name": "울 니트 스웨터", "gender": "women"},
        {"product_name": "코튼 파자마 세트", "gender": "women"},
        {"product_name": "zip hoodie", "gender": "men"},
        {"product_name": "crew neck sweatshirt", "gender": "men"},
        {"product_name": "basic tee", "gender": "men"},
        {"product_name": "cable knit", "gender": "men"},
        {"product_name": "sleepwear set", "gender": "men"},
    ]


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoded = text.encode(sys.stdout.encoding or "utf-8", errors="replace")
        print(encoded.decode(sys.stdout.encoding or "utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build category_mapping table and run standalone mapping tests")
    parser.add_argument("--raw-json", default="_debug/buyma_categories.json", help="buyma_categories_raw JSON path")
    parser.add_argument("--output-json", default="_debug/category_mapping.json", help="output mapping JSON path")
    parser.add_argument("--sheet-name", default="category_mapping", help="Google Sheet tab name")
    parser.add_argument("--spreadsheet-id", default="", help="Google Spreadsheet ID")
    parser.add_argument("--save-sheet", type=_parse_bool, default=False, help="save mapping to Google Sheet")
    parser.add_argument("--overwrite", type=_parse_bool, default=True, help="true=overwrite false=append")
    args = parser.parse_args()

    raw_path = os.path.abspath(args.raw_json)
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"raw category json not found: {raw_path}")

    raw_rows = load_category_json(raw_path)
    mapping_rows = build_common_mapping_rows_from_raw(raw_rows)
    mapping_dicts = [row.to_dict() for row in mapping_rows]

    output_json = os.path.abspath(args.output_json)
    save_category_json(output_json, mapping_dicts)

    if args.save_sheet:
        spreadsheet_id = (args.spreadsheet_id or "").strip() or _load_runtime_sheet_id()
        if not spreadsheet_id:
            raise RuntimeError("save-sheet is true but spreadsheet-id could not be resolved")
        values = mapping_rows_to_sheet_values(mapping_rows)
        _save_mapping_to_sheet(
            spreadsheet_id=spreadsheet_id,
            sheet_name=args.sheet_name,
            values=values,
            overwrite=args.overwrite,
        )

    samples = _default_test_samples()
    test_results = run_mapping_tests(mapping_rows, samples)

    found_count = sum(1 for x in test_results if x.get("mapping_found") == "Y")
    _safe_print("\n=== category_mapping build summary ===")
    _safe_print(f"raw rows loaded: {len(raw_rows)}")
    _safe_print(f"mapping rows built: {len(mapping_rows)}")
    _safe_print(f"saved json: {output_json}")
    if args.save_sheet:
        _safe_print(f"saved sheet: {args.sheet_name}")
    _safe_print(f"test samples: {len(test_results)}")
    _safe_print(f"mapping hit: {found_count}/{len(test_results)}")

    _safe_print("\n=== mapping test results ===")
    for i, row in enumerate(test_results, start=1):
        _safe_print(
            f"{i:02d}. [{row['gender']}] {row['product_name']} | "
            f"{row['standard_category']} -> "
            f"{row['buyma_parent']} / {row['buyma_middle']} / {row['buyma_child']} "
            f"(found={row['mapping_found']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
