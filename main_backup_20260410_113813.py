"""
무신사 상품 정보를 크롤링하여 Google Sheets에 자동으로 입력하는 자동화 스크립트
아래 링크의 스프레드시트 구조와 동일하게 사용할 수 있도록 데이터를 입력합니다.
- 시트 ID: 1mTV-Fcybov-0uC7tNyM_GXGDoth8F_7wM__zaC1fAjs
- 탭 GID: 1698424449
"""

import json
import argparse
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple
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

# 시트 열 구조
SEQUENCE_COLUMN = "A"
URL_COLUMN = "B"
BRAND_COLUMN = "C"
PRODUCT_NAME_KR_COLUMN = "D"
PRODUCT_NAME_EN_COLUMN = "E"
MUSINSA_SKU_COLUMN = "F"
COLOR_KR_COLUMN = "G"
COLOR_EN_COLUMN = "H"
SIZE_COLUMN = "I"
PRICE_COLUMN = "J"
BAIMA_SELL_PRICE_COLUMN = "K"
ROW_START = 2

# Selenium 설정
HEADLESS = True  # True = 백그라운드 실행, False = 브라우저 창 보기

# 감시 모드 기본값(초)
WATCH_INTERVAL_SECONDS = 20

# ==================== Google Sheets 연동 ====================

