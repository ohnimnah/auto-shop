"""
무신사 상품 정보를 크롤링하여 Google Sheets에 자동으로 입력하는 자동화 스크립트
아래 링크의 스프레드시트 구조와 동일하게 사용할 수 있도록 데이터를 입력합니다.
- 시트 ID: 1mTV-Fcybov-0uC7tNyM_GXGDoth8F_7wM__zaC1fAjs
- 탭 GID: 1698424449
"""

import json
import argparse
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

# Windows cp949 터미널에서 유니코드 출력 오류 방지
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") in ("cp949", "euckr"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# SSL 경고 무시
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 설정 부분 ====================
SPREADSHEET_ID = "1mTV-Fcybov-0uC7tNyM_GXGDoth8F_7wM__zaC1fAjs"
# 링크의 탭 GID 목록을 적어주세요. 서비스 계정이 해당 스프레드시트에 권한이 있어야 동작합니다.
SHEET_GIDS = [1698424449]
# GID를 사용하지 않을 때는 아래 default sheet name을 설정합니다.
SHEET_NAME = "시트1"
HEADER_ROW = 1
MARGIN_RATE_HEADER = "마진률"
PROGRESS_STATUS_HEADER = "진행상태"
MARGIN_THRESHOLD_PERCENT = 9.0
STATUS_HOLD = "보류"
# 레거시 호환용 상태 (읽기 전용)
STATUS_WAITING = "대기"
STATUS_IMAGE_READY = "이미지진행대기"
STATUS_THUMBNAIL_READY = "썸네일진행대기"
STATUS_UPLOAD_READY = "업로드진행대기"
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
IMAGE_PATHS_COLUMN = "N"
SHIPPING_COST_COLUMN = "O"
CATEGORY_LARGE_COLUMN = "V"
CATEGORY_MIDDLE_COLUMN = "W"
CATEGORY_SMALL_COLUMN = "X"
ROW_START = 2


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

# 상품명 키워드 → 추정 무게(kg)  (X열 예시 기반, 무거운 것부터 매칭)
KEYWORD_WEIGHT_RULES: List[Tuple[List[str], float]] = [
    (['패딩', '다운', '점퍼', '코트', '무스탕', '파카', 'padding', 'down', 'coat', 'parka', 'puffer'], 2.5),
    (['겨울신발', '부츠', '워커', 'boots', 'boot', 'walker'], 3.5),
    (['가방', '백팩', '캐리어', '토트백', '숄더백', '크로스백', 'bag', 'backpack', 'tote', 'shoulder', 'crossbody', 'carrier'], 3.5),
    (['후드', '맨투맨', '스웨트', '니트', '집업', 'hoodie', 'sweatshirt', 'sweat', 'knit', 'cardigan', 'zip-up', 'zipup'], 1.5),
    (['자켓', '블레이저', '블루종', '바람막이', '아우터', 'jacket', 'blazer', 'blouson', 'windbreaker', 'outer'], 2.0),
    (['바지', '팬츠', '청바지', '데님', '슬랙스', '조거', '트랙', 'pants', 'jeans', 'denim', 'slacks', 'jogger', 'track'], 1.0),
    (['원피스', '드레스', 'dress', 'onepiece'], 1.0),
    (['셔츠', '블라우스', 'shirt', 'blouse'], 0.5),
    (['티셔츠', '반팔', '긴팔', '탑', '티', 't-shirt', 'tee', 'top', 'long sleeve', 'short sleeve'], 1.0),
    (['운동화', '스니커즈', '슬리퍼', '샌들', '로퍼', '플랫', '슈즈', '클로그', 'sneakers', 'sneaker', 'slipper', 'sandals', 'loafer', 'flat', 'shoes', 'clog'], 1.5),
    (['레깅스', '스타킹', '양말', '속옷', 'leggings', 'stocking', 'socks', 'underwear', 'bra', 'panty'], 0.5),
    (['모자', '캡', '버킷햇', '비니', 'hat', 'cap', 'bucket hat', 'beanie'], 0.5),
    (['안경', '선글라스', '장갑', '머플러', '스카프', '벨트', '지갑', '케이스', '키링', 'glasses', 'sunglasses', 'glove', 'muffler', 'scarf', 'belt', 'wallet', 'case', 'keyring'], 0.5),
]
# optKindCd 기반 기본 무게 (키워드 매칭 실패 시)
OPT_KIND_WEIGHT_MAP = {
    'SHOES': 1.5,
    'BAG': 3.5,
    'ACC': 0.5,
    'CLOTHES': 1.2,
    'OUTER': 2.5,
    'TOP': 1.0,
    'BOTTOM': 1.0,
    'DRESS': 1.0,
    'UNDERWEAR': 0.5,
}
DEFAULT_WEIGHT_KG = 1.0
MAX_THUMBNAIL_IMAGES = 10

# Selenium 설정
HEADLESS = True  # True = 백그라운드 실행, False = 브라우저 창 보기

# 감시 모드 기본값(초)
WATCH_INTERVAL_SECONDS = 20


def get_default_data_dir() -> str:
    """기본 런타임 데이터 경로를 OS별로 반환한다"""
    local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
    if local_app_data:
        return os.path.join(local_app_data, 'auto_shop')
    return os.path.join(os.path.expanduser('~'), '.auto_shop')


def get_default_images_dir() -> str:
    """기본 이미지 저장 경로를 반환한다 (홈 디렉토리 하위 images 폴더)"""
    env_images_dir = os.environ.get('AUTO_SHOP_IMAGES_DIR', '').strip()
    if env_images_dir:
        return os.path.abspath(os.path.expanduser(env_images_dir))
    return os.path.join(os.path.expanduser('~'), 'images')


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
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!Z1:AB60"
        ).execute()
        rows = result.get('values', [])
        table: List[Tuple[float, int]] = []
        for row in rows:
            if len(row) < 2:
                continue
            weight_str = row[0].strip()
            # 숫자 행만 파싱 (헤더/비고 스킵)
            try:
                weight = float(weight_str)
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
    except Exception as e:
        print(f" 배송비 기준표 조회 실패: {e}")
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
    if index < 0:
        raise ValueError("열 인덱스는 0 이상이어야 합니다.")
    result = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_sheet_header_map(service, sheet_name: str) -> Dict[str, int]:
    """1행 헤더명을 읽어 헤더명 -> 0-based 열 인덱스 맵을 반환한다."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!{HEADER_ROW}:{HEADER_ROW}"
        ).execute()
        header_row = result.get('values', [[]])[0] if result.get('values') else []
        header_map: Dict[str, int] = {}
        for idx, value in enumerate(header_row):
            header = (value or '').strip()
            if header:
                header_map[header] = idx
        return header_map
    except Exception as e:
        print(f" 헤더 조회 실패 ({sheet_name}): {e}")
        return {}


def get_row_dynamic_values(
    service,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_names: List[str],
) -> Dict[str, str]:
    """헤더명 기준으로 특정 행의 동적 컬럼 값을 읽는다."""
    target_indexes = [header_map[name] for name in header_names if name in header_map]
    if not target_indexes:
        return {}

    min_index = min(target_indexes)
    max_index = max(target_indexes)
    start_col = column_index_to_letter(min_index)
    end_col = column_index_to_letter(max_index)

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!{start_col}{row_num}:{end_col}{row_num}"
        ).execute()
        row = result.get('values', [[]])[0] if result.get('values') else []
    except Exception as e:
        print(f" {sheet_name} {row_num}행 동적 컬럼 조회 실패: {e}")
        return {}

    values: Dict[str, str] = {}
    for name in header_names:
        idx = header_map.get(name)
        if idx is None:
            continue
        offset = idx - min_index
        values[name] = row[offset].strip() if offset < len(row) and row[offset] else ""
    return values


def update_cell_by_header(
    service,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_name: str,
    value: str,
) -> bool:
    """헤더명 기준으로 특정 셀 값을 업데이트한다."""
    col_index = header_map.get(header_name)
    if col_index is None:
        return False

    try:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!{column_index_to_letter(col_index)}{row_num}",
            valueInputOption='USER_ENTERED',
            body={'values': [[value]]},
        ).execute()
        return True
    except Exception as e:
        print(f" {sheet_name} {row_num}행 {header_name} 업데이트 실패: {e}")
        return False


def parse_margin_rate(value: str) -> float | None:
    """마진률 셀 문자열을 퍼센트 숫자로 변환한다."""
    text = (value or '').strip()
    if not text:
        return None

    has_percent = '%' in text
    cleaned = re.sub(r'[^0-9.\-]', '', text)
    if not cleaned:
        return None

    try:
        parsed = float(cleaned)
    except ValueError:
        return None

    if has_percent:
        return parsed
    if 0 <= parsed <= 1:
        return parsed * 100
    return parsed


def determine_progress_status(margin_rate: float | None) -> str:
    """마진률 기준으로 다음 진행상태를 계산한다."""
    if margin_rate is not None and margin_rate < MARGIN_THRESHOLD_PERCENT:
        return STATUS_HOLD
    return STATUS_CRAWLED


def is_crawler_ready_status(status: str) -> bool:
    normalized = (status or "").strip()
    # 신규만 정찰 대상으로 삼되, 기존 데이터 호환을 위해 일부 레거시 값을 허용
    return normalized in {"", STATUS_WAITING, STATUS_NEW, "NEW"}


def is_image_ready_status(status: str) -> bool:
    normalized = (status or "").strip()
    return normalized in {STATUS_CRAWLED, "CRAWLED", STATUS_IMAGE_READY}


def is_thumbnail_ready_status(status: str) -> bool:
    normalized = (status or "").strip()
    return normalized in {STATUS_IMAGES_SAVED, "IMAGES_SAVED", STATUS_THUMBNAIL_READY}


def resolve_image_folder_from_paths(image_paths: str) -> str:
    """콤마 구분 image_paths에서 첫 이미지의 폴더 경로를 반환한다."""
    parts = [part.strip() for part in (image_paths or "").split(",") if part.strip()]
    if not parts:
        return ""
    first_path = os.path.abspath(os.path.expanduser(parts[0].replace('/', os.sep)))
    return os.path.dirname(first_path)


def build_thumbnail_brand(existing_values: Dict[str, str]) -> str:
    """썸네일용 브랜드명을 우선순위대로 반환한다."""
    brand = (existing_values.get(BRAND_EN_COLUMN, "") or "").strip()
    if brand:
        return brand
    brand = (existing_values.get(BRAND_COLUMN, "") or "").strip()
    return brand or "BRAND"


def create_thumbnail_for_folder(folder_path: str, brand: str) -> bool:
    """이미지 폴더에서 썸네일을 생성한다."""
    folder = os.path.abspath(os.path.expanduser(folder_path))
    if not os.path.isdir(folder):
        print(f"    썸네일 스킵: 폴더가 없습니다 -> {folder}")
        return False

    style = random.choice(["split", "banner"])
    footer = f"{brand} / angduss k-closet"
    command = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "make_thumbnails.py"),
        folder,
        "--style",
        style,
        "--brand",
        brand,
        "--footer",
        footer,
        "--blur-face",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.stdout.strip():
            print(completed.stdout.strip())
        if completed.stderr.strip():
            print(completed.stderr.strip())
        thumb_path = os.path.join(folder, "00_thumb_main.jpg")
        if completed.returncode == 0 and os.path.exists(thumb_path):
            print(f"    썸네일 생성 완료: {thumb_path} ({style})")
            return True
        print(f"    썸네일 생성 실패 (코드 {completed.returncode})")
        return False
    except Exception as e:
        print(f"    썸네일 생성 오류: {e}")
        return False

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
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        for sheet in spreadsheet.get('sheets', []):
            props = sheet.get('properties', {})
            if props.get('sheetId') == gid:
                return props.get('title')
    except Exception as e:
        print(f" 시트 메타데이터 조회 실패: {e}")
    return ""


def get_target_sheet_names(service) -> List[str]:
    """SHEET_GIDS로 시트 이름을 찾거나 default sheet name을 반환"""
    sheet_names = []
    for gid in SHEET_GIDS:
        title = get_sheet_name_by_gid(service, gid)
        if title:
            sheet_names.append(title)
        else:
            print(f" GID {gid}에 해당하는 시트 이름을 찾을 수 없습니다")

    if not sheet_names:
        sheet_names = [SHEET_NAME]
        print(f" GID 기반 시트 이름 찾기에 실패했습니다. 기본 시트 이름 '{SHEET_NAME}'을(를) 사용합니다.")
    return sheet_names


def is_url_cell(value: str) -> bool:
    """셀값이 URL인지 감지"""
    if not isinstance(value, str):
        return False
    value = value.strip()
    return value.startswith('http://') or value.startswith('https://')


def read_urls_from_sheet(service, sheet_name: str) -> List[Tuple[int, str]]:
    """Google Sheets에서 URL을 읽어 row 번호와 URL 목록을 반환"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!{URL_COLUMN}{ROW_START}:{URL_COLUMN}1000"
        ).execute()
        values = result.get('values', [])
        rows = []
        for index, row in enumerate(values, start=ROW_START):
            if row and row[0].strip():
                url = row[0].strip()
                if is_url_cell(url):
                    rows.append((index, url))
        return rows
    except Exception as e:
        print(f" URL read failed ({sheet_name}): {e}")
        return []


