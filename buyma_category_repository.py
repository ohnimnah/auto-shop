"""Repository helpers for BUYMA category collection data."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from typing import Dict, Iterable, List, Set, Tuple

from buyma_category_collector import BuymaCategoryRow


DEFAULT_HEADERS = [
    "parent_category",
    "middle_category",
    "child_category",
    "category_url",
    "category_id",
    "raw_text",
    "collected_at",
]


def _row_key(raw: Dict[str, str]) -> Tuple[str, str, str, str, str]:
    return (
        (raw.get("parent_category") or "").strip(),
        (raw.get("middle_category") or "").strip(),
        (raw.get("child_category") or "").strip(),
        (raw.get("category_url") or "").strip(),
        (raw.get("category_id") or "").strip(),
    )


def load_category_json(path: str) -> List[Dict[str, str]]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    out: List[Dict[str, str]] = []
    for row in data:
        if isinstance(row, dict):
            out.append({k: str(v) if v is not None else "" for k, v in row.items()})
    return out


def save_category_json(path: str, rows: Iterable[Dict[str, str]]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    data = list(rows)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def merge_deduplicated(existing: Iterable[Dict[str, str]], incoming: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()
    for row in list(existing) + list(incoming):
        key = _row_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def rows_from_dataclass(rows: Iterable[BuymaCategoryRow]) -> List[Dict[str, str]]:
    return [asdict(row) for row in rows]


def save_rows_to_google_sheet(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    rows: Iterable[Dict[str, str]],
    *,
    overwrite: bool = True,
) -> None:
    values = [DEFAULT_HEADERS]
    for row in rows:
        values.append([str(row.get(h, "") or "") for h in DEFAULT_HEADERS])

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

