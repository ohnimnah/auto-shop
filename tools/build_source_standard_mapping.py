"""Build starter source_to_standard_mapping rows.

Standalone helper: does NOT change upload behavior.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import sys
from typing import Dict, List

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from marketplace.common import sheet_source as common_sheet_source_mod


HEADERS: List[str] = [
    "source_site",
    "source_gender",
    "source_cat_large",
    "source_cat_middle",
    "source_cat_small",
    "title_keywords_include",
    "title_keywords_exclude",
    "standard_category",
    "priority",
    "enabled",
    "updated_at",
    "note",
]


def _parse_bool(value: str) -> bool:
    text = (value or "").strip().lower()
    return text in {"1", "true", "t", "yes", "y", "on"}


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


def _row(
    *,
    source_site: str,
    source_gender: str,
    source_cat_large: str,
    source_cat_middle: str,
    source_cat_small: str,
    include: str,
    standard_category: str,
    priority: int,
    note: str = "",
) -> List[str]:
    now = datetime.now().isoformat(timespec="seconds")
    return [
        source_site,
        source_gender,
        source_cat_large,
        source_cat_middle,
        source_cat_small,
        include,
        "",
        standard_category,
        str(priority),
        "TRUE",
        now,
        note,
    ]


def build_starter_rows() -> List[List[str]]:
    # 요청 우선: 기타로 자주 빠지는 니트/가디건/슬랙스
    rows: List[List[str]] = [
        _row(
            source_site="musinsa",
            source_gender="any",
            source_cat_large="상의",
            source_cat_middle="니트웨어",
            source_cat_small="니트/스웨터",
            include="니트, knit, sweater, 풀오버",
            standard_category="TOP_KNIT",
            priority=10,
            note="starter",
        ),
        _row(
            source_site="musinsa",
            source_gender="any",
            source_cat_large="아우터",
            source_cat_middle="가디건",
            source_cat_small="가디건",
            include="가디건, cardigan",
            standard_category="TOP_CARDIGAN",
            priority=10,
            note="starter",
        ),
        _row(
            source_site="musinsa",
            source_gender="any",
            source_cat_large="하의",
            source_cat_middle="팬츠",
            source_cat_small="슬랙스",
            include="슬랙스, slacks, trousers",
            standard_category="PANTS",
            priority=10,
            note="starter",
        ),
        # 보너스 안정화 샘플
        _row(
            source_site="musinsa",
            source_gender="any",
            source_cat_large="상의",
            source_cat_middle="후드",
            source_cat_small="후드 집업",
            include="후드, 후드집업, hoodie, hooded, zip hoodie",
            standard_category="TOP_HOODIE",
            priority=20,
            note="starter",
        ),
    ]
    return rows


def _safe_sheet_name(name: str) -> str:
    return (name or "").replace("'", "''")


def _ensure_sheet(service, spreadsheet_id: str, sheet_name: str) -> None:
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))",
    ).execute()
    titles = [((s.get("properties", {}) or {}).get("title") or "").strip() for s in meta.get("sheets", [])]
    if sheet_name not in titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        ).execute()


def _write_sheet(
    *,
    spreadsheet_id: str,
    sheet_name: str,
    rows: List[List[str]],
    overwrite: bool,
) -> None:
    credentials_path = common_sheet_source_mod.get_credentials_path(ROOT_DIR)
    service = common_sheet_source_mod.get_sheets_service(credentials_path)
    _ensure_sheet(service, spreadsheet_id, sheet_name)

    safe_name = _safe_sheet_name(sheet_name)
    if overwrite:
        values = [HEADERS] + rows
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{safe_name}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()
    else:
        # Header 보장
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{safe_name}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [HEADERS]},
        ).execute()
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{safe_name}'!A2",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build starter source_to_standard_mapping rows")
    parser.add_argument("--sheet-name", default="source_to_standard_mapping", help="target mapping tab name")
    parser.add_argument("--spreadsheet-id", default="", help="Google Spreadsheet ID (optional)")
    parser.add_argument("--save-sheet", type=_parse_bool, default=True, help="save rows to Google Sheet")
    parser.add_argument("--overwrite", type=_parse_bool, default=False, help="true=replace tab contents")
    parser.add_argument("--print-only", action="store_true", help="print rows only")
    args = parser.parse_args()

    rows = build_starter_rows()
    print("=== source_to_standard_mapping starter rows ===")
    print(f"rows: {len(rows)}")
    for i, row in enumerate(rows, start=1):
        print(f"{i:02d}. {row[7]} <- {row[5]}")

    if args.print_only:
        return 0

    if args.save_sheet:
        spreadsheet_id = (args.spreadsheet_id or "").strip() or _load_runtime_sheet_id()
        if not spreadsheet_id:
            raise RuntimeError("spreadsheet-id could not be resolved")
        _write_sheet(
            spreadsheet_id=spreadsheet_id,
            sheet_name=args.sheet_name,
            rows=rows,
            overwrite=args.overwrite,
        )
        print(f"saved sheet: {args.sheet_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

