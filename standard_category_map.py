"""Reusable StandardCategory -> BUYMA category table layer.

Standalone support module. No direct integration into current upload flow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple

from marketplace.buyma.standard_category import StandardCategory


@dataclass(frozen=True)
class StandardCategoryMapRow:
    standard_category: str
    gender_scope: str  # women / men / unisex
    parent_category: str
    middle_category: str
    child_category: str
    note: str = ""


DEFAULT_STANDARD_CATEGORY_MAP: List[StandardCategoryMapRow] = [
    StandardCategoryMapRow(StandardCategory.TOP_HOODIE.value, "women", "レディーズファッション", "トップス", "パーカー・フーディ"),
    StandardCategoryMapRow(StandardCategory.TOP_HOODIE.value, "men", "メンズファッション", "トップス", "パーカー・フーディ"),
    StandardCategoryMapRow(StandardCategory.TOP_SWEAT.value, "women", "レディーズファッション", "トップス", "スウェット・トレーナー"),
    StandardCategoryMapRow(StandardCategory.TOP_SWEAT.value, "men", "メンズファッション", "トップス", "スウェット・トレーナー"),
    StandardCategoryMapRow(StandardCategory.TOP_TSHIRT.value, "women", "レディーズファッション", "トップス", "Tシャツ・カットソー"),
    StandardCategoryMapRow(StandardCategory.TOP_TSHIRT.value, "men", "メンズファッション", "トップス", "Tシャツ・カットソー"),
    StandardCategoryMapRow(StandardCategory.TOP_SHIRT.value, "women", "レディーズファッション", "トップス", "シャツ"),
    StandardCategoryMapRow(StandardCategory.TOP_SHIRT.value, "men", "メンズファッション", "トップス", "シャツ"),
    StandardCategoryMapRow(StandardCategory.TOP_KNIT.value, "women", "レディーズファッション", "トップス", "ニット・セーター"),
    StandardCategoryMapRow(StandardCategory.TOP_KNIT.value, "men", "メンズファッション", "トップス", "ニット・セーター"),
    StandardCategoryMapRow(StandardCategory.TOP_CARDIGAN.value, "women", "レディーズファッション", "トップス", "カーディガン"),
    StandardCategoryMapRow(StandardCategory.TOP_CARDIGAN.value, "men", "メンズファッション", "トップス", "カーディガン"),
    StandardCategoryMapRow(StandardCategory.HOME_PAJAMA.value, "women", "レディーズファッション", "インナー・ルームウェア", "ルームウェア・パジャマ"),
    StandardCategoryMapRow(StandardCategory.HOME_PAJAMA.value, "men", "メンズファッション", "インナー・ルームウェア", "ルームウェア・パジャマ"),
    StandardCategoryMapRow(StandardCategory.OUTER.value, "women", "レディーズファッション", "アウター", "ジャケット", "default outer"),
    StandardCategoryMapRow(StandardCategory.OUTER.value, "men", "メンズファッション", "アウター・ジャケット", "ジャケット", "default outer"),
    StandardCategoryMapRow(StandardCategory.PANTS.value, "women", "レディーズファッション", "ボトムス", "パンツ", "default pants"),
    StandardCategoryMapRow(StandardCategory.PANTS.value, "men", "メンズファッション", "パンツ・ボトムス", "パンツ", "default pants"),
]


def _to_gender_scope(is_mens: bool) -> str:
    return "men" if is_mens else "women"


def resolve_standard_category_map_row(
    standard_category: StandardCategory,
    *,
    is_mens: bool,
) -> StandardCategoryMapRow | None:
    scope = _to_gender_scope(is_mens)
    key = standard_category.value
    for row in DEFAULT_STANDARD_CATEGORY_MAP:
        if row.standard_category == key and row.gender_scope == scope:
            return row
    return None


def resolve_standard_category_buyma_target(
    standard_category: StandardCategory,
    *,
    is_mens: bool,
    combined_text: str = "",
) -> Tuple[str, str, str]:
    """Return (parent, middle, child) target using table + rule refinements.

    This module is standalone support and does not alter current upload path.
    """
    base = resolve_standard_category_map_row(standard_category, is_mens=is_mens)
    if base is None:
        return "", "", ""

    text = (combined_text or "").lower()
    parent, middle, child = base.parent_category, base.middle_category, base.child_category

    if standard_category == StandardCategory.OUTER:
        if any(k in text for k in ("down jacket", "puffer", "패딩", "다운")):
            child = "ダウンジャケット"
        elif any(k in text for k in ("coat", "코트")):
            child = "コート"

    if standard_category == StandardCategory.PANTS:
        if any(k in text for k in ("denim", "jeans", "데님", "청바지")):
            child = "デニム・ジーパン"
        elif any(k in text for k in ("slacks", "trousers", "슬랙스")):
            child = "スラックス"
        elif any(k in text for k in ("shorts", "쇼츠", "반바지")):
            child = "ハーフ・ショートパンツ"

    return parent, middle, child


def default_mapping_rows_as_dicts() -> List[Dict[str, str]]:
    return [asdict(row) for row in DEFAULT_STANDARD_CATEGORY_MAP]

