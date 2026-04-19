"""
무신사 상품 정보를 크롤링하여 Google Sheets에 자동으로 입력하는 자동화 스크립트
아래 링크의 스프레드시트 구조와 동일하게 사용할 수 있도록 데이터를 입력합니다.
- 시트 ID: 1mTV-Fcybov-0uC7tNyM_GXGDoth8F_7wM__zaC1fAjs
- 탭 GID: 1698424449
"""

import json
import argparse
from dataclasses import asdict, is_dataclass
import os
import re
import sys
import time
import urllib.parse
from typing import Dict, List, Tuple
from app_config import (
    ACTUAL_SIZE_COLUMN,
    BAIMA_SELL_PRICE_COLUMN,
    BRAND_COLUMN,
    BRAND_EN_COLUMN,
    CATEGORY_LARGE_COLUMN,
    CATEGORY_MIDDLE_COLUMN,
    CATEGORY_SMALL_COLUMN,
    COLOR_EN_COLUMN,
    COLOR_KR_COLUMN,
    CRAWL_PAGE_SETTLE_SECONDS,
    CRAWLER_ROW_DELAY_SECONDS,
    DEFAULT_ROW_START,
    DEFAULT_SHEET_GIDS,
    DEFAULT_SHEET_NAME,
    DEFAULT_SPREADSHEET_ID,
    DEFAULT_WEIGHT_KG,
    HEADLESS,
    HEADER_ROW,
    IMAGE_PATHS_COLUMN,
    IMAGE_ROW_DELAY_SECONDS,
    KEYWORD_WEIGHT_RULES,
    MARGIN_RATE_HEADER,
    MARGIN_THRESHOLD_PERCENT,
    MAX_THUMBNAIL_IMAGES,
    MUSINSA_SKU_COLUMN,
    OPT_KIND_WEIGHT_MAP,
    PRICE_COLUMN,
    PRODUCT_NAME_EN_COLUMN,
    PRODUCT_NAME_KR_COLUMN,
    PROGRESS_STATUS_HEADER,
    SEQUENCE_COLUMN,
    SHIPPING_COST_COLUMN,
    SIZE_COLUMN,
    STATUS_COMPLETED,
    STATUS_CRAWLED,
    STATUS_CRAWLING,
    STATUS_DOWNLOADING,
    STATUS_ERROR,
    STATUS_HOLD,
    STATUS_IMAGE_READY,
    STATUS_IMAGES_SAVED,
    STATUS_NEW,
    STATUS_THUMBNAIL_READY,
    STATUS_THUMBNAILING,
    STATUS_THUMBNAILS_DONE,
    STATUS_UPLOAD_READY,
    STATUS_WAITING,
    THUMB_ROW_DELAY_SECONDS,
    URL_COLUMN,
    WATCH_INTERVAL_SECONDS,
    get_default_data_dir,
    get_default_images_dir,
)
from sheet_service import (
    batch_update_values as svc_batch_update_values,
    column_index_to_letter as svc_column_index_to_letter,
    get_existing_row_values as svc_get_existing_row_values,
    get_existing_rows_bulk as svc_get_existing_rows_bulk,
    get_target_sheet_names as svc_get_target_sheet_names,
    get_sheet_name_by_gid as svc_get_sheet_name_by_gid,
    is_url_cell as svc_is_url_cell,
    read_urls_from_sheet as svc_read_urls_from_sheet,
    get_row_dynamic_values as svc_get_row_dynamic_values,
    get_rows_dynamic_values_bulk as svc_get_rows_dynamic_values_bulk,
    get_sheet_header_map as svc_get_sheet_header_map,
    parse_margin_rate as svc_parse_margin_rate,
    update_value_by_range as svc_update_value_by_range,
    update_cell_by_header as svc_update_cell_by_header,
)
from image_service import (
    build_thumbnail_brand as svc_build_thumbnail_brand,
    create_thumbnail_for_folder as svc_create_thumbnail_for_folder,
    download_brand_logo as svc_download_brand_logo,
    download_thumbnail_images as svc_download_thumbnail_images,
    extract_brand_logo_url as svc_extract_brand_logo_url,
    resolve_image_folder_from_paths as svc_resolve_image_folder_from_paths,
)
from crawler_service import (
    build_image_folder_name as svc_build_image_folder_name,
    build_image_identity_key as svc_build_image_identity_key,
    classify_size_token as svc_classify_size_token,
    clean_product_name as svc_clean_product_name,
    extract_actual_size_text as svc_extract_actual_size_text,
    extract_actual_size_table_text as svc_extract_actual_size_table_text,
    extract_color_from_api as svc_extract_color_from_api,
    extract_musinsa_categories as svc_extract_musinsa_categories,
    extract_musinsa_gender_large as svc_extract_musinsa_gender_large,
    extract_musinsa_sku as svc_extract_musinsa_sku,
    extract_brand_en_from_musinsa as svc_extract_brand_en_from_musinsa,
    extract_brand_text as svc_extract_brand_text,
    extract_color_from_name as svc_extract_color_from_name,
    extract_mss_product_state as svc_extract_mss_product_state,
    extract_musinsa_thumbnail_urls as svc_extract_musinsa_thumbnail_urls,
    extract_product_json as svc_extract_product_json,
    fetch_actual_size as svc_fetch_actual_size,
    fetch_goods_options as svc_fetch_goods_options,
    fetch_json as svc_fetch_json,
    find_longest_step_sequence as svc_find_longest_step_sequence,
    get_color_name_map as svc_get_color_name_map,
    has_hangul as svc_has_hangul,
    is_date_like_size_token as svc_is_date_like_size_token,
    is_color_count_placeholder as svc_is_color_count_placeholder,
    normalize_image_source as svc_normalize_image_source,
    normalize_english_color as svc_normalize_english_color,
    normalize_gender_label as svc_normalize_gender_label,
    normalize_korean_color as svc_normalize_korean_color,
    normalize_size_tokens as svc_normalize_size_tokens,
    extract_sizes as svc_extract_sizes,
    extract_sizes_from_api as svc_extract_sizes_from_api,
    extract_sizes_from_option_ui as svc_extract_sizes_from_option_ui,
    extract_sizes_from_review_options as svc_extract_sizes_from_review_options,
    extract_sizes_from_table as svc_extract_sizes_from_table,
    extract_size_from_fit_info_block as svc_extract_size_from_fit_info_block,
    remap_categories_with_gender as svc_remap_categories_with_gender,
    scrape_musinsa_product as svc_scrape_musinsa_product,
    sanitize_path_component as svc_sanitize_path_component,
    split_color_size_tokens as svc_split_color_size_tokens,
    split_name_and_color as svc_split_name_and_color,
)
from pipeline_service import (
    build_incremental_payload as svc_build_incremental_payload,
    determine_progress_status as svc_determine_progress_status,
    is_empty_cell as svc_is_empty_cell,
    row_has_existing_output as svc_row_has_existing_output,
    row_needs_image_download as svc_row_needs_image_download,
    row_needs_update as svc_row_needs_update,
    is_crawler_ready_status as svc_is_crawler_ready_status,
    is_image_ready_status as svc_is_image_ready_status,
    process_sheet_once as svc_process_sheet_once,
    is_thumbnail_ready_status as svc_is_thumbnail_ready_status,
)
from buyma_service import (
    fetch_buyma_lowest_price as svc_fetch_buyma_lowest_price,
    format_price as svc_format_price,
    extract_buyma_item_page_price as svc_extract_buyma_item_page_price,
    extract_buyma_listing_entries as svc_extract_buyma_listing_entries,
    extract_buyma_listing_prices as svc_extract_buyma_listing_prices,
    extract_buyma_shipping_included_prices as svc_extract_buyma_shipping_included_prices,
    extract_discounted_product_price as svc_extract_discounted_product_price,
    extract_yen_values as svc_extract_yen_values,
    is_relevant_buyma_item as svc_is_relevant_buyma_item,
    is_relevant_buyma_listing_entry as svc_is_relevant_buyma_listing_entry,
    normalize_buyma_query as svc_normalize_buyma_query,
    normalize_price as svc_normalize_price,
)
from browser_service import setup_chrome_driver as svc_setup_chrome_driver
from product_model import Product