def has_hangul(text: str) -> bool:
    """문자열에 한글이 포함되어 있는지 확인"""
    return any('\uac00' <= char <= '\ud7a3' for char in text)


def fetch_json(url: str) -> Dict[str, object]:
    """JSON API를 호출한다"""
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def sanitize_path_component(value: str) -> str:
    """파일/폴더명으로 안전한 문자열로 정리한다"""
    cleaned = re.sub(r'[\\/:*?"<>|]+', '_', (value or '').strip())
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip(' ._') or 'item'


def build_image_folder_name(row_num: int, product_name: str) -> str:
    """이미지 폴더명을 '행번호. 상품명' 형식으로 만든다"""
    display_index = max(1, row_num - ROW_START + 1)
    safe_name = sanitize_path_component(product_name or '상품명 미확인')
    return f"{display_index}. {safe_name}"


def normalize_image_source(src: str) -> str:
    """무신사 이미지 URL을 다운로드 가능한 형태로 정규화한다"""
    if not src:
        return ""

    normalized = src.strip()
    if normalized.startswith('//'):
        normalized = f"https:{normalized}"
    elif normalized.startswith('/'):
        normalized = f"https://image.msscdn.net{normalized}"

    normalized = normalized.split('?')[0]
    normalized = normalized.replace('https://image.msscdn.net/thumbnails/', 'https://image.msscdn.net/')
    normalized = normalized.replace('/thumbnails/', '/')
    return normalized


def build_image_identity_key(image_url: str) -> str:
    """같은 원본 사진의 다른 사이즈 URL을 하나로 묶기 위한 키를 만든다"""
    normalized = normalize_image_source(image_url)
    parsed = urllib.parse.urlparse(normalized)
    path = parsed.path.lower()
    path = re.sub(r'_(?:60|80|125|250|500|big)(\.[a-z0-9]+)$', r'\1', path)
    return path


def extract_musinsa_thumbnail_urls(
    soup: BeautifulSoup,
    product_json: Dict[str, object],
    goods_no: str,
) -> List[str]:
    """무신사 상품 페이지에서 이미지 URL 목록을 추출한다"""
    candidates: List[str] = []
    seen_urls = set()
    seen_images = set()

    def add_candidate(src: str):
        normalized = normalize_image_source(src)
        if not normalized or normalized in seen_urls:
            return
        if 'goods_img' not in normalized and 'prd_img' not in normalized:
            return
        if goods_no and goods_no not in normalized:
            return
        identity_key = build_image_identity_key(normalized)
        if identity_key in seen_images:
            return
        seen_urls.add(normalized)
        seen_images.add(identity_key)
        candidates.append(normalized)

    if isinstance(product_json, dict):
        image_field = product_json.get('image')
        if isinstance(image_field, str):
            add_candidate(image_field)
        elif isinstance(image_field, list):
            for item in image_field:
                if isinstance(item, str):
                    add_candidate(item)

    og_image = soup.select_one('meta[property="og:image"]')
    if og_image:
        add_candidate(og_image.get('content', ''))

    for img in soup.select('img'):
        for attr in ('src', 'data-src', 'data-original', 'data-lazy-src'):
            src = img.get(attr, '')
            if not src:
                continue
            if goods_no and goods_no not in src:
                continue
            add_candidate(src)

    return candidates[:MAX_THUMBNAIL_IMAGES]


def download_thumbnail_images(image_urls: List[str], folder_name: str) -> str:
    """이미지를 로컬 images 폴더에 저장하고 상대 경로 목록을 반환한다"""
    if not image_urls:
        return ""

    from datetime import date as _date
    date_folder = _date.today().strftime("%Y%m%d")
    image_dir = os.path.join(IMAGES_ROOT, date_folder, sanitize_path_component(folder_name))
    os.makedirs(image_dir, exist_ok=True)

    saved_paths: List[str] = []
    for index, image_url in enumerate(image_urls[:MAX_THUMBNAIL_IMAGES], start=1):
        try:
            parsed = urllib.parse.urlparse(image_url)
            ext = os.path.splitext(parsed.path)[1].lower()
            if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
                ext = '.jpg'

            file_name = f"{index:02d}{ext}"
            file_path = os.path.join(image_dir, file_name)
            request = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                with open(file_path, 'wb') as image_file:
                    image_file.write(response.read())

            saved_paths.append(file_path.replace('\\', '/'))
        except Exception as image_error:
            print(f"    이미지 다운로드 스킵: {image_error}")

    return ','.join(saved_paths)


def extract_brand_logo_url(soup: BeautifulSoup, product_json: Dict[str, object]) -> str:
    """Extract brand logo URL from Musinsa page/json."""
    candidates: List[str] = []

    def add_candidate(src: str):
        normalized = normalize_image_source(src or "")
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    if isinstance(product_json, dict):
        brand_obj = product_json.get('brand')
        if isinstance(brand_obj, dict):
            for key in ('logoImageUrl', 'logoImage', 'logoUrl', 'logo', 'imageUrl', 'image', 'thumbnail'):
                val = brand_obj.get(key)
                if isinstance(val, str):
                    add_candidate(val)

    for img in soup.select('a[href*="/brand/"] img'):
        for attr in ('src', 'data-src', 'data-original', 'data-lazy-src'):
            src = img.get(attr, '')
            if src:
                add_candidate(src)

    for m in soup.select('meta[property="og:image"], meta[name="twitter:image"]'):
        src = m.get('content', '')
        if src and ('brand' in src.lower() or 'logo' in src.lower()):
            add_candidate(src)

    for url in candidates:
        lower = url.lower()
        if 'brand' in lower or 'logo' in lower:
            return url
    return candidates[0] if candidates else ""


