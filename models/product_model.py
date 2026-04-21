"""Product model used across crawler/pipeline/services."""

from dataclasses import asdict, dataclass
from typing import Dict


@dataclass
class Product:
    brand: str = ""
    brand_en: str = ""
    product_name_kr: str = "상품명 미확인"
    color_kr: str = "none"
    size: str = ""
    actual_size: str = "못찾음"
    price: str = "가격 미확인"
    buyma_price: str = ""
    musinsa_sku: str = ""
    image_paths: str = ""
    brand_logo_url: str = ""
    opt_kind_cd: str = ""
    musinsa_category_large: str = ""
    musinsa_category_middle: str = ""
    musinsa_category_small: str = ""
    shipping_cost: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)