# Windows cp949 터미널에서 유니코드 출력 오류 방지
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") in ("cp949", "euckr"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# SSL 경고 무시
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 설정 부분 ====================
SPREADSHEET_ID = DEFAULT_SPREADSHEET_ID
# 링크의 탭 GID 목록을 적어주세요. 서비스 계정이 해당 스프레드시트에 권한이 있어야 동작합니다.
SHEET_GIDS = list(DEFAULT_SHEET_GIDS)
# GID를 사용하지 않을 때는 아래 default sheet name을 설정합니다.
SHEET_NAME = DEFAULT_SHEET_NAME
ROW_START = DEFAULT_ROW_START


def _load_sheet_runtime_config() -> None:
    """런처에서 저장한 시트 설정을 읽어 런타임 기본값을 덮어쓴다."""
    global SPREADSHEET_ID, SHEET_GIDS, SHEET_NAME, ROW_START
    local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
    if local_app_data:
        data_dir = os.path.join(local_app_data, 'auto_shop')
    else:
        data_dir = os.path.join(os.path.expanduser('~'), '.auto_shop')

    cfg_path = os.path.join(data_dir, 'sheets_config.json')
    if not os.path.exists(cfg_path):
        return

    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return

        sid = (cfg.get('spreadsheet_id') or '').strip()
        # URL 전체가 저장된 경우에도 /d/<id>/에서 ID만 추출
        if sid:
            m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sid)
            if m:
                sid = m.group(1)
            else:
                m2 = re.search(r'(?:^|/)d/([a-zA-Z0-9-_]+)', sid)
                if m2:
                    sid = m2.group(1)
        if sid:
            SPREADSHEET_ID = sid

        sname = (cfg.get('sheet_name') or '').strip()
        if sname:
            SHEET_NAME = sname

        gids = cfg.get('sheet_gids')
        if isinstance(gids, list):
            parsed = [int(x) for x in gids if isinstance(x, int) or str(x).isdigit()]
            if parsed:
                SHEET_GIDS = parsed

        rstart = cfg.get('row_start')
        if isinstance(rstart, int) and rstart >= 1:
            ROW_START = rstart
    except Exception as e:
        print(f"시트 설정 로드 실패: {e}")


_load_sheet_runtime_config()

DATA_DIR = get_default_data_dir()
IMAGES_ROOT = get_default_images_dir()
CREDENTIALS_PATH = os.path.join(DATA_DIR, 'credentials.json')


def initialize_runtime_paths(data_dir: str = "", credentials_file: str = ""):
    """런타임 파일 경로를 초기화한다"""
    global DATA_DIR, IMAGES_ROOT, CREDENTIALS_PATH

    env_data_dir = os.environ.get('AUTO_SHOP_DATA_DIR', '').strip()
    selected_data_dir = (data_dir or env_data_dir or DATA_DIR).strip()
    selected_data_dir = os.path.abspath(os.path.expanduser(selected_data_dir))

    DATA_DIR = selected_data_dir
    # --data-dir가 명시적으로 지정된 경우에만 images 경로도 그 하위로 이동
    if data_dir or env_data_dir:
        IMAGES_ROOT = os.path.join(DATA_DIR, 'images')
    else:
        IMAGES_ROOT = get_default_images_dir()
    os.makedirs(IMAGES_ROOT, exist_ok=True)

    env_credentials = os.environ.get('AUTO_SHOP_CREDENTIALS', '').strip()
    if credentials_file:
        CREDENTIALS_PATH = os.path.abspath(os.path.expanduser(credentials_file))
    elif env_credentials:
        CREDENTIALS_PATH = os.path.abspath(os.path.expanduser(env_credentials))
    else:
        CREDENTIALS_PATH = os.path.join(DATA_DIR, 'credentials.json')

    print(f"데이터 폴더: {DATA_DIR}")
    print(f"자격증명 파일: {CREDENTIALS_PATH}")


# ==================== 배송비 산출 ====================

