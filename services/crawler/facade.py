from __future__ import annotations

# Re-export legacy behavior first for compatibility.
from services.crawler_service_legacy import *  # type: ignore

from services.crawler import image_extractor as _image_extractor
from services.crawler import musinsa_client as _musinsa_client
from services.crawler import option_parser as _option_parser
from services.crawler import parser as _parser
from services.crawler import price_parser as _price_parser


def fetch_json(url: str):
    return _musinsa_client.fetch_json(url)


def has_hangul(text: str) -> bool:
    return _parser.has_hangul(text)


def sanitize_path_component(value: str) -> str:
    return _parser.sanitize_path_component(value)


def build_image_folder_name(row_num: int, row_start: int, product_name: str) -> str:
    return _parser.build_image_folder_name(row_num, row_start, product_name)


def normalize_image_source(src: str) -> str:
    return _image_extractor.normalize_image_source(src)


def build_image_identity_key(image_url: str) -> str:
    return _image_extractor.build_image_identity_key(image_url)


def extract_discounted_product_price(soup):
    return _price_parser.extract_discounted_product_price(soup)


def normalize_size_tokens(tokens, option_kind: str = ""):
    return _option_parser.normalize_size_tokens(tokens, option_kind=option_kind)

