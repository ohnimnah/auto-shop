"""Standalone StandardCategory -> BUYMA mapping table support.

This module does NOT change upload behavior.
It is a support layer for manual `category_mapping` table creation and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from marketplace.buyma.standard_category import StandardCategory


# BUYMA labels (use unicode escapes to avoid terminal/font encoding issues)
PARENT_WOMEN = "\u30ec\u30c7\u30a3\u30fc\u30b9\u30d5\u30a1\u30c3\u30b7\u30e7\u30f3"
PARENT_MEN = "\u30e1\u30f3\u30ba\u30d5\u30a1\u30c3\u30b7\u30e7\u30f3"

MIDDLE_TOPS = "\u30c8\u30c3\u30d7\u30b9"
MIDDLE_INNER_ROOM = "\u30a4\u30f3\u30ca\u30fc\u30fb\u30eb\u30fc\u30e0\u30a6\u30a7\u30a2"

CHILD_HOODIE = "\u30d1\u30fc\u30ab\u30fc\u30fb\u30d5\u30fc\u30c7\u30a3"
CHILD_SWEAT = "\u30b9\u30a6\u30a7\u30c3\u30c8\u30fb\u30c8\u30ec\u30fc\u30ca\u30fc"
CHILD_TSHIRT = "T\u30b7\u30e3\u30c4\u30fb\u30ab\u30c3\u30c8\u30bd\u30fc"
CHILD_KNIT = "\u30cb\u30c3\u30c8\u30fb\u30bb\u30fc\u30bf\u30fc"
CHILD_PAJAMA = "\u30eb\u30fc\u30e0\u30a6\u30a7\u30a2\u30fb\u30d1\u30b8\u30e3\u30de"


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
    text = " ".join([musinsa_large or "", musinsa_middle or "", musinsa_small or "", product_name or ""]).lower()

    if _contains(text, ["\ud30c\uc790\ub9c8", "\uc7a0\uc637", "\ub8f8\uc6e8\uc5b4", "pajama", "sleepwear", "loungewear"]):
        return StandardCategory.HOME_PAJAMA
    if _contains(text, ["\ud6c4\ub4dc", "\ud6c4\ub514", "hoodie", "hooded"]):
        return StandardCategory.TOP_HOODIE
    if _contains(text, ["\ub9e8\ud22c\ub9e8", "\uc2a4\uc6e8\ud2b8", "\uc2a4\uc6fb", "sweatshirt"]):
        return StandardCategory.TOP_SWEAT
    if _contains(text, ["\ub2c8\ud2b8", "\uc2a4\uc6e8\ud130", "knit", "sweater"]):
        return StandardCategory.TOP_KNIT
    if _contains(text, ["\ud2f0\uc154\uce20", "\ubc18\ud314", "\uae34\ud314", "t-shirt", "tee"]):
        return StandardCategory.TOP_TSHIRT
    return StandardCategory.ETC


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
    specs: List[Tuple[StandardCategory, str, str]] = [
        (StandardCategory.TOP_HOODIE, MIDDLE_TOPS, CHILD_HOODIE),
        (StandardCategory.TOP_SWEAT, MIDDLE_TOPS, CHILD_SWEAT),
        (StandardCategory.TOP_TSHIRT, MIDDLE_TOPS, CHILD_TSHIRT),
        (StandardCategory.TOP_KNIT, MIDDLE_TOPS, CHILD_KNIT),
        (StandardCategory.HOME_PAJAMA, MIDDLE_INNER_ROOM, CHILD_PAJAMA),
    ]

    out: List[CategoryMappingRow] = []
    now = _now_iso()
    for gender, parent in (("women", PARENT_WOMEN), ("men", PARENT_MEN)):
        for std_cat, middle, child in specs:
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