def read_shipping_table(service, sheet_name: str) -> List[Tuple[float, int]]:
    """Z/AA/AB 영역에서 무게(kg)→배송비(원) 기준표를 읽어 리스트로 반환한다.
    반환: [(0.5, 8950), (1.0, 11350), ...] 무게 오름차순"""
    def _parse_table_rows(rows: List[List[str]]) -> List[Tuple[float, int]]:
        table: List[Tuple[float, int]] = []
        for row in rows:
            if len(row) < 2:
                continue
            weight_raw = (row[0] or '').strip()
            weight_norm = weight_raw.replace('kg', '').replace('KG', '').replace(',', '.').strip()
            try:
                weight = float(weight_norm)
            except ValueError:
                continue

            # AA열 배송비를 우선 사용, 없으면 AB열을 보조 사용
            cost_digits = re.sub(r'[^\d]', '', (row[1] or '').strip()) if len(row) > 1 else ""
            if not cost_digits and len(row) > 2:
                cost_digits = re.sub(r'[^\d]', '', (row[2] or '').strip())
            if not cost_digits:
                continue
            table.append((weight, int(cost_digits)))
        table.sort(key=lambda x: x[0])
        return table

    # 일시적 시트 응답 문제 대비: 1회 재시도
    for attempt in (1, 2):
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=f"'{sheet_name}'!Z1:AB60"
            ).execute()
            rows = result.get('values', [])
            table = _parse_table_rows(rows)
            if table:
                return table
            if attempt == 1:
                time.sleep(0.4)
                continue
            return []
        except Exception as e:
            if attempt == 1:
                time.sleep(0.4)
                continue
            print(f" 배송비 기준표 조회 실패: {e}")
            return []
    return []


def estimate_weight(product_name: str, opt_kind_cd: str) -> float:
    """상품명 키워드 + optKindCd로 추정 무게(kg)를 반환한다"""
    name_lower = (product_name or '').lower()
    for keywords, weight in KEYWORD_WEIGHT_RULES:
        for kw in keywords:
            if kw in name_lower:
                return weight
    kind = (opt_kind_cd or '').upper()
    return OPT_KIND_WEIGHT_MAP.get(kind, DEFAULT_WEIGHT_KG)


def lookup_shipping_cost(table: List[Tuple[float, int]], weight_kg: float) -> str:
    """무게에 해당하는 배송비를 기준표에서 찾아 '₩xx,xxx' 형태로 반환한다.
    무게 이상인 가장 가까운 구간을 선택한다."""
    if not table:
        return ""
    for tier_weight, tier_cost in table:
        if weight_kg <= tier_weight:
            return f"{tier_cost:,}"
    # 기준표 최대치 초과 시 마지막 구간 사용
    return f"{table[-1][1]:,}"


# ==================== Google Sheets 연동 ====================

def column_index_to_letter(index: int) -> str:
    """0-based 열 인덱스를 Google Sheets 열 문자로 변환한다."""
    return svc_column_index_to_letter(index)


def get_sheet_header_map(service, sheet_name: str) -> Dict[str, int]:
    """1행 헤더명을 읽어 헤더명 -> 0-based 열 인덱스 맵을 반환한다."""
    return svc_get_sheet_header_map(service, SPREADSHEET_ID, sheet_name, HEADER_ROW)


def get_row_dynamic_values(
    service,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_names: List[str],
) -> Dict[str, str]:
    """헤더명 기준으로 특정 행의 동적 컬럼 값을 읽는다."""
    return svc_get_row_dynamic_values(
        service,
        SPREADSHEET_ID,
        sheet_name,
        row_num,
        header_map,
        header_names,
    )


def get_rows_dynamic_values_bulk(
    service,
    sheet_name: str,
    row_numbers: List[int],
    header_map: Dict[str, int],
    header_names: List[str],
) -> Dict[int, Dict[str, str]]:
    """헤더명 기준 동적 컬럼 값을 여러 행에서 한 번에 읽어 반환한다."""
    return svc_get_rows_dynamic_values_bulk(
        service,
        SPREADSHEET_ID,
        sheet_name,
        row_numbers,
        header_map,
        header_names,
    )


def update_cell_by_header(
    service,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_name: str,
    value: str,
) -> bool:
    """헤더명 기준으로 특정 셀 값을 업데이트한다."""
    return svc_update_cell_by_header(
        service,
        SPREADSHEET_ID,
        sheet_name,
        row_num,
        header_map,
        header_name,
        value,
    )


def parse_margin_rate(value: str) -> float | None:
    """마진률 셀 문자열을 퍼센트 숫자로 변환한다."""
    return svc_parse_margin_rate(value)


def determine_progress_status(margin_rate: float | None) -> str:
    """마진률 기준으로 다음 진행상태를 계산한다."""
    return svc_determine_progress_status(
        margin_rate=margin_rate,
        margin_threshold_percent=MARGIN_THRESHOLD_PERCENT,
        status_hold=STATUS_HOLD,
        status_crawled=STATUS_CRAWLED,
    )


def is_crawler_ready_status(status: str) -> bool:
    return svc_is_crawler_ready_status(
        status=status,
        status_waiting=STATUS_WAITING,
        status_new=STATUS_NEW,
    )


def is_image_ready_status(status: str) -> bool:
    return svc_is_image_ready_status(
        status=status,
        status_crawled=STATUS_CRAWLED,
        status_image_ready=STATUS_IMAGE_READY,
    )


def is_thumbnail_ready_status(status: str) -> bool:
    return svc_is_thumbnail_ready_status(
        status=status,
        status_images_saved=STATUS_IMAGES_SAVED,
        status_thumbnail_ready=STATUS_THUMBNAIL_READY,
    )


def resolve_image_folder_from_paths(image_paths: str) -> str:
    """콤마 구분 image_paths에서 첫 이미지의 폴더 경로를 반환한다."""
    return svc_resolve_image_folder_from_paths(image_paths)


def build_thumbnail_brand(existing_values: Dict[str, str]) -> str:
    """썸네일용 브랜드명을 우선순위대로 반환한다."""
    return svc_build_thumbnail_brand(existing_values)


def create_thumbnail_for_folder(folder_path: str, brand: str) -> bool:
    """이미지 폴더에서 썸네일을 생성한다."""
    return svc_create_thumbnail_for_folder(folder_path, brand)

def get_sheets_service():
    """Google Sheets API 서비스 객체 생성"""
    try:
        if not os.path.exists(CREDENTIALS_PATH):
            # 하위호환: 기존 프로젝트 루트의 credentials.json 우선 사용
            legacy_credentials = os.path.abspath('credentials.json')
            if os.path.exists(legacy_credentials):
                print("경고: 프로젝트 루트 credentials.json 사용 중. 보안을 위해 데이터 폴더로 이동 권장")
                credentials_path = legacy_credentials
            else:
                raise FileNotFoundError(f"자격증명 파일을 찾을 수 없습니다: {CREDENTIALS_PATH}")
        else:
            credentials_path = CREDENTIALS_PATH

        creds = Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        print(f" Google Sheets connection failed: {e}")
        sys.exit(1)


