"""Product model used across crawler/pipeline/services."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping


# Product field groups (current usage based)
PRODUCT_CORE_ID_FIELDS = (
    "musinsa_sku",
    "product_name_kr",
    "product_name_jp",
    "product_name_en",
    "brand",
)

PRODUCT_SHEET_DERIVED_FIELDS = (
    "image_paths",
    "buyma_price",
    "buyma_meta",
    "shipping_cost",
    "musinsa_category_large",
    "musinsa_category_middle",
    "musinsa_category_small",
)

PRODUCT_CRAWL_RESULT_FIELDS = (
    "brand_en",
    "color_kr",
    "size",
    "actual_size",
    "price",
    "brand_logo_url",
    "opt_kind_cd",
)

PRODUCT_POST_PROCESS_FIELDS = (
    "buyma_price",
    "image_paths",
    "shipping_cost",
)

# Reserved candidates (not introduced to dataclass yet):
# - status
# - row_num
# - url
# - error_message


@dataclass
class Product:
    # Core identifiers
    musinsa_sku: str = ""
    product_name_kr: str = "상품명 미확인"
    product_name_jp: str = ""
    product_name_en: str = ""
    brand: str = ""

    # Crawl result fields
    brand_en: str = ""
    color_kr: str = "none"
    size: str = ""
    actual_size: str = "못찾음"
    price: str = "가격 미확인"
    brand_logo_url: str = ""
    opt_kind_cd: str = ""
    musinsa_category_large: str = ""
    musinsa_category_middle: str = ""
    musinsa_category_small: str = ""

    # Post-process / upload derived fields
    buyma_price: str = ""
    buyma_meta: str = ""
    image_paths: str = ""
    shipping_cost: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


PRODUCT_SHEET_FIELDS = (
    "brand",
    "brand_en",
    "product_name_kr",
    "product_name_jp",
    "product_name_en",
    "musinsa_sku",
    "color_kr",
    "size",
    "actual_size",
    "price",
    "buyma_price",
    "buyma_meta",
    "image_paths",
    "shipping_cost",
    "musinsa_category_large",
    "musinsa_category_middle",
    "musinsa_category_small",
)


def product_to_sheet_field_map(product: Any) -> Dict[str, str]:
    """Normalize Product/dict-like value into sheet field map."""
    if product is None:
        return {}

    raw: Mapping[str, Any] | Dict[str, Any] | None = None
    if isinstance(product, dict):
        raw = product
    elif isinstance(product, Product):
        raw = product.to_dict()
    elif hasattr(product, "to_dict"):
        try:
            maybe_dict = product.to_dict()
            if isinstance(maybe_dict, dict):
                raw = maybe_dict
        except Exception:
            raw = None

    if raw is None:
        return {}

    out: Dict[str, str] = {}
    for field in PRODUCT_SHEET_FIELDS:
        value = raw.get(field, "")
        out[field] = str(value or "").strip()
    return out


def product_from_sheet_row(
    row_values: Mapping[str, Any] | None,
    column_map: Mapping[str, str],
) -> Product:
    """Build Product from one sheet row dict using field->column mapping."""
    row = row_values or {}

    def _cell(field_name: str) -> str:
        column = str(column_map.get(field_name, "") or "").strip()
        if not column:
            return ""
        return str(row.get(column, "") or "").strip()

    return Product(
        brand=_cell("brand"),
        brand_en=_cell("brand_en"),
        product_name_kr=_cell("product_name_kr"),
        product_name_jp=_cell("product_name_jp"),
        product_name_en=_cell("product_name_en"),
        color_kr=_cell("color_kr"),
        size=_cell("size"),
        actual_size=_cell("actual_size"),
        price=_cell("price"),
        buyma_price=_cell("buyma_price"),
        buyma_meta=_cell("buyma_meta"),
        musinsa_sku=_cell("musinsa_sku"),
        image_paths=_cell("image_paths"),
        musinsa_category_large=_cell("musinsa_category_large"),
        musinsa_category_middle=_cell("musinsa_category_middle"),
        musinsa_category_small=_cell("musinsa_category_small"),
        shipping_cost=_cell("shipping_cost"),
    )
