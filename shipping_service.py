"""Shipping table and estimate helpers."""

import re
import time
from typing import List, Tuple


def read_shipping_table(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    range_a1: str = "Z1:AB60",
) -> List[Tuple[float, int]]:
    """Read weight->shipping-cost table from a sheet range."""

    def _parse_table_rows(rows: List[List[str]]) -> List[Tuple[float, int]]:
        table: List[Tuple[float, int]] = []
        for row in rows:
            if len(row) < 2:
                continue
            weight_raw = (row[0] or "").strip()
            weight_norm = weight_raw.replace("kg", "").replace("KG", "").replace(",", ".").strip()
            try:
                weight = float(weight_norm)
            except ValueError:
                continue

            # Use AA as primary shipping cost, AB as fallback.
            cost_digits = re.sub(r"[^\d]", "", (row[1] or "").strip()) if len(row) > 1 else ""
            if not cost_digits and len(row) > 2:
                cost_digits = re.sub(r"[^\d]", "", (row[2] or "").strip())
            if not cost_digits:
                continue
            table.append((weight, int(cost_digits)))
        table.sort(key=lambda item: item[0])
        return table

    for attempt in (1, 2):
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_name}'!{range_a1}",
            ).execute()
            rows = result.get("values", [])
            table = _parse_table_rows(rows)
            if table:
                return table
            if attempt == 1:
                time.sleep(0.4)
                continue
            return []
        except Exception:
            if attempt == 1:
                time.sleep(0.4)
                continue
            return []
    return []


def estimate_weight(
    product_name: str,
    opt_kind_cd: str,
    keyword_weight_rules,
    opt_kind_weight_map,
    default_weight_kg: float,
) -> float:
    """Estimate product weight by keyword and option kind."""
    name_lower = (product_name or "").lower()
    for keywords, weight in keyword_weight_rules:
        for keyword in keywords:
            if keyword in name_lower:
                return weight
    kind = (opt_kind_cd or "").upper()
    return opt_kind_weight_map.get(kind, default_weight_kg)


def lookup_shipping_cost(table: List[Tuple[float, int]], weight_kg: float) -> str:
    """Return matched shipping cost as comma-formatted KRW string."""
    if not table:
        return ""
    for tier_weight, tier_cost in table:
        if weight_kg <= tier_weight:
            return f"{tier_cost:,}"
    return f"{table[-1][1]:,}"