def get_sheet_name_by_gid(service, gid: int) -> str:
    """GID로 시트 이름을 찾는다"""
    return svc_get_sheet_name_by_gid(service, SPREADSHEET_ID, gid)


def get_target_sheet_names(service) -> List[str]:
    """SHEET_GIDS로 시트 이름을 찾거나 default sheet name을 반환"""
    return svc_get_target_sheet_names(service, SPREADSHEET_ID, SHEET_GIDS, SHEET_NAME)


def is_url_cell(value: str) -> bool:
    """셀값이 URL인지 감지"""
    return svc_is_url_cell(value)


def read_urls_from_sheet(service, sheet_name: str) -> List[Tuple[int, str]]:
    """Google Sheets에서 URL을 읽어 row 번호와 URL 목록을 반환"""
    return svc_read_urls_from_sheet(
        service,
        SPREADSHEET_ID,
        sheet_name,
        URL_COLUMN,
        ROW_START,
    )


def has_hangul(text: str) -> bool:
    """문자열에 한글이 포함되어 있는지 확인"""
    return svc_has_hangul(text)


def fetch_json(url: str) -> Dict[str, object]:
    """JSON API를 호출한다"""
    return svc_fetch_json(url)


def sanitize_path_component(value: str) -> str:
    """파일/폴더명으로 안전한 문자열로 정리한다"""
    return svc_sanitize_path_component(value)


def build_image_folder_name(row_num: int, product_name: str) -> str:
    """이미지 폴더명을 '행번호. 상품명' 형식으로 만든다"""
    return svc_build_image_folder_name(row_num, ROW_START, product_name)


def normalize_image_source(src: str) -> str:
    """무신사 이미지 URL을 다운로드 가능한 형태로 정규화한다"""
    return svc_normalize_image_source(src)


def build_image_identity_key(image_url: str) -> str:
    """같은 원본 사진의 다른 사이즈 URL을 하나로 묶기 위한 키를 만든다"""
    return svc_build_image_identity_key(image_url)


def extract_musinsa_thumbnail_urls(
    soup: BeautifulSoup,
    product_json: Dict[str, object],
    goods_no: str,
) -> List[str]:
    """무신사 상품 페이지에서 이미지 URL 목록을 추출한다"""
    return svc_extract_musinsa_thumbnail_urls(
        soup=soup,
        product_json=product_json,
        goods_no=goods_no,
        max_thumbnail_images=MAX_THUMBNAIL_IMAGES,
    )


def download_thumbnail_images(image_urls: List[str], folder_name: str) -> str:
    """이미지를 로컬 images 폴더에 저장하고 상대 경로 목록을 반환한다"""
    return svc_download_thumbnail_images(
        image_urls=image_urls,
        folder_name=folder_name,
        images_root=IMAGES_ROOT,
        max_thumbnail_images=MAX_THUMBNAIL_IMAGES,
    )


def extract_brand_logo_url(soup: BeautifulSoup, product_json: Dict[str, object]) -> str:
    """Extract brand logo URL from Musinsa page/json."""
    return svc_extract_brand_logo_url(soup, product_json)


def download_brand_logo(logo_url: str, folder_name: str, image_paths: str = "") -> str:
    """Save brand logo as __brand_logo.png in product image folder."""
    return svc_download_brand_logo(
        logo_url=logo_url,
        folder_name=folder_name,
        images_root=IMAGES_ROOT,
        image_paths=image_paths,
    )


def get_color_name_map() -> Dict[str, str]:
    """무신사 색상 코드표를 가져온다"""
    return svc_get_color_name_map()


def fetch_goods_options(goods_no: str, goods_sale_type: str, opt_kind_cd: str) -> Dict[str, object]:
    """상품 옵션 정보를 가져온다"""
    return svc_fetch_goods_options(goods_no, goods_sale_type, opt_kind_cd)


def fetch_actual_size(goods_no: str) -> Dict[str, object]:
    """상품 실측 사이즈 정보를 가져온다"""
    return svc_fetch_actual_size(goods_no)


def extract_actual_size_text(goods_no: str) -> str:
    """무신사 실측 API에서 실측표 텍스트를 추출해 한 줄 문자열로 반환한다."""
    return svc_extract_actual_size_text(goods_no)


def extract_actual_size_table_text(soup: BeautifulSoup, option_kind: str = "") -> str:
    """페이지의 실측 표를 읽어 한 줄 문자열로 반환한다."""
    return svc_extract_actual_size_table_text(soup, option_kind)


def extract_size_from_fit_info_block(soup: BeautifulSoup, option_kind: str = "") -> str:
    """무신사 사이즈 정보 문단에서 '내 사이즈 FREE[999]' 같은 텍스트를 추출한다."""
    return svc_extract_size_from_fit_info_block(soup, option_kind)


def extract_product_json(soup: BeautifulSoup) -> Dict[str, object]:
    """페이지 내 JSON-LD Product 데이터를 추출한다"""
    return svc_extract_product_json(soup)


def extract_mss_product_state(soup: BeautifulSoup) -> Dict[str, object]:
    """window.__MSS__.product.state 또는 __MSS_FE__.product.state를 추출한다"""
    return svc_extract_mss_product_state(soup)


def clean_product_name(name: str) -> str:
    """상품명에서 색상/품번 접미부를 제거한다"""
    return svc_clean_product_name(name)


def split_name_and_color(raw_name: str) -> Tuple[str, str]:
    """상품명과 색상 접미부를 분리한다"""
    return svc_split_name_and_color(raw_name)


def extract_color_from_name(raw_name: str) -> str:
    """???? ?? ?? ??? ???? ???? ????"""
    return svc_extract_color_from_name(raw_name)


def is_color_count_placeholder(text: str) -> bool:
    """'2color', '4 colors', '3??' ?? ?? ???? ????."""
    return svc_is_color_count_placeholder(text)

def normalize_korean_color(color_text: str) -> str:
    """한국어 색상 문자열을 보기 좋게 정리한다"""
    return svc_normalize_korean_color(color_text)