def download_brand_logo(logo_url: str, folder_name: str, image_paths: str = "") -> str:
    """Save brand logo as __brand_logo.* in product image folder."""
    if not logo_url:
        return ""

    image_dir = resolve_image_folder_from_paths(image_paths)
    if not image_dir:
        from datetime import date as _date
        date_folder = _date.today().strftime("%Y%m%d")
        image_dir = os.path.join(IMAGES_ROOT, date_folder, sanitize_path_component(folder_name))
    os.makedirs(image_dir, exist_ok=True)

    try:
        parsed = urllib.parse.urlparse(logo_url)
        ext = os.path.splitext(parsed.path)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
            ext = '.png'
        logo_path = os.path.join(image_dir, f"__brand_logo{ext}")
        request = urllib.request.Request(logo_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            with open(logo_path, 'wb') as f:
                f.write(response.read())
        print(f"    브랜드 로고 저장: {logo_path}")
        return logo_path.replace('\\', '/')
    except Exception as e:
        print(f"    브랜드 로고 저장 실패: {e}")
        return ""


COLOR_NAME_MAP = None


def get_color_name_map() -> Dict[str, str]:
    """무신사 색상 코드표를 가져온다"""
    global COLOR_NAME_MAP
    if COLOR_NAME_MAP is not None:
        return COLOR_NAME_MAP

    try:
        payload = fetch_json('https://goods-detail.musinsa.com/api2/goods/color-images')
        color_images = payload.get('data', {}).get('colorImages', [])
        COLOR_NAME_MAP = {
            str(item.get('colorId')): str(item.get('colorName', '')).strip()
            for item in color_images
            if item.get('colorId') is not None and item.get('colorName')
        }
    except Exception:
        COLOR_NAME_MAP = {}
    return COLOR_NAME_MAP


def fetch_goods_options(goods_no: str, goods_sale_type: str, opt_kind_cd: str) -> Dict[str, object]:
    """상품 옵션 정보를 가져온다"""
    if not goods_no:
        return {}

    sale_type = goods_sale_type or 'SALE'
    opt_kind = opt_kind_cd or 'CLOTHES'
    url = f'https://goods-detail.musinsa.com/api2/goods/{goods_no}/options?goodsSaleType={sale_type}&optKindCd={opt_kind}'
    try:
        payload = fetch_json(url)
        return payload.get('data', {})
    except Exception:
        return {}


def fetch_actual_size(goods_no: str) -> Dict[str, object]:
    """상품 실측 사이즈 정보를 가져온다"""
    if not goods_no:
        return {}

    url = f'https://goods-detail.musinsa.com/api2/goods/{goods_no}/actual-size'
    try:
        payload = fetch_json(url)
        return payload.get('data', {})
    except Exception:
        return {}


def extract_actual_size_text(goods_no: str) -> str:
    """무신사 실측 API에서 실측표 텍스트를 추출해 한 줄 문자열로 반환한다."""
    data = fetch_actual_size(goods_no)
    if not isinstance(data, dict):
        return ""

    rows = data.get("sizes")
    if not isinstance(rows, list):
        return ""

    result_rows: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        size_name = str(row.get("name", "")).strip()
        values = row.get("values")
        if not isinstance(values, list) or not values:
            # Some Musinsa responses use "items" instead of "values"
            values = row.get("items")
        if not isinstance(values, list) or not values:
            continue

        parts: List[str] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            measure_name = str(item.get("name", "")).strip()
            raw_value = item.get("value", "")
            if isinstance(raw_value, (int, float)):
                measure_value = f"{raw_value:g}"
            else:
                measure_value = str(raw_value).strip()
            if not measure_name or not measure_value:
                continue
            parts.append(f"{measure_name} {measure_value}")

        if not parts:
            continue

        if size_name:
            result_rows.append(f"{size_name}: {', '.join(parts)}")
        else:
            result_rows.append(", ".join(parts))

    return " | ".join(result_rows)


def extract_product_json(soup: BeautifulSoup) -> Dict[str, object]:
    """페이지 내 JSON-LD Product 데이터를 추출한다"""
    for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        raw_text = script.get_text(strip=True)
        if not raw_text:
            continue
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            continue

        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get('@type') == 'Product':
                return candidate
    return {}


def extract_mss_product_state(soup: BeautifulSoup) -> Dict[str, object]:
    """window.__MSS__.product.state 또는 __MSS_FE__.product.state를 추출한다"""
    patterns = [
        r'window\.__MSS__\.product\.state\s*=\s*(\{.*?\});',
        r'window\.__MSS_FE__\.product\.state\s*=\s*(\{.*?\});',
    ]

    for script in soup.find_all('script'):
        script_text = script.get_text(strip=False)
        if not script_text:
            continue

        for pattern in patterns:
            match = re.search(pattern, script_text, re.DOTALL)
            if not match:
                continue
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return {}


def clean_product_name(name: str) -> str:
    """상품명에서 색상/품번 접미부를 제거한다"""
    if not name:
        return "상품명 미확인"

    cleaned = re.sub(r'\s*/\s*[A-Z0-9-]+$', '', name).strip()
    if ' - ' in cleaned:
        cleaned = cleaned.split(' - ', 1)[0].strip()
    cleaned = re.sub(r'\s+(?:M|W|K|FREE|O/S|OS)$', '', cleaned, flags=re.IGNORECASE).strip()
    return cleaned or "상품명 미확인"


def split_name_and_color(raw_name: str) -> Tuple[str, str]:
    """상품명과 색상 접미부를 분리한다"""
    if not raw_name:
        return "", ""

    text = re.sub(r'\s*/\s*[A-Z0-9-]+$', '', raw_name).strip()
    if ' - ' not in text:
        return text, ""

    name_part, color_part = text.split(' - ', 1)
    return name_part.strip(), color_part.strip()


def extract_color_from_name(raw_name: str) -> str:
    """???? ?? ?? ??? ???? ???? ????"""
    if not raw_name:
        return ""

    cleaned = re.sub(r'\s*/\s*[A-Z0-9-]+$', '', raw_name).strip()
    _, color_part = split_name_and_color(cleaned)
    if color_part and not is_color_count_placeholder(color_part):
        return color_part

    bracket_match = re.search(r'\[([^\[\]]{1,50})\]\s*$', cleaned)
    if bracket_match:
        candidate = bracket_match.group(1).strip()
        if not is_color_count_placeholder(candidate):
            return candidate

    paren_match = re.search(r'\(([^()]{1,50})\)\s*$', cleaned)
    if paren_match:
        candidate = paren_match.group(1).strip()
        if (
            not is_color_count_placeholder(candidate)
            and (any(token in candidate for token in ['/', ',', '-', ':']) or has_hangul(candidate))
        ):
            return candidate

    return ""


def is_color_count_placeholder(text: str) -> bool:
    """'2color', '4 colors', '3??' ?? ?? ???? ????."""
    value = (text or "").strip().lower()
    if not value:
        return False
    compact = re.sub(r'\s+', '', value)

    # english patterns: 2color, 4colors, color3, colours2
    if re.fullmatch(r'^\d+(?:color|colors|colour|colours)$', compact):
        return True
    if re.fullmatch(r'^(?:color|colors|colour|colours)\d+$', compact):
        return True

    # korean patterns: 2??, 4??, ??3, ??2
    korean_suffixes = ("\uceec\ub7ec", "\uc0c9\uc0c1")
    m_prefix = re.fullmatch(r'^(\d+)(.+)$', compact)
    if m_prefix and m_prefix.group(2) in korean_suffixes:
        return True
    m_suffix = re.fullmatch(r'^(.+?)(\d+)$', compact)
    if m_suffix and m_suffix.group(1) in korean_suffixes:
        return True
    return False

def normalize_korean_color(color_text: str) -> str:
    """한국어 색상 문자열을 보기 좋게 정리한다"""
    if not color_text:
        return ""

    normalized = color_text.replace(':', ', ')
    normalized = re.sub(r'\s*,\s*', ', ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip(' ,')

    tokens = []
    for token in normalized.split(','):
        value = token.strip()
        if value.endswith('색') and len(value) > 1 and has_hangul(value):
            value = value[:-1].strip()
        if value and not is_color_count_placeholder(value):
            tokens.append(value)

    return ', '.join(tokens)


def normalize_english_color(color_text: str) -> str:
    """영문 색상 문자열을 보기 좋게 정리한다"""
    if not color_text:
        return ""

    normalized = color_text.replace('/', ', ')
    normalized = re.sub(r'\s*-\s*', ', ', normalized)
    normalized = re.sub(r'\s*,\s*', ', ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip(' ,')
    return normalized.title()


def extract_brand_text(product_json: Dict[str, object], title_text: str) -> str:
    """브랜드명을 추출한다"""
    brand = product_json.get('brand', {}) if isinstance(product_json, dict) else {}
    if isinstance(brand, dict) and brand.get('name'):
        return str(brand['name']).strip()

    match = re.match(r'([^()]+)\(', title_text)
    if match:
        return match.group(1).strip()
    return ""


def extract_brand_en_from_musinsa(driver, product_url: str) -> str:
    """무신사 상품 페이지에서 브랜드 영문명을 추출한다.
    상품 페이지의 브랜드 링크(/brand/slug)를 찾아
    브랜드 페이지 og:title에서 '한글(ENGLISH)' 패턴으로 영문명을 가져온다."""
    try:
        brand_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/brand/"]')
        slug = ''
        for bl in brand_links:
            href = bl.get_attribute('href') or ''
            text = bl.text.strip()
            m = re.search(r'/brand/([a-z0-9_-]+)', href)
            if m and text and len(text) < 30 and text != '더보기' and '바로가기' not in text:
                slug = m.group(1)
                break
        if not slug:
            return ''

        # 브랜드 페이지에서 og:title 읽기
        driver.get(f'https://www.musinsa.com/brand/{slug}')
        time.sleep(2)
        og_tags = driver.find_elements(By.CSS_SELECTOR, 'meta[property="og:title"]')
        if og_tags:
            og_title = og_tags[0].get_attribute('content') or ''
            # "한글(ENGLISH)" 패턴에서 영문 추출
            m = re.search(r'\(([A-Za-z0-9\s&\-\.]+)\)', og_title)
            if m:
                return m.group(1).strip()
        # 슬러그를 대문자로 변환하여 반환 (fallback)
        return slug.upper().replace('-', ' ')
    except Exception as e:
        print(f"   영문 브랜드 추출 실패: {e}")
        return ''


def find_longest_step_sequence(values: List[int], allowed_steps: Tuple[int, ...]) -> List[int]:
    """허용된 간격을 갖는 가장 긴 수열을 찾는다"""
    if not values:
        return []

    sorted_values = sorted(set(values))
    best_sequence: List[int] = []
    current_sequence = [sorted_values[0]]

    for value in sorted_values[1:]:
        step = value - current_sequence[-1]
        if step in allowed_steps:
            current_sequence.append(value)
        else:
            if len(current_sequence) > len(best_sequence):
                best_sequence = current_sequence[:]
            current_sequence = [value]

    if len(current_sequence) > len(best_sequence):
        best_sequence = current_sequence[:]

    return best_sequence


def classify_size_token(token: str) -> str:
    """사이즈 토큰 타입을 반환한다: numeric, english, korean, mixed, other"""
    value = token.strip()
    if not value:
        return "other"
    if value.isdigit():
        return "numeric"
    if re.fullmatch(r'[A-Za-z0-9/\-+ ]+', value):
        return "english"
    if has_hangul(value):
        english_present = bool(re.search(r'[A-Za-z]', value))
        digit_present = bool(re.search(r'\d', value))
        if english_present or digit_present:
            return "mixed"
        return "korean"
    return "other"


def normalize_size_tokens(tokens: List[str], option_kind: str = "") -> List[str]:
    """사이즈 토큰을 숫자/영문/한글 한 종류만 남도록 정규화한다"""
    cleaned: List[str] = []
    seen = set()
    for token in tokens:
        value = re.sub(r'\s+', ' ', str(token)).strip(' ,')
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)

    if not cleaned:
        return []

    groups = {
        'numeric': [],
        'english': [],
        'korean': [],
        'mixed': [],
    }
    for token in cleaned:
        token_type = classify_size_token(token)
        if token_type in groups:
            groups[token_type].append(token)

    option_kind = option_kind.upper()
    if groups['numeric']:
        return groups['numeric']
    if option_kind == 'SHOES' and groups['english']:
        return groups['english']
    if groups['english']:
        return groups['english']
    if groups['korean']:
        return groups['korean']
    if groups['mixed']:
        return groups['mixed']
    return cleaned


def extract_color_from_api(goods_options: Dict[str, object]) -> str:
    """옵션 API의 colorCode를 색상명으로 변환한다"""
    if not goods_options:
        return ""

    # optionValues의 색상 축(C / COLOR)을 우선 사용한다. (예: CG, MG)
    option_value_colors: List[str] = []
    for item in goods_options.get('optionItems', []):
        for option_value in item.get('optionValues', []):
            axis = str(option_value.get('optionName', '')).strip().upper()
            if axis not in {"C", "COLOR", "CLR", "COL"}:
                continue
            value = str(option_value.get('name', '')).strip() or str(option_value.get('code', '')).strip()
            if not value:
                continue
            if re.fullmatch(r'\d+', value):
                continue
            value = value.lower() if re.fullmatch(r'[A-Za-z0-9._-]{1,8}', value) else value
            if value not in option_value_colors and not is_color_count_placeholder(value):
                option_value_colors.append(value)

    if option_value_colors:
        return normalize_korean_color(', '.join(option_value_colors))

    color_map = get_color_name_map()
    color_names: List[str] = []
    for item in goods_options.get('optionItems', []):
        for color in item.get('colors', []):
            color_code = str(color.get('colorCode', '')).strip()
            color_id = str(color.get('colorId', '')).strip()

            # 1) API에 색상명이 직접 있으면 우선 사용
            color_name = str(color.get('colorName', '')).strip() or str(color.get('name', '')).strip()

            # 2) 색상명 맵(color-images)으로 보강
            if not color_name:
                if color_code:
                    color_name = color_map.get(color_code, '').strip()
                if not color_name and color_id:
                    color_name = color_map.get(color_id, '').strip()

            # 3) 맵이 없으면 원본 코드라도 보존 (예: cg.mg)
            if not color_name:
                color_name = color_code or color_id

            if color_name and not is_color_count_placeholder(color_name) and color_name not in color_names:
                color_names.append(color_name)

    return normalize_korean_color(', '.join(color_names))


def split_color_size_tokens(tokens: List[str]) -> Tuple[List[str], List[str]]:
    """'한글색상 영문사이즈' 패턴 토큰에서 색상과 사이즈를 분리한다.
    절반 이상 패턴 일치 시 (색상 목록, 사이즈 목록) 반환, 아니면 ([], 원래 토큰) 반환."""
    pattern = re.compile(r'^([가-힣]+)\s+([A-Za-z0-9/+\-]+)$')
    colors: List[str] = []
    sizes: List[str] = []
    matched = 0
    for token in tokens:
        m = pattern.match(token.strip())
        if m:
            matched += 1
            color = m.group(1)
            size = m.group(2).upper()
            if color not in colors:
                colors.append(color)
            if size not in sizes:
                sizes.append(size)
    if tokens and matched >= len(tokens) * 0.5:
        return colors, sizes
    return [], list(tokens)


def extract_sizes_from_api(goods_no: str, goods_sale_type: str, opt_kind_cd: str) -> Tuple[str, str]:
    """옵션 API와 실측 API를 이용해 사이즈(, 색상)를 추출한다.
    반환: (size_str, color_str) — color_str은 '한글색상 영문사이즈' 패턴 감지 시에만 채워짐"""
    option_kind = (opt_kind_cd or '').upper()
    options_data = fetch_goods_options(goods_no, goods_sale_type, opt_kind_cd)

    option_tokens: List[str] = []
    basic_options = options_data.get('basic', [])
    size_options = []
    for option in basic_options:
        option_name = str(option.get('name', '')).strip().lower()
        if option_name in {'사이즈', 'size'}:
            size_options.append(option)

    source_options = size_options if size_options else basic_options
    for option in source_options:
        for value in option.get('optionValues', []):
            token = str(value.get('name', '')).strip()
            if token:
                option_tokens.append(token)

    detected_colors, pure_size_tokens = split_color_size_tokens(option_tokens)
    if detected_colors:
        color_str = normalize_korean_color(', '.join(detected_colors))
        normalized_sizes = normalize_size_tokens(pure_size_tokens, option_kind)
        size_str = ', '.join(normalized_sizes) if normalized_sizes else ""
        return size_str, color_str

    normalized_option_tokens = normalize_size_tokens(option_tokens, option_kind)
    if normalized_option_tokens:
        return ', '.join(normalized_option_tokens), ""

    actual_size = fetch_actual_size(goods_no)
    actual_tokens = [str(item.get('name', '')).strip() for item in actual_size.get('sizes', []) if item.get('name')]
    normalized_actual_tokens = normalize_size_tokens(actual_tokens, option_kind)
    if normalized_actual_tokens:
        return ', '.join(normalized_actual_tokens), ""

    return "", ""


def extract_sizes_from_table(soup: BeautifulSoup, option_kind: str = "") -> List[str]:
    """무신사 표 영역에서 사이즈 값을 우선 추출한다"""
    size_values: List[str] = []
    valid_text_sizes = {
        'FREE', 'O/S', 'OS', 'ONE SIZE', 'XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL',
        '프리', '원사이즈', '스몰', '미디움', '라지', '엑스라지', '투엑스라지'
    }
    option_kind = option_kind.upper()

    for cell in soup.select('td[class*="StandardSizeTable"], th[class*="StandardSizeTable"]'):
        text = cell.get_text(' ', strip=True)
        if not text:
            continue

        upper_text = text.upper()
        if upper_text in valid_text_sizes or text in valid_text_sizes:
            if text not in size_values:
                size_values.append(text)
            continue

        if text.isdigit():
            number = int(text)
            if option_kind == 'SHOES':
                if 200 <= number <= 300 and number % 5 == 0 and text not in size_values:
                    size_values.append(text)
            else:
                if 40 <= number <= 130 and text not in size_values:
                    size_values.append(text)

    return normalize_size_tokens(size_values, option_kind)


def extract_sizes_from_review_options(soup: BeautifulSoup, option_kind: str = "") -> List[int]:
    """리뷰의 선택옵션 영역에서 노출된 사이즈를 추출한다"""
    option_kind = option_kind.upper()
    values: List[int] = []

    for tag in soup.select('span[class*="text-body_13px_reg"][class*="text-black"]'):
        text = tag.get_text(' ', strip=True)
        if not text.isdigit():
            continue

        number = int(text)
        if option_kind == 'SHOES':
            if 200 <= number <= 300 and number % 5 == 0:
                values.append(number)
        else:
            if 40 <= number <= 130:
                values.append(number)

    return sorted(set(values))


def extract_sizes(soup: BeautifulSoup, option_kind: str = "") -> str:
    """페이지에서 사용 가능한 사이즈 후보를 추출한다"""
    text_candidates: List[str] = []
    numeric_candidates: List[int] = []
    text_sizes = {
        'FREE', 'O/S', 'OS', 'ONE SIZE', 'XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL',
        '프리', '원사이즈', '스몰', '미디움', '라지', '엑스라지', '투엑스라지'
    }
    numeric_sizes = {
        44, 55, 66, 77, 88,
        90, 95, 100, 105, 110, 115, 120,
        130, 135, 140, 145, 150, 155, 160,
        200, 205, 210, 215, 220, 225, 230, 235, 240, 245,
        250, 255, 260, 265, 270, 275, 280, 285, 290, 295, 300,
    }

    table_sizes = extract_sizes_from_table(soup, option_kind)
    review_sizes = extract_sizes_from_review_options(soup, option_kind)

    if review_sizes:
        if table_sizes:
            table_numbers = [int(x) for x in table_sizes if x.isdigit()]
            if table_numbers:
                low, high = min(review_sizes), max(review_sizes)
                narrowed = [n for n in table_numbers if low <= n <= high]
                narrowed = find_longest_step_sequence(narrowed, (5, 10))
                if narrowed:
                    return ', '.join(str(n) for n in narrowed)
        return ', '.join(str(n) for n in review_sizes)

    if table_sizes:
        if all(item.isdigit() for item in table_sizes):
            numeric = [int(item) for item in table_sizes]
            numeric = find_longest_step_sequence(numeric, (5, 10))
            if option_kind.upper() == 'SHOES' and len(numeric) >= 4:
                return ', '.join(str(n) for n in numeric)
            if option_kind.upper() != 'SHOES' and len(numeric) >= 2:
                return ', '.join(str(n) for n in numeric)
            return ""
        if len(table_sizes) >= 2:
            return ', '.join(table_sizes)
        return ""

    for text in soup.stripped_strings:
        value = text.strip()
        upper_value = value.upper()

        if upper_value in text_sizes or value in text_sizes:
            if value not in text_candidates:
                text_candidates.append(value)

        if has_hangul(value) and value in text_sizes and value not in text_candidates:
            text_candidates.append(value)

        if value.isdigit() and int(value) in numeric_sizes:
            numeric_candidates.append(int(value))

    option_kind = option_kind.upper()
    if option_kind == 'SHOES' or any(number >= 200 for number in numeric_candidates):
        size_numbers = [number for number in numeric_candidates if 200 <= number <= 300]
        numeric_sequence = find_longest_step_sequence(size_numbers, (5,))
    else:
        size_numbers = [number for number in numeric_candidates if number < 200]
        numeric_sequence = find_longest_step_sequence(size_numbers, (5, 10))

    formatted_numeric = [str(number) for number in numeric_sequence]

    if option_kind.upper() == 'SHOES' and len(formatted_numeric) >= 4:
        return ', '.join(formatted_numeric)
    if option_kind.upper() != 'SHOES' and len(formatted_numeric) >= 2:
        return ', '.join(formatted_numeric)
    if text_candidates:
        normalized_text = normalize_size_tokens(text_candidates[:12], option_kind)
        return ', '.join(normalized_text)
    return ""


def format_price(price_value: object) -> str:
    """숫자 또는 문자열 가격을 숫자 문자열로 변환한다"""
    if isinstance(price_value, (int, float)):
        return f"{int(price_value):,}"
    if isinstance(price_value, str):
        return normalize_price(price_value)
    return "가격 미확인"


def is_empty_cell(value: str) -> bool:
    """셀 값이 비어있는지 확인한다"""
    if value is None:
        return True
    return str(value).strip() == ""


def extract_musinsa_sku(
    raw_product_name: str,
    product_name: str,
    mss_state: Dict[str, object],
    product_json: Dict[str, object] = None,
    soup: object = None,
) -> str:
    """무신사 원본 데이터에서 품번을 추출한다"""
    raw_text = (raw_product_name or "").strip()

    # 1) 상품명 끝 '/ XXXXX' 패턴 우선
    suffix_match = re.search(r'/\s*([A-Z0-9-]{4,})\s*$', raw_text)
    if suffix_match:
        return suffix_match.group(1)

    # 2) API 상태값: styleNo, modelNo, articleNo 등 여러 필드 확인
    if isinstance(mss_state, dict):
        for field in ('styleNo', 'modelNo', 'articleNo', 'modelNm', 'referenceNo'):
            val = str(mss_state.get(field, '')).strip()
            if val and re.fullmatch(r'[A-Z0-9-]{4,}', val, re.IGNORECASE):
                return val.upper()

    # 3) JSON-LD Product의 mpn / sku 필드
    if isinstance(product_json, dict):
        for field in ('mpn', 'sku', 'model', 'productID'):
            val = str(product_json.get(field, '')).strip()
            if val and re.fullmatch(r'[A-Z0-9-]{4,}', val, re.IGNORECASE):
                return val.upper()

    # 4) 페이지 내 품번 표기 탐지 (soup 기반)
    if soup is not None:
        page_text = soup.get_text(separator=' ')
        # "품번 : XXXX" / "Style No. XXXX" / "모델번호 : XXXX" 등
        label_match = re.search(
            r'(?:품번|스타일\s*번호|Style\s*No\.?|Model\s*No\.?|모델번호)\s*[:\s]+([A-Z0-9][A-Z0-9-]{3,})',
            page_text, re.IGNORECASE
        )
        if label_match:
            return label_match.group(1).upper()

        # 상품 상세정보 테이블 내 품번 셀
        for tag in soup.select('th, td, li, dt, dd, span[class*="info"], span[class*="detail"]'):
            text = tag.get_text(strip=True)
            sku_cell = re.search(
                r'(?:품번|스타일번호|모델번호)[\s:：]+([A-Z0-9][A-Z0-9-]{3,})',
                text, re.IGNORECASE
            )
            if sku_cell:
                return sku_cell.group(1).upper()

    # 5) 상품명 내 SKU 형태 탐지 (다양한 패턴)
    base_text = f"{raw_text} {product_name or ''}".strip()

    sku_patterns = [
        r'\b([A-Z]{2,}[0-9]{2,}[A-Z0-9-]*)\b',               # 영문시작: S260106HBP13
        r'\b([A-Z][0-9]{2,}[A-Z][A-Z0-9-]{2,})\b',            # 영숫자혼합: A12BC34
        r'\b([A-Z0-9]{2,}-[A-Z0-9]{2,}(?:-[A-Z0-9]+)*)\b',    # 하이픈: SU25-CW-P001
        r'\b([0-9]{3,}[A-Z]{2,}[A-Z0-9-]*)\b',                 # 숫자시작: 123ABC
    ]
    for pattern in sku_patterns:
        m = re.search(pattern, base_text)
        if m:
            candidate = m.group(1)
            # 단순 숫자열이나 너무 짧은 건 제외
            if re.search(r'[A-Z]', candidate) and re.search(r'[0-9]', candidate):
                return candidate

    return ""


def get_existing_row_values(service, sheet_name: str, row_num: int) -> Dict[str, str]:
    """현재 행의 A~X 값을 읽어 컬럼별로 반환한다"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!A{row_num}:X{row_num}"
        ).execute()
        rows = result.get('values', [])
        row = rows[0] if rows else []

        existing = {
            SEQUENCE_COLUMN: row[0] if len(row) > 0 else "",
            URL_COLUMN: row[1] if len(row) > 1 else "",
            BRAND_COLUMN: row[2] if len(row) > 2 else "",
            BRAND_EN_COLUMN: row[3] if len(row) > 3 else "",
            PRODUCT_NAME_KR_COLUMN: row[4] if len(row) > 4 else "",
            PRODUCT_NAME_EN_COLUMN: row[5] if len(row) > 5 else "",
            MUSINSA_SKU_COLUMN: row[6] if len(row) > 6 else "",
            COLOR_KR_COLUMN: row[7] if len(row) > 7 else "",
            COLOR_EN_COLUMN: row[8] if len(row) > 8 else "",
            SIZE_COLUMN: row[9] if len(row) > 9 else "",
            ACTUAL_SIZE_COLUMN: row[10] if len(row) > 10 else "",
            PRICE_COLUMN: row[11] if len(row) > 11 else "",
            BAIMA_SELL_PRICE_COLUMN: row[12] if len(row) > 12 else "",
            IMAGE_PATHS_COLUMN: row[13] if len(row) > 13 else "",
            SHIPPING_COST_COLUMN: row[14] if len(row) > 14 else "",
            CATEGORY_LARGE_COLUMN: row[21] if len(row) > 21 else "",
            CATEGORY_MIDDLE_COLUMN: row[22] if len(row) > 22 else "",
            CATEGORY_SMALL_COLUMN: row[23] if len(row) > 23 else "",
        }
        return existing
    except Exception as e:
        print(f" {sheet_name} {row_num}행 기존 데이터 조회 실패: {e}")
        return {}


def get_existing_rows_bulk(
    service,
    sheet_name: str,
    row_numbers: List[int],
) -> Dict[int, Dict[str, str]]:
    """여러 행의 A~X 값을 한 번에 읽어 행 번호별 맵으로 반환한다"""
    if not row_numbers:
        return {}

    min_row = min(row_numbers)
    max_row = max(row_numbers)
    columns = [
        SEQUENCE_COLUMN, URL_COLUMN, BRAND_COLUMN, BRAND_EN_COLUMN,
        PRODUCT_NAME_KR_COLUMN, PRODUCT_NAME_EN_COLUMN, MUSINSA_SKU_COLUMN,
        COLOR_KR_COLUMN, COLOR_EN_COLUMN, SIZE_COLUMN,
        ACTUAL_SIZE_COLUMN,
        PRICE_COLUMN, BAIMA_SELL_PRICE_COLUMN, IMAGE_PATHS_COLUMN, SHIPPING_COST_COLUMN,
        CATEGORY_LARGE_COLUMN, CATEGORY_MIDDLE_COLUMN, CATEGORY_SMALL_COLUMN,
    ]

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!A{min_row}:X{max_row}"
        ).execute()
        values = result.get('values', [])

        row_map: Dict[int, Dict[str, str]] = {}
        for offset, row_num in enumerate(range(min_row, max_row + 1)):
            row_values = values[offset] if offset < len(values) else []
            mapped = {}
            mapped[SEQUENCE_COLUMN] = row_values[0] if len(row_values) > 0 else ""
            mapped[URL_COLUMN] = row_values[1] if len(row_values) > 1 else ""
            mapped[BRAND_COLUMN] = row_values[2] if len(row_values) > 2 else ""
            mapped[BRAND_EN_COLUMN] = row_values[3] if len(row_values) > 3 else ""
            mapped[PRODUCT_NAME_KR_COLUMN] = row_values[4] if len(row_values) > 4 else ""
            mapped[PRODUCT_NAME_EN_COLUMN] = row_values[5] if len(row_values) > 5 else ""
            mapped[MUSINSA_SKU_COLUMN] = row_values[6] if len(row_values) > 6 else ""
            mapped[COLOR_KR_COLUMN] = row_values[7] if len(row_values) > 7 else ""
            mapped[COLOR_EN_COLUMN] = row_values[8] if len(row_values) > 8 else ""
            mapped[SIZE_COLUMN] = row_values[9] if len(row_values) > 9 else ""
            mapped[ACTUAL_SIZE_COLUMN] = row_values[10] if len(row_values) > 10 else ""
            mapped[PRICE_COLUMN] = row_values[11] if len(row_values) > 11 else ""
            mapped[BAIMA_SELL_PRICE_COLUMN] = row_values[12] if len(row_values) > 12 else ""
            mapped[IMAGE_PATHS_COLUMN] = row_values[13] if len(row_values) > 13 else ""
            mapped[SHIPPING_COST_COLUMN] = row_values[14] if len(row_values) > 14 else ""
            mapped[CATEGORY_LARGE_COLUMN] = row_values[21] if len(row_values) > 21 else ""
            mapped[CATEGORY_MIDDLE_COLUMN] = row_values[22] if len(row_values) > 22 else ""
            mapped[CATEGORY_SMALL_COLUMN] = row_values[23] if len(row_values) > 23 else ""
            row_map[row_num] = mapped

        return row_map
    except Exception as e:
        print(f" {sheet_name} 기존 데이터 일괄 조회 실패: {e}")
        return {}


def build_incremental_payload(
    sheet_name: str,
    row_num: int,
    product_info: Dict[str, str],
    existing_values: Dict[str, str],
) -> List[Dict[str, object]]:
    """기존 값이 비어 있는 셀만 채우는 payload를 구성한다"""
    sequence = f"{row_num - ROW_START + 1:03d}"
    candidates = [
        (SEQUENCE_COLUMN, sequence),
        (BRAND_COLUMN, product_info.get('brand', '')),
        (BRAND_EN_COLUMN, product_info.get('brand_en', '')),
        (PRODUCT_NAME_KR_COLUMN, product_info.get('product_name_kr', '')),
        (MUSINSA_SKU_COLUMN, product_info.get('musinsa_sku', '')),
        (COLOR_KR_COLUMN, product_info.get('color_kr', '')),
        (SIZE_COLUMN, product_info.get('size', '')),
        (ACTUAL_SIZE_COLUMN, product_info.get('actual_size', '')),
        (PRICE_COLUMN, product_info.get('price', '')),
        (BAIMA_SELL_PRICE_COLUMN, product_info.get('buyma_price', '')),
        (IMAGE_PATHS_COLUMN, product_info.get('image_paths', '')),
        (SHIPPING_COST_COLUMN, product_info.get('shipping_cost', '')),
        (CATEGORY_LARGE_COLUMN, product_info.get('musinsa_category_large', '')),
        (CATEGORY_MIDDLE_COLUMN, product_info.get('musinsa_category_middle', '')),
        (CATEGORY_SMALL_COLUMN, product_info.get('musinsa_category_small', '')),
    ]

    updates: List[Dict[str, object]] = []
    for column, new_value in candidates:
        if is_empty_cell(new_value):
            continue

        current_value = existing_values.get(column, "")
        if is_empty_cell(current_value):
            updates.append({
                'range': f"'{sheet_name}'!{column}{row_num}",
                'values': [[new_value]],
            })
    return updates


def row_needs_update(existing_values: Dict[str, str], require_image_paths: bool = True) -> bool:
    """자동 입력 대상 열 중 빈 칸이 있으면 True.

    require_image_paths=False면 N열(image_paths) 빈칸은 대상에서 제외한다.
    """
    target_columns = [
        BRAND_COLUMN,
        BRAND_EN_COLUMN,
        PRODUCT_NAME_KR_COLUMN,
        MUSINSA_SKU_COLUMN,
        COLOR_KR_COLUMN,
        SIZE_COLUMN,
        ACTUAL_SIZE_COLUMN,
        PRICE_COLUMN,
        BAIMA_SELL_PRICE_COLUMN,
        SHIPPING_COST_COLUMN,
    ]
    if require_image_paths:
        target_columns.append(IMAGE_PATHS_COLUMN)

    for column in target_columns:
        if is_empty_cell(existing_values.get(column, "")):
            return True
    return False


def row_has_existing_output(existing_values: Dict[str, str]) -> bool:
    """자동 입력 대상 열에 이미 값이 하나라도 있으면 True"""
    target_columns = [
        BRAND_COLUMN,
        BRAND_EN_COLUMN,
        PRODUCT_NAME_KR_COLUMN,
        MUSINSA_SKU_COLUMN,
        COLOR_KR_COLUMN,
        SIZE_COLUMN,
        ACTUAL_SIZE_COLUMN,
        PRICE_COLUMN,
        BAIMA_SELL_PRICE_COLUMN,
        IMAGE_PATHS_COLUMN,
        SHIPPING_COST_COLUMN,
    ]
    for column in target_columns:
        if not is_empty_cell(existing_values.get(column, "")):
            return True
    return False


def row_needs_image_download(existing_values: Dict[str, str]) -> bool:
    """N열(image_paths)이 비어있으면 이미지 저장 대상으로 본다."""
    return is_empty_cell(existing_values.get(IMAGE_PATHS_COLUMN, ""))


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

    try:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!{IMAGE_PATHS_COLUMN}{row_num}",
            valueInputOption='USER_ENTERED',
            body={'values': [[image_paths]]},
        ).execute()
        print(f" {sheet_name} {row_num}행 저장: N열(image_paths) 업데이트")
    except Exception as e:
        print(f" {sheet_name} {row_num}행 N열 저장 실패: {e}")


def write_to_sheet(
    service,
    sheet_name: str,
    row_num: int,
    product_info: Dict[str, str],
    existing_values: Dict[str, str] = None,
):
    """Google Sheets의 A, C~O 열에 한 행 데이터를 쓴다"""
    try:
        if existing_values is None:
            existing_values = get_existing_row_values(service, sheet_name, row_num)
        updates = build_incremental_payload(sheet_name, row_num, product_info, existing_values)

        if not updates:
            print(f" {sheet_name} {row_num}행: 기존 값이 있어 새로 쓸 내용이 없습니다")
            return

        body = {
            'valueInputOption': 'USER_ENTERED',
            'data': updates,
        }
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body=body
        ).execute()
        print(
            f" {sheet_name} {row_num}행 저장: "
            f"{len(updates)}개 셀 업데이트"
        )
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
    print(f"'{sheet_name}' 시트에서 B열 링크를 읽는 중...")
    rows = read_urls_from_sheet(service, sheet_name)
    if not rows:
        print(f"'{sheet_name}' 시트의 B열에 처리할 URL이 없습니다.")
        return

    header_map = get_sheet_header_map(service, sheet_name)
    has_margin_header = MARGIN_RATE_HEADER in header_map
    has_status_header = PROGRESS_STATUS_HEADER in header_map
    if not has_margin_header:
        print(f"'{sheet_name}' 시트: '{MARGIN_RATE_HEADER}' 헤더를 찾지 못했습니다.")
    if not has_status_header:
        print(f"'{sheet_name}' 시트: '{PROGRESS_STATUS_HEADER}' 헤더를 찾지 못했습니다.")

    row_numbers = [row_num for row_num, _ in rows]
    existing_rows_map = get_existing_rows_bulk(service, sheet_name, row_numbers)

    target_rows: List[Tuple[int, str]] = []
    for row_num, url in rows:
        existing_values = existing_rows_map.get(row_num, {})
        dynamic_values = get_row_dynamic_values(
            service,
            sheet_name,
            row_num,
            header_map,
            [MARGIN_RATE_HEADER, PROGRESS_STATUS_HEADER],
        )
        margin_rate = parse_margin_rate(dynamic_values.get(MARGIN_RATE_HEADER, ""))
        current_status = dynamic_values.get(PROGRESS_STATUS_HEADER, "")

        if make_thumbnails:
            if is_thumbnail_ready_status(current_status):
                target_rows.append((row_num, url))
        elif download_images:
            # 이미지 저장은 상태가 '이미지진행대기'인 행만 처리한다.
            if is_image_ready_status(current_status) and row_needs_image_download(existing_values):
                target_rows.append((row_num, url))
        else:
            # 감시 모드에서도 "빈 칸이 있는 행"은 계속 보충 입력 대상으로 포함한다.
            if is_crawler_ready_status(current_status) and row_needs_update(existing_values, require_image_paths=False):
                target_rows.append((row_num, url))

    if not target_rows:
        print(f"'{sheet_name}' 시트: 신규 작성 대상이 없습니다.")
        return

    print(f"'{sheet_name}' 시트: {len(target_rows)}개 행을 처리합니다.")

    if make_thumbnails:
        print(f"'{sheet_name}' 시트: 썸네일 자동 생성 모드로 처리합니다.")
        for idx, _url in target_rows:
            print(f"[{sheet_name}] {idx}행 썸네일 생성 중")
            existing_values_for_row = existing_rows_map.get(idx, {})
            folder_path = resolve_image_folder_from_paths(existing_values_for_row.get(IMAGE_PATHS_COLUMN, ""))
            brand = build_thumbnail_brand(existing_values_for_row)
            if has_status_header:
                update_cell_by_header(service, sheet_name, idx, header_map, PROGRESS_STATUS_HEADER, STATUS_THUMBNAILING)
            if create_thumbnail_for_folder(folder_path, brand):
                if has_status_header:
                    if update_cell_by_header(service, sheet_name, idx, header_map, PROGRESS_STATUS_HEADER, STATUS_THUMBNAILS_DONE):
                        print(f" {sheet_name} {idx}행 상태 업데이트: {STATUS_THUMBNAILS_DONE}")
            elif has_status_header:
                if update_cell_by_header(service, sheet_name, idx, header_map, PROGRESS_STATUS_HEADER, STATUS_ERROR):
                    print(f" {sheet_name} {idx}행 상태 업데이트: {STATUS_ERROR}")
            time.sleep(1)
        return

    if download_images:
        print(f"'{sheet_name}' 시트: 이미지 저장 모드(N열 기준)로 처리합니다.")
        for idx, url in target_rows:
            print(f"[{sheet_name}] {idx}행 이미지 저장 중: {url}")
            existing_values_for_row = existing_rows_map.get(idx, {})
            sheet_sku = existing_values_for_row.get(MUSINSA_SKU_COLUMN, "")
            if has_status_header:
                update_cell_by_header(service, sheet_name, idx, header_map, PROGRESS_STATUS_HEADER, STATUS_DOWNLOADING)
            product_info = scrape_musinsa_product(
                driver,
                url,
                idx,
                existing_sku=sheet_sku,
                download_images=True,
                images_only=True,
            )
            write_image_paths_only(
                service,
                sheet_name,
                idx,
                product_info.get('image_paths', ''),
                existing_values_for_row,
            )
            if product_info.get('image_paths', '') and has_status_header:
                if update_cell_by_header(service, sheet_name, idx, header_map, PROGRESS_STATUS_HEADER, STATUS_IMAGES_SAVED):
                    print(f" {sheet_name} {idx}행 상태 업데이트: {STATUS_IMAGES_SAVED}")
            time.sleep(1)
        return

    shipping_table = read_shipping_table(service, sheet_name)
    if not shipping_table:
        print(f"'{sheet_name}' 시트: 배송비 기준표(Z/AA/AB)를 읽지 못해 O열 배송비는 비워집니다.")
    for idx, url in target_rows:
        print(f"[{sheet_name}] {idx}행 처리 중: {url}")
        existing_values_for_row = existing_rows_map.get(idx, {})
        sheet_sku = existing_values_for_row.get(MUSINSA_SKU_COLUMN, "")
        if has_status_header:
            update_cell_by_header(service, sheet_name, idx, header_map, PROGRESS_STATUS_HEADER, STATUS_CRAWLING)
        product_info = scrape_musinsa_product(
            driver,
            url,
            idx,
            existing_sku=sheet_sku,
            download_images=download_images,
        )
        # 배송비 산출: 상품명 + 카테고리로 무게 추정 → W/X/Y 기준표로 배송비 산출
        estimated_weight = estimate_weight(
            product_info.get('product_name_kr', ''),
            product_info.get('opt_kind_cd', ''),
        )
        shipping_cost = lookup_shipping_cost(shipping_table, estimated_weight)
        if shipping_cost:
            product_info['shipping_cost'] = shipping_cost
            print(f"    배송비 산출: 추정 {estimated_weight}kg -> KRW {shipping_cost}")
        else:
            print(f"    배송비 산출 실패: 기준표/무게 매칭을 확인하세요 (추정 {estimated_weight}kg)")
        write_to_sheet(
            service,
            sheet_name,
            idx,
            product_info,
            existing_rows_map.get(idx, {}),
        )
        if has_status_header:
            dynamic_values = get_row_dynamic_values(
                service,
                sheet_name,
                idx,
                header_map,
                [MARGIN_RATE_HEADER, PROGRESS_STATUS_HEADER],
            )
            margin_rate = parse_margin_rate(dynamic_values.get(MARGIN_RATE_HEADER, ""))
            current_status = dynamic_values.get(PROGRESS_STATUS_HEADER, "")
            next_status = determine_progress_status(margin_rate)

            # 정찰 단계 입력이 완료되면 다음 단계(CRAWLED)로 전환한다.
            refreshed_values = get_existing_row_values(service, sheet_name, idx)
            if not row_needs_update(refreshed_values, require_image_paths=False):
                next_status = STATUS_CRAWLED

            if current_status != next_status:
                if update_cell_by_header(service, sheet_name, idx, header_map, PROGRESS_STATUS_HEADER, next_status):
                    if margin_rate is None:
                        print(f" {sheet_name} {idx}행 상태 업데이트: {next_status} (마진률 미확인)")
                    else:
                        print(f" {sheet_name} {idx}행 상태 업데이트: {next_status} (마진률 {margin_rate:.2f}%)")
        time.sleep(5)  # 차단 방지를 위한 대기 시간 유지


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
    chrome_options = ChromeOptions()
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def normalize_price(text: str) -> str:
    """가격 문자열에서 숫자만 추출하여 정상화"""
    if not text:
        return "가격 미확인"
    match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*원', text)
    if match:
        return f"{int(match.group(1).replace(',', '')):,}"
    digits = ''.join(filter(str.isdigit, text))
    if digits:
        return f"{int(digits):,}"
    return "가격 미확인"


def extract_discounted_product_price(soup: BeautifulSoup) -> str:
    """페이지에서 쿠폰가를 제외한 상품 할인판매가를 추출한다"""
    if soup is None:
        return "가격 미확인"

    candidates: List[int] = []

    # 상품 가격 UI 영역 우선 탐색 (쿠폰 영역 제외)
    selectors = [
        '[class*="CurrentPrice"]',
        '[class*="CalculatedPrice"]',
        '[class*="PriceTotalWrap"]',
        '[class*="DiscountWrap"]',
        '[class*="sale_price"]',
        '[class*="price"]',
    ]
    for selector in selectors:
        for tag in soup.select(selector):
            text = tag.get_text(' ', strip=True)
            if not text:
                continue
            # 쿠폰 적용가는 제외
            if '쿠폰' in text:
                continue
            for raw in re.findall(r'(\d{1,3}(?:,\d{3})*)\s*원', text):
                try:
                    value = int(raw.replace(',', ''))
                except ValueError:
                    continue
                if 1000 <= value <= 100000000:
                    candidates.append(value)

    # 라벨 기반 패턴 (판매가/할인가/현재가)
    page_text = soup.get_text(' ', strip=True)
    patterns = [
        r'(?:할인가|판매가|현재가)[^0-9]{0,20}(\d{1,3}(?:,\d{3})*)\s*원',
        r'(\d{1,3}(?:,\d{3})*)\s*원[^가-힣A-Za-z0-9]{0,10}(?:할인)',
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, page_text, re.IGNORECASE):
            try:
                value = int(str(raw).replace(',', ''))
            except ValueError:
                continue
            if 1000 <= value <= 100000000:
                candidates.append(value)

    if not candidates:
        return "가격 미확인"

    return f"{min(candidates):,}"


def extract_yen_values(text: str) -> List[int]:
    """문자열에서 엔화 금액 후보를 정수 목록으로 추출한다"""
    if not text:
        return []
    matches = re.findall(r'[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})', text)
    values: List[int] = []
    for raw in matches:
        try:
            value = int(raw.replace(',', ''))
        except ValueError:
            continue
        # 비정상적으로 작은/큰 값은 제외
        if 500 <= value <= 10000000:
            values.append(value)
    return values


def extract_buyma_listing_prices(soup: BeautifulSoup) -> List[int]:
    """BUYMA 검색 첫 페이지에서 셀러 상품 카드의 가격만 추출한다"""
    prices: List[int] = []

    # 1) BUYMA 상품 액션 블록(item-url) 기반 추출
    action_blocks = soup.select('[item-url*="/item/"]')
    for action in action_blocks:
        container = action
        price_tags = []
        for _ in range(5):
            if not container:
                break
            price_tags = container.select('span.Price_Txt')
            if price_tags:
                break
            container = container.parent

        for tag in price_tags:
            prices.extend(extract_yen_values(tag.get_text(' ', strip=True)))

    if prices:
        return prices

    # 2) fallback: 실제 상품 상세 링크(/item/숫자/) 주변에서만 추출
    item_links = soup.select('a[href*="/item/"]')
    for link in item_links:
        href = link.get('href', '')
        if not re.search(r'/item/\d+/?', href):
            continue

        container = link
        price_tags = []
        for _ in range(6):
            if not container:
                break
            price_tags = container.select('span.Price_Txt')
            if price_tags:
                break
            container = container.parent

        for tag in price_tags:
            prices.extend(extract_yen_values(tag.get_text(' ', strip=True)))

    return prices


def extract_buyma_listing_entries(soup: BeautifulSoup) -> List[Dict[str, object]]:
    """BUYMA 검색 첫 페이지에서 상품카드의 제목/가격/링크를 함께 추출한다"""
    entries: List[Dict[str, object]] = []
    seen_urls = set()

    # 검색 페이지의 표시 개수(예: "該当件数 8件")를 읽어 추천/연관 영역을 제외하기 위한 상한으로 사용
    result_count = None
    page_text = soup.get_text(' ', strip=True)
    count_match = re.search(r'該当件数\s*([0-9]+)件', page_text)
    if count_match:
        try:
            result_count = int(count_match.group(1))
        except ValueError:
            result_count = None

    for link in soup.select('a[href*="/item/"]'):
        href = link.get('href', '').strip()
        if not re.search(r'/item/\d+/?', href):
            continue

        full_url = href if href.startswith('http') else f"https://www.buyma.com{href}"
        full_url = full_url.split('?')[0]
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        container = link
        title_text = link.get_text(' ', strip=True)
        price_values: List[int] = []

        for _ in range(6):
            if not container:
                break
            if not title_text:
                title_tag = container.select_one('a[href*="/item/"], h3, [class*="title"], [class*="name"]')
                if title_tag:
                    title_text = title_tag.get_text(' ', strip=True)

            # 1) 대표 가격 클래스 우선
            price_tag = container.select_one('span.Price_Txt, [class*="price"], [class*="Price"]')
            if price_tag:
                price_values = extract_yen_values(price_tag.get_text(' ', strip=True))
                price_values = [p for p in price_values if p >= 3000]
                if price_values:
                    break

            # 2) 클래스가 바뀐 경우를 대비해 카드 텍스트 전체에서 보정 추출
            context_text = container.get_text(' ', strip=True)
            text_prices = extract_yen_values(context_text)
            text_prices = [p for p in text_prices if p >= 3000]
            if text_prices:
                price_values = text_prices
                break
            container = container.parent

        if not price_values:
            continue

        entries.append({
            'url': full_url,
            'title': title_text,
            'price': min(price_values),
        })

    if result_count is not None and result_count > 0 and len(entries) > result_count:
        entries = entries[:result_count]

    return entries


def extract_buyma_shipping_included_prices(soup: BeautifulSoup) -> List[int]:
    """검색 페이지 텍스트에서 '¥xx,xxx 送料込' 형태 가격을 추출한다"""
    text = soup.get_text(' ', strip=True)
    patterns = [
        r'[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})\s*送料込',
        r'([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})\s*円\s*送料込',
    ]

    prices: List[int] = []
    for pattern in patterns:
        for raw in re.findall(pattern, text):
            try:
                value = int(raw.replace(',', ''))
            except ValueError:
                continue
            if 3000 <= value <= 10000000:
                prices.append(value)

    return prices


def extract_buyma_item_page_price(soup: BeautifulSoup) -> int:
    """BUYMA 상품 상세 페이지에서 판매가격을 추출한다"""
    page_text = soup.get_text(' ', strip=True)

    def clean_price_context(text: str) -> str:
        cleaned = re.sub(r'\s+', ' ', text)
        cleaned = re.sub(
            r'参考価格\s*[¥￥]?\s*[0-9]{1,3}(?:,[0-9]{3})+|参考価格\s*[¥￥]?\s*[0-9]{3,}',
            ' ',
            cleaned,
        )
        cleaned = re.sub(
            r'あなただけの特別価格\s*[¥￥]?\s*[0-9]{1,3}(?:,[0-9]{3})+|あなただけの特別価格\s*[¥￥]?\s*[0-9]{3,}',
            ' ',
            cleaned,
        )
        return cleaned

    price_texts: List[str] = []
    selectors = [
        '[class*="price"]',
        '[class*="Price"]',
        '.product_price',
        '.Price_Txt',
    ]
    for selector in selectors:
        for tag in soup.select(selector):
            text = tag.get_text(' ', strip=True)
            if text:
                price_texts.append(text)

    cleaned_texts = [clean_price_context(text) for text in price_texts]

    # 우선순위 1: 타임세일 가격
    sale_candidates: List[int] = []
    for text in cleaned_texts:
        for raw in re.findall(r'タイムセール.*?[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})', text):
            try:
                sale_candidates.append(int(raw.replace(',', '')))
            except ValueError:
                continue
    sale_candidates = [p for p in sale_candidates if p >= 3000]
    if sale_candidates:
        return min(sale_candidates)

    # 우선순위 2: 일반 판매가격(参考価格/개인특가 제외 후)
    direct_candidates: List[int] = []
    for text in cleaned_texts:
        for raw in re.findall(r'(?:^|\s)価格[^\d¥￥]{0,20}[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})', text):
            try:
                direct_candidates.append(int(raw.replace(',', '')))
            except ValueError:
                continue
    direct_candidates = [p for p in direct_candidates if p >= 3000]
    if direct_candidates:
        return min(direct_candidates)

    # 우선순위 3: 가격 관련 영역 전체에서 엔화 값 추출
    price_candidates: List[int] = []
    for text in cleaned_texts:
        price_candidates.extend(extract_yen_values(text))

    # 0원/비정상 저가를 제외하고 반환
    price_candidates = [p for p in price_candidates if p >= 3000]
    if price_candidates:
        return min(price_candidates)

    # 우선순위 4: 페이지 전체 fallback
    cleaned_page_text = clean_price_context(page_text)
    fallback_candidates = extract_yen_values(cleaned_page_text)
    fallback_candidates = [p for p in fallback_candidates if p >= 3000]
    if fallback_candidates:
        return min(fallback_candidates)

    return 0


def is_relevant_buyma_item(
    soup: BeautifulSoup,
    musinsa_sku: str,
    english_name: str,
    brand: str,
) -> bool:
    """BUYMA 상세 페이지가 현재 상품과 관련 있는지 판별한다"""
    title_tag = soup.select_one('h1')
    title_text = title_tag.get_text(' ', strip=True) if title_tag else ''
    page_text = soup.get_text(' ', strip=True)
    haystack = f"{title_text} {page_text[:3000]}".lower()
    full_haystack = f"{title_text} {page_text}".lower()

    sku = (musinsa_sku or '').strip().lower()
    if sku:
        if sku in full_haystack:
            return True
        # SKU 일부만 포함된 경우 대비
        if len(sku) >= 6 and sku[:6] in full_haystack:
            return True

    english = re.sub(r'\s+', ' ', (english_name or '').strip()).lower()
    tokens = [
        t for t in re.findall(r'[a-z0-9]{4,}', english)
        if t not in {'with', 'from', 'size', 'color', 'shoes', 'black', 'white'}
    ]

    if tokens:
        hits = sum(1 for token in tokens if token in haystack)
        if hits >= 2:
            return True

    brand_text = (brand or '').strip().lower()
    if brand_text and brand_text in haystack and tokens:
        hits = sum(1 for token in tokens[:3] if token in haystack)
        if hits >= 1:
            return True

    return False


def is_relevant_buyma_listing_entry(
    title: str,
    musinsa_sku: str,
    english_name: str,
    brand: str,
) -> bool:
    """검색 결과 카드 제목이 현재 상품과 관련 있는지 더 엄격하게 판별한다."""
    title_lower = re.sub(r'\s+', ' ', (title or '').strip()).lower()
    if not title_lower:
        return False

    sku = (musinsa_sku or '').strip().lower()
    if sku:
        if sku in title_lower:
            return True
        if len(sku) >= 6 and sku[:6] in title_lower:
            return True

    english = re.sub(r'\s+', ' ', (english_name or '').strip()).lower()
    tokens = [
        t for t in re.findall(r'[a-z0-9]{4,}', english)
        if t not in {'with', 'from', 'size', 'color', 'shoes', 'black', 'white'}
    ]
    brand_text = (brand or '').strip().lower()

    # 브랜드만 일치하거나 토큰 1개만 일치하는 카드는 다른 상품이 섞이기 쉬워 제외
    if brand_text and brand_text not in title_lower:
        return False

    if tokens:
        hits = sum(1 for token in tokens if token in title_lower)
        if hits >= 2:
            return True

    return False


def normalize_buyma_query(product_name: str, brand: str) -> List[str]:
    """바이마 검색용 질의를 우선순위 순으로 생성한다
    SKU 형태 > 상품명+브랜드 > 상품명 순서로 우선도 결정"""
    cleaned_name = re.sub(r'\s+', ' ', (product_name or '').strip())
    cleaned_name = re.sub(r'[\[\](){}]', ' ', cleaned_name)
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    cleaned_brand = re.sub(r'\s+', ' ', (brand or '').strip())

    # 상품명에서 SKU 형태 추출: 대문자+숫자 조합이나 4자리 이상 숫자
    sku_match = re.search(r'\b([A-Z]{2,}[0-9]{2,}[A-Z0-9]*|[0-9]{4,})\b', cleaned_name)
    sku_candidates = [sku_match.group(1)] if sku_match else []

    # 상품명에서 영문 부분만 추출 (한글 제거)
    english_parts = re.findall(r'[A-Za-z0-9\s\-/]+', cleaned_name)
    english_name = ' '.join(english_parts)
    english_name = re.sub(r'\s+', ' ', english_name).strip()

    candidates = [
        *sku_candidates,  # SKU/품번 우선
        f"{cleaned_brand} {english_name}".strip(),  # 브랜드 + 영문
        english_name,  # 영문만
        cleaned_brand,  # 브랜드만
    ]

    # 너무 긴 질의는 검색 노이즈가 커져서 앞부분만 사용
    normalized: List[str] = []
    seen = set()
    for query in candidates:
        query = query[:80].strip()
        if len(query) < 2 or query in seen:
            continue
        seen.add(query)
        normalized.append(query)
    return normalized


def fetch_buyma_lowest_price(driver, product_name: str, brand: str, musinsa_sku: str = "") -> str:
    """품번 우선으로 BUYMA 첫 페이지를 검색해 최저가를 반환하고, 실패 시 이름 검색으로 재시도한다"""
    print(f"\n>>> BUYMA 최저가 검색 시작")
    print(f"    상품명: {product_name}, 브랜드: {brand}, 품번: {musinsa_sku}")

    sku_query = re.sub(r'\s+', ' ', (musinsa_sku or '').strip())

    cleaned_name = re.sub(r'\s+', ' ', (product_name or '').strip())
    cleaned_brand = re.sub(r'\s+', ' ', (brand or '').strip())
    english_parts = re.findall(r'[A-Za-z0-9\s\-/]+', cleaned_name)
    english_name = re.sub(r'\s+', ' ', ' '.join(english_parts)).strip()
    english_brand_parts = re.findall(r'[A-Za-z0-9\s\-/]+', cleaned_brand)
    english_brand = re.sub(r'\s+', ' ', ' '.join(english_brand_parts)).strip()

    # 검색 우선순위: 품번 -> 영문상품명 -> 영문 조합 (한글 검색 금지)
    query_candidates = [
        sku_query,
        f"{english_brand} {english_name}".strip() if english_brand and english_name else "",
        english_name,
    ]

    if not sku_query and not english_name and english_brand:
        query_candidates.append(english_brand)

    queries: List[str] = []
    seen = set()
    for candidate in query_candidates:
        query = re.sub(r'\s+', ' ', (candidate or '').strip())
        # BUYMA 검색은 품번/영문만 사용 (한글 포함 질의 금지)
        if re.search(r'[\uac00-\ud7a3]', query):
            continue
        if len(query) < 2 or query in seen:
            continue
        seen.add(query)
        queries.append(query)

    if not queries:
        print("    [검색 질의 없음] 빈 값 반환")
        return ""

    print(f"    검색 시도 순서: {queries}")

    for idx, query in enumerate(queries, start=1):
        try:
            encoded = urllib.parse.quote(query)
            search_url = f"https://www.buyma.com/r/{encoded}/"
            print(f"  [{idx}/{len(queries)}] BUYMA 검색: {query}")
            print(f"    검색 URL: {search_url}")
            driver.get(search_url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(3)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            entries = extract_buyma_listing_entries(soup)
            print(f"    발견된 상품카드(첫 페이지): {len(entries)}개")

            # 검색 결과 카드 URL로 상세페이지 진입 후 가격 확인
            detail_prices: List[int] = []
            listing_matched_prices: List[int] = []
            candidate_entries = entries[:10]
            print(f"    상세페이지 확인 대상: {len(candidate_entries)}개")

            # 카드 수준에서는 더 엄격하게 제목 일치 여부를 본다.
            for entry in candidate_entries:
                if is_relevant_buyma_listing_entry(
                    str(entry.get('title', '')),
                    sku_query,
                    english_name,
                    english_brand,
                ):
                    listing_matched_prices.append(int(entry['price']))

            for entry in candidate_entries:
                item_url = str(entry.get('url', '')).strip()
                if not item_url:
                    continue
                try:
                    driver.get(item_url)
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    time.sleep(1.2)

                    item_soup = BeautifulSoup(driver.page_source, 'html.parser')
                    if not is_relevant_buyma_item(item_soup, sku_query, english_name, english_brand):
                        continue

                    detail_price = extract_buyma_item_page_price(item_soup)
                    if detail_price > 0:
                        detail_prices.append(detail_price)
                except Exception as detail_error:
                    print(f"    상세페이지 스킵: {detail_error}")

            # 상세페이지에서 검증된 가격을 우선 사용하고, 상세 진입이 모두 실패했을 때만 카드 가격으로 보정
            combined_prices = list(detail_prices)
            if not combined_prices:
                combined_prices.extend(listing_matched_prices)

            if combined_prices:
                unique_prices = sorted(set(combined_prices))
                best_price = min(unique_prices)
                detail_min = min(detail_prices) if detail_prices else None
                listing_min = min(listing_matched_prices) if listing_matched_prices else None
                print(
                    f"    셀러가격 통합 통계: {len(unique_prices)}개, "
                    f"최저: {best_price:,}엔, 최고: {max(unique_prices):,}엔, "
                    f"상세최저: {detail_min if detail_min else 'none'}, 카드최저: {listing_min if listing_min else 'none'}"
                )
                return f"{best_price:,}"

            print("    해당 질의에서는 가격을 찾지 못함")
        except Exception as e:
            print(f"    검색 오류: {e}")

    print("  모든 검색 질의 실패 - 빈 값 반환")
    return ""


def extract_musinsa_categories(soup: BeautifulSoup, mss_state: Dict[str, object]) -> Tuple[str, str, str]:
    """무신사 상품 페이지에서 대/중/소 분류를 추출한다."""
    key_candidates = [
        ('categoryDepth1Name', 'categoryDepth2Name', 'categoryDepth3Name'),
        ('dispCatNm1', 'dispCatNm2', 'dispCatNm3'),
        ('itemCategoryDepth1Name', 'itemCategoryDepth2Name', 'itemCategoryDepth3Name'),
    ]
    for k1, k2, k3 in key_candidates:
        v1 = str(mss_state.get(k1, '')).strip()
        v2 = str(mss_state.get(k2, '')).strip()
        v3 = str(mss_state.get(k3, '')).strip()
        if v1 or v2 or v3:
            return v1, v2, v3

    # 일부 상품은 category/categoryInfo 같은 중첩 객체에 담긴다.
    for container_key in ('category', 'categoryInfo', 'itemCategory', 'displayCategory'):
        container = mss_state.get(container_key)
        if not isinstance(container, dict):
            continue
        for k1, k2, k3 in key_candidates:
            v1 = str(container.get(k1, '')).strip()
            v2 = str(container.get(k2, '')).strip()
            v3 = str(container.get(k3, '')).strip()
            if v1 or v2 or v3:
                return v1, v2, v3

        v1 = str(container.get('depth1Name', '')).strip()
        v2 = str(container.get('depth2Name', '')).strip()
        v3 = str(container.get('depth3Name', '')).strip()
        if v1 or v2 or v3:
            return v1, v2, v3

    texts: List[str] = []
    selectors = [
        'nav[aria-label*="breadcrumb"] a',
        'nav[aria-label*="Breadcrumb"] a',
        '.breadcrumb a',
        '[class*="breadcrumb"] a',
    ]
    for selector in selectors:
        tags = soup.select(selector)
        if tags:
            texts = [t.get_text(strip=True) for t in tags if t.get_text(strip=True)]
            break

    if not texts:
        return '', '', ''

    blacklist = {'홈', 'HOME', '무신사', 'MUSINSA'}
    cleaned = [x for x in texts if x and x not in blacklist]
    if not cleaned:
        cleaned = []
        # JSON-LD BreadcrumbList fallback
        for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
            raw_text = script.get_text(strip=True)
            if not raw_text:
                continue
            try:
                payload = json.loads(raw_text)
            except Exception:
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                if candidate.get('@type') != 'BreadcrumbList':
                    continue
                items = candidate.get('itemListElement') or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get('name', '')).strip()
                    if name and name not in blacklist:
                        cleaned.append(name)
        if not cleaned:
            return '', '', ''

    cats = cleaned[-3:]
    while len(cats) < 3:
        cats.insert(0, '')
    return cats[0], cats[1], cats[2]


def _normalize_gender_label(raw_value: str) -> str:
    value = (raw_value or "").strip().lower()
    if not value:
        return ""

    male_tokens = ("남", "남성", "male", "man", "men", "mens", "m")
    female_tokens = ("여", "여성", "female", "woman", "women", "womens", "w")

    if value in male_tokens:
        return "남성"
    if value in female_tokens:
        return "여성"
    if any(t in value for t in ("남성", "male", "mens", " men")):
        return "남성"
    if any(t in value for t in ("여성", "female", "womens", " women")):
        return "여성"
    if value.startswith("m_") or value.endswith("_m"):
        return "남성"
    if value.startswith("w_") or value.endswith("_w"):
        return "여성"
    return ""


def extract_musinsa_gender_large(
    mss_state: Dict[str, object],
    cat_large: str = "",
    cat_middle: str = "",
    cat_small: str = "",
) -> str:
    """무신사 상태값/카테고리 텍스트에서 성별 대분류(남성/여성)를 추출한다."""
    keys = (
        "sex", "gender", "goodsSex", "goodsGender", "targetSex", "targetGender",
        "displaySex", "sexCd", "genderCd", "sexCode", "genderCode",
    )

    values: List[str] = []
    for k in keys:
        values.append(str(mss_state.get(k, "")).strip())

    for container_key in ("category", "categoryInfo", "itemCategory", "displayCategory", "goods"):
        container = mss_state.get(container_key)
        if not isinstance(container, dict):
            continue
        for k in keys:
            values.append(str(container.get(k, "")).strip())

    values.extend([cat_large, cat_middle, cat_small])
    for v in values:
        label = _normalize_gender_label(v)
        if label:
            return label
    return ""


def remap_categories_with_gender(
    gender_large: str,
    cat_large: str,
    cat_middle: str,
    cat_small: str,
) -> Tuple[str, str, str]:
    """성별을 대분류로 고정하고, 나머지 카테고리를 중/소로 재배치한다."""
    if not gender_large:
        return cat_large, cat_middle, cat_small

    rest: List[str] = []
    for v in (cat_large, cat_middle, cat_small):
        text = (v or "").strip()
        if not text:
            continue
        if _normalize_gender_label(text):
            continue
        rest.append(text)

    new_middle = rest[0] if len(rest) > 0 else ""
    new_small = rest[1] if len(rest) > 1 else ""
    return gender_large, new_middle, new_small


def scrape_musinsa_product(
    driver,
    url: str,
    row_num: int,
    existing_sku: str = "",
    download_images: bool = False,
    images_only: bool = False,
) -> dict:
    """Selenium을 사용하여 무신사 상품 페이지에서 A~O 구조용 정보를 추출"""
    try:
        print(f"    페이지 로드 중... {url}")
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        title_text = soup.title.string.strip() if soup.title else ""
        product_json = extract_product_json(soup)
        mss_state = extract_mss_product_state(soup)
        goods_no = str(mss_state.get('goodsNo', '')).strip()

        raw_product_name = str(mss_state.get('goodsNm') or product_json.get('name', '')).strip()
        product_name = clean_product_name(raw_product_name)
        if product_name == "상품명 미확인" and title_text:
            product_name = clean_product_name(
                re.split(r'\s*-\s*사이즈|\s*\|\s*무신사|\s*-\s*무신사', title_text)[0].strip()
            )

        if images_only:
            image_paths = ""
            if download_images:
                image_urls = extract_musinsa_thumbnail_urls(soup, product_json, goods_no)
                image_folder_name = build_image_folder_name(row_num, product_name)
                image_paths = download_thumbnail_images(image_urls, image_folder_name)

            return {
                'brand': '',
                'brand_en': '',
                'product_name_kr': product_name,
                'color_kr': '',
                'size': '',
                'actual_size': '못찾음',
                'price': '',
                'buyma_price': '',
                'musinsa_sku': existing_sku.strip() if existing_sku else '',
                'image_paths': image_paths,
                'opt_kind_cd': '',
                'musinsa_category_large': '',
                'musinsa_category_middle': '',
                'musinsa_category_small': '',
            }

        goods_sale_type = str(mss_state.get('goodsSaleType', 'SALE')).strip()
        opt_kind_cd = str(mss_state.get('optKindCd', '')).strip()
        goods_options = fetch_goods_options(goods_no, goods_sale_type, opt_kind_cd)

        if product_name == "상품명 미확인":
            selectors_name = [
                'h1',
                '[class*="title"]',
                '.product-detail__sc-190p98n-0', # 무신사 최신 클래스 대응
                '[class*="product_title"]',
                'div[class*="name"]',
                '.product-title',
            ]
            for selector in selectors_name:
                tag = soup.select_one(selector)
                if tag:
                    text = tag.get_text(separator=' ', strip=True)
                    if text and len(text) > 5:
                        product_name = clean_product_name(text)
                        break

        musinsa_sku = extract_musinsa_sku(raw_product_name, product_name, mss_state, product_json, soup)
        if not musinsa_sku and existing_sku:
            print(f"    [품번 fallback] 무신사에서 품번을 못 찾아 시트 내 품번 사용: {existing_sku}")
            musinsa_sku = existing_sku.strip()

        brand = extract_brand_text(product_json, title_text)
        color_from_name = normalize_korean_color(extract_color_from_name(raw_product_name))
        color_from_api = extract_color_from_api(goods_options)
        size_text, color_from_size = extract_sizes_from_api(goods_no, goods_sale_type, opt_kind_cd)
        actual_size_text = extract_actual_size_text(goods_no)
        if not actual_size_text:
            actual_size_text = "못찾음"

        # 실제 옵션 색상을 우선 반영한다. (size 파싱 > 옵션 API > 상품명)
        if color_from_size:
            color_kr = color_from_size
        elif color_from_api:
            color_kr = color_from_api
        else:
            color_kr = color_from_name
        if not color_kr:
            color_kr = "none"
        if not size_text:
            size_text = extract_sizes(soup, opt_kind_cd)

        # J열은 쿠폰가가 아닌 상품 할인판매가를 우선 사용
        discounted_price_text = extract_discounted_product_price(soup)
        if discounted_price_text != "가격 미확인":
            price_text = discounted_price_text
        else:
            price_text = format_price(product_json.get('offers', {}).get('price') if isinstance(product_json.get('offers'), dict) else None)
        price_selectors = [
            '[class*="CurrentPrice"]',
            '[class*="CalculatedPrice"]',
            '[class*="DiscountWrap"]',
            '[class*="PriceTotalWrap"]',
            '.product-detail__sc-1p1ulhg-6', # 최신 가격 클래스
            '[class*="PriceWrap"]',
            '[class*="price"]',
            '[class*="product_price"]',
            '[class*="sale_price"]',
            '[class*="original_price"]',
        ]
        if price_text == "가격 미확인":
            for selector in price_selectors:
                for price_tag in soup.select(selector):
                    text = price_tag.get_text(separator=' ', strip=True)
                    if '결제 시' in text and '할인' in text:
                        continue
                    normalized = normalize_price(text)
                    if normalized != "가격 미확인":
                        price_text = normalized
                        break
                if price_text != "가격 미확인":
                    break

        if price_text == "가격 미확인":
            page_text = soup.get_text()
            matches = re.findall(r'(\d{1,3}(?:,\d{3})*)\s*원', page_text)
            if matches:
                price_text = normalize_price(matches[0])

        image_paths = ""
        if download_images:
            image_urls = extract_musinsa_thumbnail_urls(soup, product_json, goods_no)
            image_folder_name = build_image_folder_name(row_num, product_name)
            image_paths = download_thumbnail_images(image_urls, image_folder_name)
        buyma_price_text = fetch_buyma_lowest_price(driver, product_name, brand, musinsa_sku)
        cat_large, cat_middle, cat_small = extract_musinsa_categories(soup, mss_state)
        gender_large = extract_musinsa_gender_large(mss_state, cat_large, cat_middle, cat_small)
        if gender_large:
            cat_large, cat_middle, cat_small = remap_categories_with_gender(
                gender_large, cat_large, cat_middle, cat_small
            )
        if cat_large or cat_middle or cat_small:
            print(f"    무신사 카테고리 추출: 대='{cat_large}' / 중='{cat_middle}' / 소='{cat_small}'")
        else:
            print("    무신사 카테고리 추출 실패: 대/중/소가 비어 있습니다.")

        # 영문 브랜드명 추출 (상품 페이지로 돌아간 뒤 브랜드 페이지 방문)
        driver.get(url)
        time.sleep(2)
        brand_en = extract_brand_en_from_musinsa(driver, url)
        if brand_en:
            print(f"   영문 브랜드: {brand_en}")

        return {
            'brand': brand,
            'brand_en': brand_en,
            'product_name_kr': product_name,
            'color_kr': color_kr,
            'size': size_text,
            'actual_size': actual_size_text,
            'price': price_text,
            'buyma_price': buyma_price_text,
            'musinsa_sku': musinsa_sku,
            'image_paths': image_paths,
            'opt_kind_cd': opt_kind_cd,
            'musinsa_category_large': cat_large,
            'musinsa_category_middle': cat_middle,
            'musinsa_category_small': cat_small,
        }
    except Exception as e:
        print(f"   크롤링 오류 발생: {e}")
        return {
            'brand': '',
            'brand_en': '',
            'product_name_kr': '상품명 미확인',
            'color_kr': 'none',
            'size': '',
            'actual_size': '못찾음',
            'price': '가격 미확인',
            'buyma_price': '',
            'musinsa_sku': '',
            'image_paths': '',
            'opt_kind_cd': '',
            'musinsa_category_large': '',
            'musinsa_category_middle': '',
            'musinsa_category_small': '',
        }


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

