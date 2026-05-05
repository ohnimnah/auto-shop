"""Application-wide constants and default configuration values."""

import os
from typing import List, Tuple

# ==================== 설정 기본값 ====================
DEFAULT_SPREADSHEET_ID = "1mTV-Fcybov-0uC7tNyM_GXGDoth8F_7wM__zaC1fAjs"
DEFAULT_SHEET_GIDS = [1698424449]
DEFAULT_SHEET_NAME = "시트1"

HEADER_ROW = 1
MARGIN_RATE_HEADER = "마진률"
PROGRESS_STATUS_HEADER = "진행상태"
MARGIN_THRESHOLD_PERCENT = 9.0

# 진행 상태
STATUS_HOLD = "보류"
STATUS_WAITING = "대기"  # 레거시 호환
STATUS_IMAGE_READY = "이미지진행대기"  # 레거시 호환
STATUS_THUMBNAIL_READY = "썸네일진행대기"  # 레거시 호환
STATUS_UPLOAD_READY = "업로드진행대기"  # 레거시 호환
STATUS_COMPLETED = "출품완료"
STATUS_ERROR = "오류"
STATUS_NEW = "신규"
STATUS_CRAWLED = "정찰완료"
STATUS_IMAGES_SAVED = "이미지저장완료"
STATUS_THUMBNAILS_DONE = "썸네일완료"
STATUS_CRAWLING = "정찰중"
STATUS_DOWNLOADING = "이미지저장중"
STATUS_THUMBNAILING = "썸네일작업중"

# 시트 열 구조
SEQUENCE_COLUMN = "A"
URL_COLUMN = "B"
BRAND_COLUMN = "C"
BRAND_EN_COLUMN = "D"
PRODUCT_NAME_KR_COLUMN = "E"
PRODUCT_NAME_EN_COLUMN = "F"
MUSINSA_SKU_COLUMN = "G"
COLOR_KR_COLUMN = "H"
COLOR_EN_COLUMN = "I"
SIZE_COLUMN = "J"
ACTUAL_SIZE_COLUMN = "K"
PRICE_COLUMN = "L"
BAIMA_SELL_PRICE_COLUMN = "M"
IMAGE_PATHS_COLUMN = "O"
SHIPPING_COST_COLUMN = "P"
CATEGORY_LARGE_COLUMN = "X"
CATEGORY_MIDDLE_COLUMN = "Y"
CATEGORY_SMALL_COLUMN = "Z"
SHIPPING_TABLE_RANGE = "AA1:AC60"
DEFAULT_ROW_START = 2

DEFAULT_SHEET_COLUMNS = {
    "sequence": SEQUENCE_COLUMN,
    "url": URL_COLUMN,
    "brand": BRAND_COLUMN,
    "brand_en": BRAND_EN_COLUMN,
    "product_name_kr": PRODUCT_NAME_KR_COLUMN,
    "product_name_en": PRODUCT_NAME_EN_COLUMN,
    "musinsa_sku": MUSINSA_SKU_COLUMN,
    "color_kr": COLOR_KR_COLUMN,
    "color_en": COLOR_EN_COLUMN,
    "size": SIZE_COLUMN,
    "actual_size": ACTUAL_SIZE_COLUMN,
    "price": PRICE_COLUMN,
    "buyma_price": BAIMA_SELL_PRICE_COLUMN,
    "buyma_meta": "N",
    "image_paths": IMAGE_PATHS_COLUMN,
    "shipping_cost": SHIPPING_COST_COLUMN,
    "category_large": CATEGORY_LARGE_COLUMN,
    "category_middle": CATEGORY_MIDDLE_COLUMN,
    "category_small": CATEGORY_SMALL_COLUMN,
    "shipping_table_range": SHIPPING_TABLE_RANGE,
}

# 상품명 키워드 → 추정 무게(kg)
KEYWORD_WEIGHT_RULES: List[Tuple[List[str], float]] = [
    (["패딩", "다운", "점퍼", "코트", "무스탕", "파카", "padding", "down", "coat", "parka", "puffer"], 2.5),
    (["겨울신발", "부츠", "워커", "boots", "boot", "walker"], 3.5),
    (["가방", "백팩", "캐리어", "토트백", "숄더백", "크로스백", "bag", "backpack", "tote", "shoulder", "crossbody", "carrier"], 3.5),
    (["후드", "맨투맨", "스웨트", "니트", "집업", "hoodie", "sweatshirt", "sweat", "knit", "cardigan", "zip-up", "zipup"], 1.5),
    (["자켓", "블레이저", "블루종", "바람막이", "아우터", "jacket", "blazer", "blouson", "windbreaker", "outer"], 2.0),
    (["바지", "팬츠", "청바지", "데님", "슬랙스", "조거", "트랙", "pants", "jeans", "denim", "slacks", "jogger", "track"], 1.0),
    (["원피스", "드레스", "dress", "onepiece"], 1.0),
    (["셔츠", "블라우스", "shirt", "blouse"], 0.5),
    (["티셔츠", "반팔", "긴팔", "탑", "티", "t-shirt", "tee", "top", "long sleeve", "short sleeve"], 1.0),
    (["운동화", "스니커즈", "슬리퍼", "샌들", "로퍼", "플랫", "슈즈", "클로그", "sneakers", "sneaker", "slipper", "sandals", "loafer", "flat", "shoes", "clog"], 1.5),
    (["레깅스", "스타킹", "양말", "속옷", "leggings", "stocking", "socks", "underwear", "bra", "panty"], 0.5),
    (["모자", "캡", "버킷햇", "비니", "hat", "cap", "bucket hat", "beanie"], 0.5),
    (["안경", "선글라스", "장갑", "머플러", "스카프", "벨트", "지갑", "케이스", "키링", "glasses", "sunglasses", "glove", "muffler", "scarf", "belt", "wallet", "case", "keyring"], 0.5),
]

OPT_KIND_WEIGHT_MAP = {
    "SHOES": 1.5,
    "BAG": 3.5,
    "ACC": 0.5,
    "CLOTHES": 1.2,
    "OUTER": 2.5,
    "TOP": 1.0,
    "BOTTOM": 1.0,
    "DRESS": 1.0,
    "UNDERWEAR": 0.5,
}

DEFAULT_WEIGHT_KG = 1.0
MAX_THUMBNAIL_IMAGES = 10
HEADLESS = True

# 감시/크롤링 간격
WATCH_INTERVAL_SECONDS = 20
CRAWL_PAGE_SETTLE_SECONDS = 1.0
CRAWLER_ROW_DELAY_SECONDS = 1.5
IMAGE_ROW_DELAY_SECONDS = 0.4
THUMB_ROW_DELAY_SECONDS = 0.4


def get_default_data_dir() -> str:
    """기본 런타임 데이터 경로를 OS별로 반환한다."""
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return os.path.join(local_app_data, "auto_shop")
    return os.path.join(os.path.expanduser("~"), ".auto_shop")


def get_default_images_dir() -> str:
    """기본 이미지 저장 경로를 반환한다."""
    env_images_dir = os.environ.get("AUTO_SHOP_IMAGES_DIR", "").strip()
    if env_images_dir:
        return os.path.abspath(os.path.expanduser(env_images_dir))
    return os.path.join(os.path.expanduser("~"), "images")