def normalize_english_color(color_text: str) -> str:
    """영문 색상 문자열을 보기 좋게 정리한다"""
    return svc_normalize_english_color(color_text)


def extract_brand_text(product_json: Dict[str, object], title_text: str) -> str:
    """브랜드명을 추출한다"""
    return svc_extract_brand_text(product_json, title_text)


def extract_brand_en_from_musinsa(driver, product_url: str) -> str:
    """무신사 상품 페이지에서 브랜드 영문명을 추출한다.
    상품 페이지의 브랜드 링크(/brand/slug)를 찾아
    브랜드 페이지 og:title에서 '한글(ENGLISH)' 패턴으로 영문명을 가져온다."""
    return svc_extract_brand_en_from_musinsa(driver, product_url)


def find_longest_step_sequence(values: List[int], allowed_steps: Tuple[int, ...]) -> List[int]:
    """허용된 간격을 갖는 가장 긴 수열을 찾는다"""
    return svc_find_longest_step_sequence(values, allowed_steps)


def classify_size_token(token: str) -> str:
    """사이즈 토큰 타입을 반환한다: numeric, english, korean, mixed, other"""
    return svc_classify_size_token(token)


def is_date_like_size_token(token: str) -> bool:
    """사이즈 토큰으로 보기 어려운 날짜형 문자열을 걸러낸다."""
    return svc_is_date_like_size_token(token)


def normalize_size_tokens(tokens: List[str], option_kind: str = "") -> List[str]:
    """사이즈 토큰을 숫자/영문/한글 한 종류만 남도록 정규화한다"""
    return svc_normalize_size_tokens(tokens, option_kind)


def extract_color_from_api(goods_options: Dict[str, object]) -> str:
    """옵션 API의 colorCode를 색상명으로 변환한다"""
    return svc_extract_color_from_api(goods_options)


def split_color_size_tokens(tokens: List[str]) -> Tuple[List[str], List[str]]:
    """'한글색상 영문사이즈' 패턴 토큰에서 색상과 사이즈를 분리한다.
    절반 이상 패턴 일치 시 (색상 목록, 사이즈 목록) 반환, 아니면 ([], 원래 토큰) 반환."""
    return svc_split_color_size_tokens(tokens)


def extract_sizes_from_api(goods_no: str, goods_sale_type: str, opt_kind_cd: str) -> Tuple[str, str]:
    """옵션 API와 실측 API를 이용해 사이즈(, 색상)를 추출한다.
    반환: (size_str, color_str) — color_str은 '한글색상 영문사이즈' 패턴 감지 시에만 채워짐"""
    return svc_extract_sizes_from_api(goods_no, goods_sale_type, opt_kind_cd)


def extract_sizes_from_table(soup: BeautifulSoup, option_kind: str = "") -> List[str]:
    """무신사 표 영역에서 사이즈 값을 우선 추출한다"""
    return svc_extract_sizes_from_table(soup, option_kind)


def extract_sizes_from_option_ui(soup: BeautifulSoup, option_kind: str = "") -> str:
    """옵션 UI에 렌더된 사이즈 텍스트를 최대한 직접 추출한다."""
    return svc_extract_sizes_from_option_ui(soup, option_kind)


def extract_sizes_from_review_options(soup: BeautifulSoup, option_kind: str = "") -> List[int]:
    """리뷰의 선택옵션 영역에서 노출된 사이즈를 추출한다"""
    return svc_extract_sizes_from_review_options(soup, option_kind)


def extract_sizes(soup: BeautifulSoup, option_kind: str = "") -> str:
    """페이지에서 사용 가능한 사이즈 후보를 추출한다"""
    return svc_extract_sizes(soup, option_kind)


def format_price(price_value: object) -> str:
    """숫자 또는 문자열 가격을 숫자 문자열로 변환한다"""
    return svc_format_price(price_value)


def is_empty_cell(value: str) -> bool:
    """셀 값이 비어있는지 확인한다"""
    return svc_is_empty_cell(value)


def extract_musinsa_sku(
    raw_product_name: str,
    product_name: str,
    mss_state: Dict[str, object],
    product_json: Dict[str, object] = None,
    soup: object = None,
) -> str:
    """무신사 원본 데이터에서 품번을 추출한다"""
    return svc_extract_musinsa_sku(
        raw_product_name=raw_product_name,
        product_name=product_name,
        mss_state=mss_state,
        product_json=product_json,
        soup=soup,
    )


def get_existing_row_values(service, sheet_name: str, row_num: int) -> Dict[str, str]:
    """현재 행의 A~Y 값을 읽어 컬럼별로 반환한다"""
    return svc_get_existing_row_values(
        service=service,
        spreadsheet_id=SPREADSHEET_ID,
        sheet_name=sheet_name,
        row_num=row_num,
        sequence_column=SEQUENCE_COLUMN,
        url_column=URL_COLUMN,
        brand_column=BRAND_COLUMN,
        brand_en_column=BRAND_EN_COLUMN,
        product_name_kr_column=PRODUCT_NAME_KR_COLUMN,
        product_name_en_column=PRODUCT_NAME_EN_COLUMN,
        musinsa_sku_column=MUSINSA_SKU_COLUMN,
        color_kr_column=COLOR_KR_COLUMN,
        color_en_column=COLOR_EN_COLUMN,
        size_column=SIZE_COLUMN,
        actual_size_column=ACTUAL_SIZE_COLUMN,
        price_column=PRICE_COLUMN,
        buyma_sell_price_column=BAIMA_SELL_PRICE_COLUMN,
        image_paths_column=IMAGE_PATHS_COLUMN,
        shipping_cost_column=SHIPPING_COST_COLUMN,
        category_large_column=CATEGORY_LARGE_COLUMN,
        category_middle_column=CATEGORY_MIDDLE_COLUMN,
        category_small_column=CATEGORY_SMALL_COLUMN,
    )


