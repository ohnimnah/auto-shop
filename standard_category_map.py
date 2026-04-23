"""Runtime StandardCategory -> BUYMA mapping table support.

The upload flow resolves StandardCategory through this module. Runtime mapping
rows are loaded once in this priority order:

1. Google Sheet tab `category_mapping`
2. local `_debug/category_mapping.json`
3. built-in default mapping rows
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import json
import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from marketplace.buyma.standard_category import (
    PARENT_MEN,
    PARENT_WOMEN,
    STANDARD_CATEGORY_SPECS,
    StandardCategory,
    get_buyma_parent_category,
    normalize_standard_category,
    resolve_standard_category,
    validate_buyma_category_path,
)


# BUYMA labels (use unicode escapes to avoid terminal/font encoding issues)

MIDDLE_TOPS = "\u30c8\u30c3\u30d7\u30b9"
MIDDLE_INNER_ROOM = "\u30a4\u30f3\u30ca\u30fc\u30fb\u30eb\u30fc\u30e0\u30a6\u30a7\u30a2"
MIDDLE_OUTER_WOMEN = "\u30a2\u30a6\u30bf\u30fc"
MIDDLE_OUTER_MEN = "\u30a2\u30a6\u30bf\u30fc\u30fb\u30b8\u30e3\u30b1\u30c3\u30c8"
MIDDLE_BOTTOMS_WOMEN = "\u30dc\u30c8\u30e0\u30b9"
MIDDLE_BOTTOMS_MEN = "\u30d1\u30f3\u30c4\u30fb\u30dc\u30c8\u30e0\u30b9"
MIDDLE_SHOES_WOMEN = "\u9774\u30fb\u30b7\u30e5\u30fc\u30ba"
MIDDLE_SHOES_MEN = "\u9774\u30fb\u30d6\u30fc\u30c4\u30fb\u30b5\u30f3\u30c0\u30eb"
MIDDLE_DRESS_WOMEN = "\u30ef\u30f3\u30d4\u30fc\u30b9\u30fb\u30aa\u30fc\u30eb\u30a4\u30f3\u30ef\u30f3"
MIDDLE_OTHER_FASHION_MEN = "\u305d\u306e\u4ed6\u30d5\u30a1\u30c3\u30b7\u30e7\u30f3"

CHILD_HOODIE = "\u30d1\u30fc\u30ab\u30fc\u30fb\u30d5\u30fc\u30c7\u30a3"
CHILD_SWEAT = "\u30b9\u30a6\u30a7\u30c3\u30c8\u30fb\u30c8\u30ec\u30fc\u30ca\u30fc"
CHILD_TSHIRT = "T\u30b7\u30e3\u30c4\u30fb\u30ab\u30c3\u30c8\u30bd\u30fc"
CHILD_KNIT = "\u30cb\u30c3\u30c8\u30fb\u30bb\u30fc\u30bf\u30fc"
CHILD_PAJAMA = "\u30eb\u30fc\u30e0\u30a6\u30a7\u30a2\u30fb\u30d1\u30b8\u30e3\u30de"
CHILD_SHIRT = "\u30b7\u30e3\u30c4"
CHILD_CARDIGAN = "\u30ab\u30fc\u30c7\u30a3\u30ac\u30f3"
CHILD_OUTER_JACKET = "\u30b8\u30e3\u30b1\u30c3\u30c8"
CHILD_PANTS = "\u30d1\u30f3\u30c4"
CHILD_SNEAKER = "\u30b9\u30cb\u30fc\u30ab\u30fc"
CHILD_DRESS = ""


MAPPING_HEADERS: List[str] = [
    "standard_category",
    "gender",
    "buyma_parent_category",
    "buyma_middle_category",
    "buyma_child_category",
    "category_url",
    "category_id",
    "source",
    "note",
    "updated_at",
]

CATEGORY_MAPPING_SHEET_NAME = "category_mapping"
_RUNTIME_MAPPING_CACHE: Optional[Tuple[List["CategoryMappingRow"], str]] = None
_RUNTIME_MAPPING_LOGGED_SOURCE = ""


@dataclass(frozen=True)
class CategoryMappingRow:
    standard_category: str
    gender: str
    buyma_parent_category: str
    buyma_middle_category: str
    buyma_child_category: str
    category_url: str
    category_id: str
    source: str
    note: str
    updated_at: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(v: str) -> str:
    return (v or "").strip()


def _contains(text: str, keywords: Sequence[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def normalize_gender(value: str) -> str:
    text = (value or "").strip().lower()
    if text in {"women", "woman", "female", "f", "w", "\uc5ec\uc131", "\ub808\ub514\uc2a4"}:
        return "women"
    if text in {"men", "man", "male", "m", "\ub0a8\uc131", "\uba58\uc988"}:
        return "men"
    return "women"


def resolve_standard_category_for_test(
    product_name: str,
    musinsa_large: str = "",
    musinsa_middle: str = "",
    musinsa_small: str = "",
) -> StandardCategory:
    """Small standalone resolver for mapping-table tests."""
    std, _combined = resolve_standard_category(musinsa_large, musinsa_middle, musinsa_small, product_name)
    return std


def _find_raw_category_row(
    raw_rows: Iterable[Dict[str, str]],
    *,
    parent: str,
    middle: str,
    child: str,
) -> Optional[Dict[str, str]]:
    for row in raw_rows:
        if (
            _norm(row.get("parent_category", "")) == parent
            and _norm(row.get("middle_category", "")) == middle
            and _norm(row.get("child_category", "")) == child
        ):
            return row
    return None


def build_common_mapping_rows_from_raw(raw_rows: Iterable[Dict[str, str]]) -> List[CategoryMappingRow]:
    """Build mapping rows for common categories and both genders."""
    out: List[CategoryMappingRow] = []
    now = _now_iso()
    for gender, parent in (("women", PARENT_WOMEN), ("men", PARENT_MEN)):
        is_mens = gender == "men"
        for std_cat, spec in STANDARD_CATEGORY_SPECS.items():
            middle = spec.middle(is_mens=is_mens)
            child = spec.child
            hit = _find_raw_category_row(raw_rows, parent=parent, middle=middle, child=child)
            out.append(
                CategoryMappingRow(
                    standard_category=std_cat.value,
                    gender=gender,
                    buyma_parent_category=parent,
                    buyma_middle_category=middle,
                    buyma_child_category=child,
                    category_url=_norm((hit or {}).get("category_url", "")),
                    category_id=_norm((hit or {}).get("category_id", "")),
                    source="buyma_categories_raw",
                    note="" if hit else "NOT_FOUND_IN_RAW",
                    updated_at=now,
                )
            )
    return out


def resolve_buyma_category_from_mapping(
    mapping_rows: Iterable[CategoryMappingRow],
    *,
    standard_category: StandardCategory,
    gender: str,
) -> Optional[CategoryMappingRow]:
    g = normalize_gender(gender)
    for row in mapping_rows:
        if row.standard_category == standard_category.value and row.gender == g:
            return row
    return None


def run_mapping_tests(
    mapping_rows: Iterable[CategoryMappingRow],
    samples: Iterable[Dict[str, str]],
) -> List[Dict[str, str]]:
    rows = list(mapping_rows)
    results: List[Dict[str, str]] = []
    for sample in samples:
        name = sample.get("product_name", "") or ""
        musinsa_large = sample.get("musinsa_large", "") or ""
        musinsa_middle = sample.get("musinsa_middle", "") or ""
        musinsa_small = sample.get("musinsa_small", "") or ""
        gender = normalize_gender(sample.get("gender", "women"))
        std = resolve_standard_category_for_test(
            name,
            musinsa_large=musinsa_large,
            musinsa_middle=musinsa_middle,
            musinsa_small=musinsa_small,
        )
        match = resolve_buyma_category_from_mapping(rows, standard_category=std, gender=gender)
        results.append(
            {
                "product_name": name,
                "gender": gender,
                "standard_category": std.value,
                "buyma_parent": match.buyma_parent_category if match else "",
                "buyma_middle": match.buyma_middle_category if match else "",
                "buyma_child": match.buyma_child_category if match else "",
                "mapping_found": "Y" if match else "N",
            }
        )
    return results


def mapping_rows_to_sheet_values(rows: Iterable[CategoryMappingRow]) -> List[List[str]]:
    out = [MAPPING_HEADERS]
    for row in rows:
        d = row.to_dict()
        out.append([str(d.get(h, "") or "") for h in MAPPING_HEADERS])
    return out


def build_default_mapping_rows() -> List[CategoryMappingRow]:
    """Return the default StandardCategory mapping set for both genders."""
    now = _now_iso()
    rows: List[CategoryMappingRow] = []
    for gender, parent in (("women", PARENT_WOMEN), ("men", PARENT_MEN)):
        is_mens = gender == "men"
        for std_cat, spec in STANDARD_CATEGORY_SPECS.items():
            rows.append(
                CategoryMappingRow(
                    std_cat.value,
                    gender,
                    parent,
                    spec.middle(is_mens=is_mens),
                    spec.child,
                    "",
                    "",
                    "default",
                    "",
                    now,
                )
            )
    return rows


def load_mapping_rows_from_json(path: str) -> List[CategoryMappingRow]:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        out: List[CategoryMappingRow] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            out.append(
                CategoryMappingRow(
                    standard_category=str(item.get("standard_category", "") or ""),
                    gender=normalize_gender(str(item.get("gender", "") or "")),
                    buyma_parent_category=str(item.get("buyma_parent_category", "") or ""),
                    buyma_middle_category=str(item.get("buyma_middle_category", "") or ""),
                    buyma_child_category=str(item.get("buyma_child_category", "") or ""),
                    category_url=str(item.get("category_url", "") or ""),
                    category_id=str(item.get("category_id", "") or ""),
                    source=str(item.get("source", "") or "json"),
                    note=str(item.get("note", "") or ""),
                    updated_at=str(item.get("updated_at", "") or ""),
                )
            )
        return out
    except Exception:
        return []


def _safe_log(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = "utf-8"
        print((message or "").encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _log_mapping_source(source: str, count: int, detail: str = "") -> None:
    global _RUNTIME_MAPPING_LOGGED_SOURCE
    if _RUNTIME_MAPPING_LOGGED_SOURCE == source:
        return
    _RUNTIME_MAPPING_LOGGED_SOURCE = source
    suffix = f" ({detail})" if detail else ""
    _safe_log(f"  [category][mapping] mapping_source={source} rows={count}{suffix}")


def reset_runtime_mapping_cache() -> None:
    """Clear runtime mapping cache. Intended for tests and explicit reload tools."""
    global _RUNTIME_MAPPING_CACHE, _RUNTIME_MAPPING_LOGGED_SOURCE
    _RUNTIME_MAPPING_CACHE = None
    _RUNTIME_MAPPING_LOGGED_SOURCE = ""


def _mapping_row_from_dict(item: Dict[str, str], *, source: str) -> CategoryMappingRow:
    return CategoryMappingRow(
        standard_category=str(item.get("standard_category", "") or "").strip(),
        gender=normalize_gender(str(item.get("gender", "") or "")),
        buyma_parent_category=str(item.get("buyma_parent_category", "") or "").strip(),
        buyma_middle_category=str(item.get("buyma_middle_category", "") or "").strip(),
        buyma_child_category=str(item.get("buyma_child_category", "") or "").strip(),
        category_url=str(item.get("category_url", "") or "").strip(),
        category_id=str(item.get("category_id", "") or "").strip(),
        source=str(item.get("source", "") or source).strip() or source,
        note=str(item.get("note", "") or "").strip(),
        updated_at=str(item.get("updated_at", "") or "").strip(),
    )


def _is_valid_mapping_row(row: CategoryMappingRow) -> bool:
    if not row.standard_category:
        return False
    try:
        category = normalize_standard_category(row.standard_category)
    except Exception:
        return False
    if category == StandardCategory.ETC:
        return False
    return validate_buyma_category_path(
        row.buyma_parent_category,
        row.buyma_middle_category,
        row.buyma_child_category,
    )


def _filter_valid_mapping_rows(rows: Iterable[CategoryMappingRow]) -> List[CategoryMappingRow]:
    valid: List[CategoryMappingRow] = []
    for row in rows:
        if _is_valid_mapping_row(row):
            valid.append(
                CategoryMappingRow(
                    standard_category=normalize_standard_category(row.standard_category).value,
                    gender=normalize_gender(row.gender),
                    buyma_parent_category=row.buyma_parent_category,
                    buyma_middle_category=row.buyma_middle_category,
                    buyma_child_category=row.buyma_child_category,
                    category_url=row.category_url,
                    category_id=row.category_id,
                    source=row.source,
                    note=row.note,
                    updated_at=row.updated_at,
                )
            )
    return valid


def _load_sheet_runtime_config() -> Tuple[str, str]:
    try:
        from marketplace.common.runtime import get_runtime_data_dir
        from marketplace.common.sheet_source import extract_spreadsheet_id

        cfg_path = os.path.join(get_runtime_data_dir(), "sheets_config.json")
        if not os.path.exists(cfg_path):
            return "", CATEGORY_MAPPING_SHEET_NAME
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return "", CATEGORY_MAPPING_SHEET_NAME
        spreadsheet_id = extract_spreadsheet_id(str(cfg.get("spreadsheet_id") or ""))
        mapping_sheet_name = str(cfg.get("category_mapping_sheet_name") or CATEGORY_MAPPING_SHEET_NAME).strip()
        return spreadsheet_id, mapping_sheet_name or CATEGORY_MAPPING_SHEET_NAME
    except Exception:
        return "", CATEGORY_MAPPING_SHEET_NAME


def _read_google_sheet_values(spreadsheet_id: str, sheet_name: str) -> List[List[str]]:
    if not spreadsheet_id:
        return []
    try:
        from marketplace.common.sheet_source import get_credentials_path, get_sheets_service

        here = os.path.dirname(os.path.abspath(__file__))
        credentials_path = get_credentials_path(here)
        service = get_sheets_service(credentials_path)
        last_col = chr(ord("A") + len(MAPPING_HEADERS) - 1)
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1:{last_col}5000",
        ).execute()
        return result.get("values", []) or []
    except Exception as exc:
        _safe_log(f"  [category][mapping] google_sheet load failed: {exc}")
        return []


def load_mapping_rows_from_google_sheet() -> List[CategoryMappingRow]:
    """Load validator-passing rows from Google Sheet tab `category_mapping`."""
    spreadsheet_id, sheet_name = _load_sheet_runtime_config()
    values = _read_google_sheet_values(spreadsheet_id, sheet_name)
    if not values:
        return []

    raw_header = [str(v or "").strip() for v in values[0]]
    header_index = {name: idx for idx, name in enumerate(raw_header) if name}
    if "standard_category" not in header_index:
        return []

    rows: List[CategoryMappingRow] = []
    for raw in values[1:]:
        record: Dict[str, str] = {}
        for header in MAPPING_HEADERS:
            idx = header_index.get(header)
            record[header] = str(raw[idx]).strip() if idx is not None and idx < len(raw) else ""
        rows.append(_mapping_row_from_dict(record, source="google_sheet"))
    return _filter_valid_mapping_rows(rows)


def _merge_with_defaults(rows: List[CategoryMappingRow]) -> List[CategoryMappingRow]:
    defaults = build_default_mapping_rows()
    if not rows:
        return defaults
    by_key = {(row.standard_category, row.gender): row for row in defaults}
    by_key.update({(row.standard_category, row.gender): row for row in rows if row.standard_category})
    return list(by_key.values())


def get_runtime_mapping_source() -> str:
    """Return the cached runtime mapping source label."""
    if _RUNTIME_MAPPING_CACHE is None:
        get_runtime_mapping_rows()
    return _RUNTIME_MAPPING_CACHE[1] if _RUNTIME_MAPPING_CACHE else "default"


def get_runtime_mapping_rows() -> List[CategoryMappingRow]:
    """Load mapping once from Google Sheet, local JSON, then defaults."""
    global _RUNTIME_MAPPING_CACHE
    if _RUNTIME_MAPPING_CACHE is not None:
        return list(_RUNTIME_MAPPING_CACHE[0])

    sheet_rows = _filter_valid_mapping_rows(load_mapping_rows_from_google_sheet())
    if sheet_rows:
        rows = _merge_with_defaults(sheet_rows)
        _RUNTIME_MAPPING_CACHE = (rows, "google_sheet")
        _log_mapping_source("google_sheet", len(sheet_rows), "validator-passing sheet rows")
        return list(rows)

    here = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(here, "_debug", "category_mapping.json")
    local_rows = _filter_valid_mapping_rows(load_mapping_rows_from_json(json_path))
    if local_rows:
        rows = _merge_with_defaults(local_rows)
        _RUNTIME_MAPPING_CACHE = (rows, "local_json")
        _log_mapping_source("local_json", len(local_rows), "_debug/category_mapping.json")
        return list(rows)

    rows = build_default_mapping_rows()
    _RUNTIME_MAPPING_CACHE = (rows, "default")
    _log_mapping_source("default", len(rows))
    return list(rows)


def resolve_standard_category_buyma_target(
    standard_category: StandardCategory,
    *,
    is_mens: bool,
    combined_text: str = "",
) -> Tuple[str, str, str]:
    """Resolve BUYMA target from StandardCategory mapping table.

    Returns (parent, middle, child). Empty values mean not matched.
    """
    gender = "men" if is_mens else "women"
    standard_category = normalize_standard_category(standard_category)
    rows = get_runtime_mapping_rows()
    match = resolve_buyma_category_from_mapping(
        rows,
        standard_category=standard_category,
        gender=gender,
    )
    if not match:
        return "", "", ""
    if not validate_buyma_category_path(
        match.buyma_parent_category,
        match.buyma_middle_category,
        match.buyma_child_category,
    ):
        return "", "", ""
    return (
        match.buyma_parent_category or "",
        match.buyma_middle_category or "",
        match.buyma_child_category or "",
    )