def get_sheets_service():
    """Google Sheets API 서비스 객체 생성"""
    try:
        creds = Credentials.from_service_account_file(
            'credentials.json',
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
    """상품명에서 색상 정보를 우선순위 기반으로 추출한다"""
    if not raw_name:
        return ""

    cleaned = re.sub(r'\s*/\s*[A-Z0-9-]+$', '', raw_name).strip()
    _, color_part = split_name_and_color(cleaned)
    if color_part:
        return color_part

    bracket_match = re.search(r'\[([^\[\]]{1,50})\]\s*$', cleaned)
    if bracket_match:
        return bracket_match.group(1).strip()

    paren_match = re.search(r'\(([^()]{1,50})\)\s*$', cleaned)
    if paren_match:
        candidate = paren_match.group(1).strip()
        if any(token in candidate for token in ['/', ',', '-', ':']) or has_hangul(candidate):
            return candidate

    return ""


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
        if value:
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

    color_map = get_color_name_map()
    color_names: List[str] = []
    for item in goods_options.get('optionItems', []):
        for color in item.get('colors', []):
            color_code = str(color.get('colorCode', '')).strip()
            color_name = color_map.get(color_code, '').strip()
            if color_name and color_name not in color_names:
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
    for option in options_data.get('basic', []):
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
    """숫자 또는 문자열 가격을 원화 문자열로 변환한다"""
    if isinstance(price_value, (int, float)):
        return f"{int(price_value):,}원"
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
    """현재 행의 A~K 값을 읽어 컬럼별로 반환한다"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!A{row_num}:K{row_num}"
        ).execute()
        rows = result.get('values', [])
        row = rows[0] if rows else []

        columns = [
            SEQUENCE_COLUMN, URL_COLUMN, BRAND_COLUMN, PRODUCT_NAME_KR_COLUMN,
            PRODUCT_NAME_EN_COLUMN, MUSINSA_SKU_COLUMN, COLOR_KR_COLUMN, COLOR_EN_COLUMN, SIZE_COLUMN,
            PRICE_COLUMN, BAIMA_SELL_PRICE_COLUMN,
        ]
        existing = {}
        for index, column in enumerate(columns):
            existing[column] = row[index] if index < len(row) else ""
        return existing
    except Exception as e:
        print(f" {sheet_name} {row_num}행 기존 데이터 조회 실패: {e}")
        return {}


def get_existing_rows_bulk(
    service,
    sheet_name: str,
    row_numbers: List[int],
) -> Dict[int, Dict[str, str]]:
    """여러 행의 A~K 값을 한 번에 읽어 행 번호별 맵으로 반환한다"""
    if not row_numbers:
        return {}

    min_row = min(row_numbers)
    max_row = max(row_numbers)
    columns = [
        SEQUENCE_COLUMN, URL_COLUMN, BRAND_COLUMN, PRODUCT_NAME_KR_COLUMN,
        PRODUCT_NAME_EN_COLUMN, MUSINSA_SKU_COLUMN, COLOR_KR_COLUMN, COLOR_EN_COLUMN, SIZE_COLUMN,
        PRICE_COLUMN, BAIMA_SELL_PRICE_COLUMN,
    ]

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!A{min_row}:K{max_row}"
        ).execute()
        values = result.get('values', [])

        row_map: Dict[int, Dict[str, str]] = {}
        for offset, row_num in enumerate(range(min_row, max_row + 1)):
            row_values = values[offset] if offset < len(values) else []
            mapped = {}
            for index, column in enumerate(columns):
                mapped[column] = row_values[index] if index < len(row_values) else ""
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
        (PRODUCT_NAME_KR_COLUMN, product_info.get('product_name_kr', '')),
        (MUSINSA_SKU_COLUMN, product_info.get('musinsa_sku', '')),
        (COLOR_KR_COLUMN, product_info.get('color_kr', '')),
        (SIZE_COLUMN, product_info.get('size', '')),
        (PRICE_COLUMN, product_info.get('price', '')),
        (BAIMA_SELL_PRICE_COLUMN, product_info.get('buyma_price', '')),
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


def row_needs_update(existing_values: Dict[str, str]) -> bool:
    """자동 입력 대상 열(C, D, F, G, I, J, K) 중 빈 칸이 있으면 True"""
    target_columns = [
        BRAND_COLUMN,
        PRODUCT_NAME_KR_COLUMN,
        MUSINSA_SKU_COLUMN,
        COLOR_KR_COLUMN,
        SIZE_COLUMN,
        PRICE_COLUMN,
        BAIMA_SELL_PRICE_COLUMN,
    ]
    for column in target_columns:
        if is_empty_cell(existing_values.get(column, "")):
            return True
    return False


def row_has_existing_output(existing_values: Dict[str, str]) -> bool:
    """자동 입력 대상 열에 이미 값이 하나라도 있으면 True"""
    target_columns = [
        BRAND_COLUMN,
        PRODUCT_NAME_KR_COLUMN,
        MUSINSA_SKU_COLUMN,
        COLOR_KR_COLUMN,
        SIZE_COLUMN,
        PRICE_COLUMN,
        BAIMA_SELL_PRICE_COLUMN,
    ]
    for column in target_columns:
        if not is_empty_cell(existing_values.get(column, "")):
            return True
    return False


def write_to_sheet(
    service,
    sheet_name: str,
    row_num: int,
    product_info: Dict[str, str],
    existing_values: Dict[str, str] = None,
):
    """Google Sheets의 A, C~K 열에 한 행 데이터를 쓴다"""
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


def process_sheet_once(service, driver, sheet_name: str, watch_mode: bool = False):
    """단일 시트를 1회 스캔하여 필요한 행만 처리"""
    print(f"'{sheet_name}' 시트에서 B열 링크를 읽는 중...")
    rows = read_urls_from_sheet(service, sheet_name)
    if not rows:
        print(f"'{sheet_name}' 시트의 B열에 처리할 URL이 없습니다.")
        return

    row_numbers = [row_num for row_num, _ in rows]
    existing_rows_map = get_existing_rows_bulk(service, sheet_name, row_numbers)

    target_rows: List[Tuple[int, str]] = []
    for row_num, url in rows:
        existing_values = existing_rows_map.get(row_num, {})
        if watch_mode and row_has_existing_output(existing_values):
            continue
        if row_needs_update(existing_values):
            target_rows.append((row_num, url))

    if not target_rows:
        print(f"'{sheet_name}' 시트: 신규 작성 대상이 없습니다.")
        return

    print(f"'{sheet_name}' 시트: {len(target_rows)}개 행을 처리합니다.")
    for idx, url in target_rows:
        print(f"[{sheet_name}] {idx}행 처리 중: {url}")
        existing_values_for_row = existing_rows_map.get(idx, {})
        sheet_sku = existing_values_for_row.get(MUSINSA_SKU_COLUMN, "")
        product_info = scrape_musinsa_product(driver, url, existing_sku=sheet_sku)
        write_to_sheet(
            service,
            sheet_name,
            idx,
            product_info,
            existing_rows_map.get(idx, {}),
        )
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

    # 우선순위 1: '価格 ¥13,220' 형태의 기본 판매가격
    direct_match = re.search(r'価格\s*[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})', page_text)
    if direct_match:
        try:
            return int(direct_match.group(1).replace(',', ''))
        except ValueError:
            pass

    # 우선순위 2: 가격 관련 영역에서 엔화 값 추출
    price_candidates: List[int] = []
    selectors = [
        '[class*="price"]',
        '[class*="Price"]',
        '.product_price',
        '.Price_Txt',
    ]
    for selector in selectors:
        for tag in soup.select(selector):
            price_candidates.extend(extract_yen_values(tag.get_text(' ', strip=True)))

    # 0원/비정상 저가를 제외하고 반환
    price_candidates = [p for p in price_candidates if p >= 3000]
    if price_candidates:
        return min(price_candidates)
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
    haystack = f"{title_text} {soup.get_text(' ', strip=True)[:2000]}".lower()

    sku = (musinsa_sku or '').strip().lower()
    if sku:
        if sku in haystack:
            return True
        # SKU 일부만 포함된 경우 대비
        if len(sku) >= 6 and sku[:6] in haystack:
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
        english_name,
        f"{english_brand} {english_name}".strip() if english_brand and english_name else "",
        english_brand,
    ]

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
        print("    [검색 질의 없음] none 반환")
        return "none"

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

            # 카드 수준에서 먼저 관련도 매칭(상세 진입 실패시 fallback용)
            query_tokens = [
                t for t in re.findall(r'[a-z0-9]{3,}', query.lower())
                if t not in {'with', 'from', 'size', 'color', 'black', 'white'}
            ]
            sku_lower = sku_query.lower()
            for entry in candidate_entries:
                title_lower = str(entry.get('title', '')).lower()
                if sku_lower and (sku_lower in title_lower or (len(sku_lower) >= 6 and sku_lower[:6] in title_lower)):
                    listing_matched_prices.append(int(entry['price']))
                    continue

                if query_tokens:
                    hits = sum(1 for token in query_tokens if token in title_lower)
                    if hits >= 1:
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

            # 상세페이지 추출이 일부 누락될 수 있어 카드매칭 가격과 함께 최저가를 계산
            combined_prices = list(detail_prices)
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

    print("  모든 검색 질의 실패 - none 반환")
    return "none"


def scrape_musinsa_product(driver, url: str, existing_sku: str = "") -> dict:
    """Selenium을 사용하여 무신사 상품 페이지에서 A~L 구조용 정보를 추출"""
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
        goods_sale_type = str(mss_state.get('goodsSaleType', 'SALE')).strip()
        opt_kind_cd = str(mss_state.get('optKindCd', '')).strip()
        goods_options = fetch_goods_options(goods_no, goods_sale_type, opt_kind_cd)

        raw_product_name = str(mss_state.get('goodsNm') or product_json.get('name', '')).strip()
        product_name = clean_product_name(raw_product_name)
        if product_name == "상품명 미확인" and title_text:
            product_name = clean_product_name(
                re.split(r'\s*-\s*사이즈|\s*\|\s*무신사|\s*-\s*무신사', title_text)[0].strip()
            )

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
        color_kr_raw = extract_color_from_name(raw_product_name)
        color_kr = normalize_korean_color(color_kr_raw)
        if not color_kr:
            color_kr = extract_color_from_api(goods_options)
        size_text, color_from_size = extract_sizes_from_api(goods_no, goods_sale_type, opt_kind_cd)
        if color_from_size:
            color_kr = color_from_size
        if not color_kr:
            color_kr = "none"
        if not size_text:
            size_text = extract_sizes(soup, opt_kind_cd)

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

        buyma_price_text = fetch_buyma_lowest_price(driver, product_name, brand, musinsa_sku)

        return {
            'brand': brand,
            'product_name_kr': product_name,
            'color_kr': color_kr,
            'size': size_text,
            'price': price_text,
            'buyma_price': buyma_price_text,
            'musinsa_sku': musinsa_sku,
        }
    except Exception as e:
        print(f"   크롤링 오류 발생: {e}")
        return {
            'brand': '',
            'product_name_kr': '상품명 미확인',
            'color_kr': 'none',
            'size': '',
            'price': '가격 미확인',
            'buyma_price': '',
            'musinsa_sku': '',
        }


def main():
    args = parse_args()
    print("Starting Musinsa data extraction")
    service = get_sheets_service()
    sheet_names = get_target_sheet_names(service)

    driver = setup_chrome_driver()
    try:
        if args.watch:
            interval = max(5, int(args.interval))
            print(f"감시 모드 시작: {interval}초 간격으로 새 링크를 확인합니다.")
            while True:
                for sheet_name in sheet_names:
                    process_sheet_once(service, driver, sheet_name, watch_mode=True)
                print(f"다음 확인까지 {interval}초 대기...")
                time.sleep(interval)
        else:
            for sheet_name in sheet_names:
                process_sheet_once(service, driver, sheet_name, watch_mode=False)
            print("모든 시트 처리가 완료되었습니다.")
    finally:
        driver.quit()
        print("브라우저를 종료합니다.")


if __name__ == "__main__":
    main()