def get_existing_rows_bulk(
    service,
    sheet_name: str,
    row_numbers: List[int],
) -> Dict[int, Dict[str, str]]:
    """여러 행의 A~Y 값을 한 번에 읽어 행 번호별 맵으로 반환한다"""
    return svc_get_existing_rows_bulk(
        service=service,
        spreadsheet_id=SPREADSHEET_ID,
        sheet_name=sheet_name,
        row_numbers=row_numbers,
        sequence_column=SEQUENCE_COLUMN,
        url_column=URL_COLUMN,
        brand_column=BRAND_COLUMN,
        brand_en_column=BRAND_EN_COLUMN,
        product_name_kr_column=PRODUCT_NAME_KR_COLUMN,
        product_name_en_column=PRODUCT_NAME_EN_COLUMN,
        musinsa_sku_column=MUSINSA_SKU_COLUMN,
        color_kr_column=COLOR_KR_COLUMN,
        color_en_column=COLOR_EN_COLUMN,
        size_column=SIZE_COLUMN,
        actual_size_column=ACTUAL_SIZE_COLUMN,
        price_column=PRICE_COLUMN,
        buyma_sell_price_column=BAIMA_SELL_PRICE_COLUMN,
        image_paths_column=IMAGE_PATHS_COLUMN,
        shipping_cost_column=SHIPPING_COST_COLUMN,
        category_large_column=CATEGORY_LARGE_COLUMN,
        category_middle_column=CATEGORY_MIDDLE_COLUMN,
        category_small_column=CATEGORY_SMALL_COLUMN,
    )


def build_incremental_payload(
    sheet_name: str,
    row_num: int,
    product_info: Dict[str, str],
    existing_values: Dict[str, str],
) -> List[Dict[str, object]]:
    """기존 값이 비어 있는 셀만 채우는 payload를 구성한다"""
    return svc_build_incremental_payload(
        sheet_name=sheet_name,
        row_num=row_num,
        row_start=ROW_START,
        product_info=product_info,
        existing_values=existing_values,
        sequence_column=SEQUENCE_COLUMN,
        brand_column=BRAND_COLUMN,
        brand_en_column=BRAND_EN_COLUMN,
        product_name_kr_column=PRODUCT_NAME_KR_COLUMN,
        musinsa_sku_column=MUSINSA_SKU_COLUMN,
        color_kr_column=COLOR_KR_COLUMN,
        size_column=SIZE_COLUMN,
        actual_size_column=ACTUAL_SIZE_COLUMN,
        price_column=PRICE_COLUMN,
        buyma_sell_price_column=BAIMA_SELL_PRICE_COLUMN,
        image_paths_column=IMAGE_PATHS_COLUMN,
        shipping_cost_column=SHIPPING_COST_COLUMN,
        category_large_column=CATEGORY_LARGE_COLUMN,
        category_middle_column=CATEGORY_MIDDLE_COLUMN,
        category_small_column=CATEGORY_SMALL_COLUMN,
    )


def row_needs_update(existing_values: Dict[str, str], require_image_paths: bool = True) -> bool:
    """자동 입력 대상 열 중 빈 칸이 있으면 True.

    require_image_paths=False면 N열(image_paths) 빈칸은 대상에서 제외한다.
    """
    return svc_row_needs_update(
        existing_values=existing_values,
        require_image_paths=require_image_paths,
        brand_column=BRAND_COLUMN,
        brand_en_column=BRAND_EN_COLUMN,
        product_name_kr_column=PRODUCT_NAME_KR_COLUMN,
        musinsa_sku_column=MUSINSA_SKU_COLUMN,
        color_kr_column=COLOR_KR_COLUMN,
        size_column=SIZE_COLUMN,
        actual_size_column=ACTUAL_SIZE_COLUMN,
        price_column=PRICE_COLUMN,
        buyma_sell_price_column=BAIMA_SELL_PRICE_COLUMN,
        shipping_cost_column=SHIPPING_COST_COLUMN,
        image_paths_column=IMAGE_PATHS_COLUMN,
    )


def row_has_existing_output(existing_values: Dict[str, str]) -> bool:
    """자동 입력 대상 열에 이미 값이 하나라도 있으면 True"""
    return svc_row_has_existing_output(
        existing_values=existing_values,
        brand_column=BRAND_COLUMN,
        brand_en_column=BRAND_EN_COLUMN,
        product_name_kr_column=PRODUCT_NAME_KR_COLUMN,
        musinsa_sku_column=MUSINSA_SKU_COLUMN,
        color_kr_column=COLOR_KR_COLUMN,
        size_column=SIZE_COLUMN,
        actual_size_column=ACTUAL_SIZE_COLUMN,
        price_column=PRICE_COLUMN,
        buyma_sell_price_column=BAIMA_SELL_PRICE_COLUMN,
        image_paths_column=IMAGE_PATHS_COLUMN,
        shipping_cost_column=SHIPPING_COST_COLUMN,
    )


def row_needs_image_download(existing_values: Dict[str, str]) -> bool:
    """N열(image_paths)이 비어있으면 이미지 저장 대상으로 본다."""
    return svc_row_needs_image_download(existing_values, IMAGE_PATHS_COLUMN)


def write_image_paths_only(
    service,
    sheet_name: str,
    row_num: int,
    image_paths: str,
    existing_values: Dict[str, str] = None,
):
    """이미지 저장 모드는 N열(image_paths)만 업데이트한다."""
    if is_empty_cell(image_paths):
        print(f" {sheet_name} {row_num}행: 저장할 이미지 경로가 없어 N열 업데이트를 건너뜁니다")
        return

    if existing_values is None:
        existing_values = get_existing_row_values(service, sheet_name, row_num)

    if not is_empty_cell(existing_values.get(IMAGE_PATHS_COLUMN, "")):
        print(f" {sheet_name} {row_num}행: N열이 이미 채워져 있어 건너뜁니다")
        return

    success = svc_update_value_by_range(
        service=service,
        spreadsheet_id=SPREADSHEET_ID,
        range_a1=f"'{sheet_name}'!{IMAGE_PATHS_COLUMN}{row_num}",
        value=image_paths,
    )
    if success:
        print(f" {sheet_name} {row_num}행 저장: N열(image_paths) 업데이트")
    else:
        print(f" {sheet_name} {row_num}행 N열 저장 실패")


def write_to_sheet(
    service,
    sheet_name: str,
    row_num: int,
    product_info: Dict[str, str],
    existing_values: Dict[str, str] = None,
):
    """Google Sheets의 A, C~O 열에 한 행 데이터를 쓴다"""
    try:
        if product_info is not None and not isinstance(product_info, dict):
            if is_dataclass(product_info):
                product_info = asdict(product_info)
            elif hasattr(product_info, "to_dict"):
                product_info = product_info.to_dict()
            else:
                product_info = {}
        if existing_values is None:
            existing_values = get_existing_row_values(service, sheet_name, row_num)
        updates = build_incremental_payload(sheet_name, row_num, product_info, existing_values)

        if not updates:
            print(f" {sheet_name} {row_num}행: 기존 값이 있어 새로 쓸 내용이 없습니다")
            return

        success = svc_batch_update_values(
            service=service,
            spreadsheet_id=SPREADSHEET_ID,
            updates=updates,
        )
        if success:
            print(
                f" {sheet_name} {row_num}행 저장: "
                f"{len(updates)}개 셀 업데이트"
            )
        else:
            print(f" {sheet_name} {row_num}행 저장 실패")
    except Exception as e:
        print(f" {sheet_name} {row_num}행 저장 실패: {e}")


def process_sheet_once(
    service,
    driver,
    sheet_name: str,
    watch_mode: bool = False,
    download_images: bool = False,
    make_thumbnails: bool = False,
):
    """단일 시트를 1회 스캔하여 필요한 행만 처리"""
    api = {
        "read_urls_from_sheet": read_urls_from_sheet,
        "get_sheet_header_map": get_sheet_header_map,
        "get_existing_rows_bulk": get_existing_rows_bulk,
        "get_rows_dynamic_values_bulk": get_rows_dynamic_values_bulk,
        "parse_margin_rate": parse_margin_rate,
        "is_thumbnail_ready_status": is_thumbnail_ready_status,
        "is_image_ready_status": is_image_ready_status,
        "row_needs_image_download": row_needs_image_download,
        "row_needs_update": row_needs_update,
        "is_empty_cell": is_empty_cell,
        "is_crawler_ready_status": is_crawler_ready_status,
        "update_cell_by_header": update_cell_by_header,
        "resolve_image_folder_from_paths": resolve_image_folder_from_paths,
        "build_thumbnail_brand": build_thumbnail_brand,
        "create_thumbnail_for_folder": create_thumbnail_for_folder,
        "scrape_musinsa_product": scrape_musinsa_product,
        "write_image_paths_only": write_image_paths_only,
        "build_image_folder_name": build_image_folder_name,
        "download_brand_logo": download_brand_logo,
        "read_shipping_table": read_shipping_table,
        "estimate_weight": estimate_weight,
        "lookup_shipping_cost": lookup_shipping_cost,
        "write_to_sheet": write_to_sheet,
        "get_row_dynamic_values": get_row_dynamic_values,
        "determine_progress_status": determine_progress_status,
        "get_existing_row_values": get_existing_row_values,
    }
    cfg = {
        "MARGIN_RATE_HEADER": MARGIN_RATE_HEADER,
        "PROGRESS_STATUS_HEADER": PROGRESS_STATUS_HEADER,
        "SHIPPING_COST_COLUMN": SHIPPING_COST_COLUMN,
        "STATUS_COMPLETED": STATUS_COMPLETED,
        "STATUS_UPLOAD_READY": STATUS_UPLOAD_READY,
        "IMAGE_PATHS_COLUMN": IMAGE_PATHS_COLUMN,
        "STATUS_THUMBNAILING": STATUS_THUMBNAILING,
        "STATUS_THUMBNAILS_DONE": STATUS_THUMBNAILS_DONE,
        "STATUS_ERROR": STATUS_ERROR,
        "THUMB_ROW_DELAY_SECONDS": THUMB_ROW_DELAY_SECONDS,
        "MUSINSA_SKU_COLUMN": MUSINSA_SKU_COLUMN,
        "STATUS_DOWNLOADING": STATUS_DOWNLOADING,
        "STATUS_IMAGES_SAVED": STATUS_IMAGES_SAVED,
        "IMAGE_ROW_DELAY_SECONDS": IMAGE_ROW_DELAY_SECONDS,
        "STATUS_CRAWLING": STATUS_CRAWLING,
        "STATUS_HOLD": STATUS_HOLD,
        "STATUS_CRAWLED": STATUS_CRAWLED,
        "CRAWLER_ROW_DELAY_SECONDS": CRAWLER_ROW_DELAY_SECONDS,
    }
    return svc_process_sheet_once(
        service=service,
        driver=driver,
        sheet_name=sheet_name,
        watch_mode=watch_mode,
        download_images=download_images,
        make_thumbnails=make_thumbnails,
        api=api,
        cfg=cfg,
    )


def parse_args():
    """실행 옵션 파싱"""
    parser = argparse.ArgumentParser(description="Musinsa -> Google Sheets 자동화")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="감시 모드: 일정 주기로 시트를 확인해 새 링크/빈 칸을 자동 처리",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=WATCH_INTERVAL_SECONDS,
        help="감시 모드 조회 주기(초), 기본값 20",
    )
    parser.add_argument(
        "--data-dir",
        default="",
        help="런타임 데이터 폴더(이미지/기타 파일). 기본값: LOCALAPPDATA/auto_shop",
    )
    parser.add_argument(
        "--credentials-file",
        default="",
        help="Google 서비스 계정 credentials.json 절대/상대 경로",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="바이마 출품 모드: 시트 데이터로 바이마에 상품 출품",
    )
    parser.add_argument(
        "--upload-row",
        type=int,
        default=0,
        help="바이마 출품 시 특정 행만 처리 (예: --upload-row 3)",
    )
    parser.add_argument(
        "--download-images",
        action="store_true",
        help="링크 기반 이미지를 로컬에 저장하고 N열(image_paths)을 채움",
    )
    parser.add_argument(
        "--make-thumbnails",
        action="store_true",
        help="진행상태가 '썸네일진행대기'인 행의 이미지 폴더로 썸네일을 자동 생성",
    )
    return parser.parse_args()


def setup_chrome_driver():
    """Chrome WebDriver 설정"""
    return svc_setup_chrome_driver(headless=HEADLESS)


def normalize_price(text: str) -> str:
    """가격 문자열에서 숫자만 추출하여 정상화"""
    return svc_normalize_price(text)


def extract_discounted_product_price(soup: BeautifulSoup) -> str:
    """페이지에서 쿠폰가를 제외한 상품 할인판매가를 추출한다"""
    return svc_extract_discounted_product_price(soup)


def extract_yen_values(text: str) -> List[int]:
    """문자열에서 엔화 금액 후보를 정수 목록으로 추출한다"""
    return svc_extract_yen_values(text)


def extract_buyma_listing_prices(soup: BeautifulSoup) -> List[int]:
    """BUYMA 검색 첫 페이지에서 셀러 상품 카드의 가격만 추출한다"""
    return svc_extract_buyma_listing_prices(soup)


def extract_buyma_listing_entries(soup: BeautifulSoup) -> List[Dict[str, object]]:
    """BUYMA 검색 첫 페이지에서 상품카드의 제목/가격/링크를 함께 추출한다"""
    return svc_extract_buyma_listing_entries(soup)


def extract_buyma_shipping_included_prices(soup: BeautifulSoup) -> List[int]:
    """검색 페이지 텍스트에서 '¥xx,xxx 送料込' 형태 가격을 추출한다"""
    return svc_extract_buyma_shipping_included_prices(soup)


def extract_buyma_item_page_price(soup: BeautifulSoup) -> int:
    """BUYMA 상품 상세 페이지에서 판매가격을 추출한다"""
    return svc_extract_buyma_item_page_price(soup)


def is_relevant_buyma_item(
    soup: BeautifulSoup,
    musinsa_sku: str,
    english_name: str,
    brand: str,
) -> bool:
    """BUYMA 상세 페이지가 현재 상품과 관련 있는지 판별한다"""
    return svc_is_relevant_buyma_item(soup, musinsa_sku, english_name, brand)


def is_relevant_buyma_listing_entry(
    title: str,
    musinsa_sku: str,
    english_name: str,
    brand: str,
) -> bool:
    """검색 결과 카드 제목이 현재 상품과 관련 있는지 더 엄격하게 판별한다."""
    return svc_is_relevant_buyma_listing_entry(title, musinsa_sku, english_name, brand)


def normalize_buyma_query(product_name: str, brand: str) -> List[str]:
    """바이마 검색용 질의를 우선순위 순으로 생성한다
    SKU 형태 > 상품명+브랜드 > 상품명 순서로 우선도 결정"""
    return svc_normalize_buyma_query(product_name, brand)


def fetch_buyma_lowest_price(driver, product_name: str, brand: str, musinsa_sku: str = "") -> str:
    """품번 우선으로 BUYMA 첫 페이지를 검색해 최저가를 반환하고, 실패 시 이름 검색으로 재시도한다"""
    return svc_fetch_buyma_lowest_price(driver, product_name, brand, musinsa_sku)


def extract_musinsa_categories(soup: BeautifulSoup, mss_state: Dict[str, object]) -> Tuple[str, str, str]:
    """무신사 상품 페이지에서 대/중/소 분류를 추출한다."""
    return svc_extract_musinsa_categories(soup, mss_state)


def _normalize_gender_label(raw_value: str) -> str:
    return svc_normalize_gender_label(raw_value)


def extract_musinsa_gender_large(
    mss_state: Dict[str, object],
    cat_large: str = "",
    cat_middle: str = "",
    cat_small: str = "",
) -> str:
    """무신사 상태값/카테고리 텍스트에서 성별 대분류(남성/여성)를 추출한다."""
    return svc_extract_musinsa_gender_large(
        mss_state=mss_state,
        cat_large=cat_large,
        cat_middle=cat_middle,
        cat_small=cat_small,
    )


def remap_categories_with_gender(
    gender_large: str,
    cat_large: str,
    cat_middle: str,
    cat_small: str,
) -> Tuple[str, str, str]:
    """성별을 대분류로 고정하고, 나머지 카테고리를 중/소로 재배치한다."""
    return svc_remap_categories_with_gender(
        gender_large=gender_large,
        cat_large=cat_large,
        cat_middle=cat_middle,
        cat_small=cat_small,
    )


def scrape_musinsa_product(
    driver,
    url: str,
    row_num: int,
    existing_sku: str = "",
    download_images: bool = False,
    images_only: bool = False,
) -> Product:
    """Selenium을 사용하여 무신사 상품 페이지에서 정보를 추출한다."""
    return svc_scrape_musinsa_product(
        driver=driver,
        url=url,
        row_num=row_num,
        existing_sku=existing_sku,
        download_images=download_images,
        images_only=images_only,
        crawl_page_settle_seconds=CRAWL_PAGE_SETTLE_SECONDS,
        max_thumbnail_images=MAX_THUMBNAIL_IMAGES,
        download_images_fn=download_thumbnail_images,
        fetch_buyma_lowest_price_fn=fetch_buyma_lowest_price,
    )


def main():
    args = parse_args()
    initialize_runtime_paths(args.data_dir, args.credentials_file)

    # 바이마 출품 모드
    if args.upload:
        from buyma_upload import upload_products
        upload_products(specific_row=args.upload_row)
        return

    print("Starting Musinsa data extraction")
    service = get_sheets_service()
    sheet_names = get_target_sheet_names(service)

    if args.make_thumbnails:
        if args.watch:
            interval = max(5, int(args.interval))
            print(f"썸네일 워커 감시 시작: {interval}초 간격")
            while True:
                for sheet_name in sheet_names:
                    process_sheet_once(
                        service,
                        driver=None,
                        sheet_name=sheet_name,
                        watch_mode=True,
                        download_images=False,
                        make_thumbnails=True,
                    )
                print(f"다음 확인까지 {interval}초 대기...")
                time.sleep(interval)
        for sheet_name in sheet_names:
            process_sheet_once(
                service,
                driver=None,
                sheet_name=sheet_name,
                watch_mode=False,
                download_images=False,
                make_thumbnails=True,
            )
        print("모든 시트 썸네일 처리가 완료되었습니다.")
        return

    driver = setup_chrome_driver()
    try:
        if args.watch:
            interval = max(5, int(args.interval))
            print(f"감시 모드 시작: {interval}초 간격으로 새 링크를 확인합니다.")
            while True:
                for sheet_name in sheet_names:
                    process_sheet_once(
                        service,
                        driver,
                        sheet_name,
                        watch_mode=True,
                        download_images=args.download_images,
                    )
                print(f"다음 확인까지 {interval}초 대기...")
                time.sleep(interval)
        else:
            for sheet_name in sheet_names:
                process_sheet_once(
                    service,
                    driver,
                    sheet_name,
                    watch_mode=False,
                    download_images=args.download_images,
                )
            print("모든 시트 처리가 완료되었습니다.")
    finally:
        driver.quit()
        print("브라우저를 종료합니다.")


if __name__ == "__main__":
    main()
