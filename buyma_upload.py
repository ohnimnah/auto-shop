"""
BUYMA 출품 자동화 모듈.

Google Sheets의 상품 정보를 BUYMA 출품 페이지에 자동 입력한다.

Usage:
    python buyma_upload.py
    python buyma_upload.py --scan
    python buyma_upload.py --row 2
    python buyma_upload.py --mode review
    python buyma_upload.py --mode auto
"""

import argparse
import glob
import json
import os
import re
import sys
import unicodedata

# Windows cp949 환경에서 유니코드 출력 오류 방지
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") in ("cp949", "euckr"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

# 전체 대기시간 스케일링: 환경변수 AUTO_SHOP_WAIT_SCALE (기본 0.6)
_RAW_SLEEP = time.sleep
try:
    WAIT_SCALE = float(os.environ.get('AUTO_SHOP_WAIT_SCALE', '0.6'))
except Exception:
    WAIT_SCALE = 0.6
if WAIT_SCALE <= 0:
    WAIT_SCALE = 0.1


def _sleep(seconds: float) -> None:
    _RAW_SLEEP(max(0.0, seconds * WAIT_SCALE))

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from category_correction import correct_buyma_category
from marketplace.common import sheet_source as common_sheet_source_mod
from marketplace.common.runtime import get_runtime_data_dir as common_get_runtime_data_dir
from marketplace.buyma import category as buyma_category_mod
from marketplace.buyma import images as buyma_images_mod
from marketplace.buyma import login as buyma_login_mod
from marketplace.buyma import mapper as buyma_mapper_mod
from marketplace.buyma import options as buyma_options_mod
from marketplace.buyma import selectors as buyma_selectors
from marketplace.buyma import submit as buyma_submit_mod
from marketplace.buyma import ui as buyma_ui_mod
from marketplace.buyma import uploader as buyma_uploader_mod
from marketplace.buyma import validate as buyma_validate_mod

# main.py와 동일한 시트 정보
SPREADSHEET_ID = "1mTV-Fcybov-0uC7tNyM_GXGDoth8F_7wM__zaC1fAjs"
SHEET_GIDS = [1698424449]
SHEET_NAME = "시트1"
ROW_START = 2
HEADER_ROW = 1
PROGRESS_STATUS_HEADER = "진행상태"
STATUS_UPLOAD_READY = "썸네일완료"
STATUS_THUMBNAILS_DONE = "썸네일완료"
STATUS_UPLOADING = "업로드중"
STATUS_COMPLETED = "출품완료"
JP_SHITEI_NASHI = buyma_selectors.JP_SHITEI_NASHI  # 指定なし
JP_SIZE_SHITEI_NASHI = buyma_selectors.JP_SIZE_SHITEI_NASHI  # サイズ指定なし


def get_runtime_data_dir() -> str:
    """런처/CLI가 지정한 런타임 데이터 폴더를 반환한다."""
    env_data_dir = os.environ.get("AUTO_SHOP_DATA_DIR", "").strip()
    if env_data_dir:
        return os.path.abspath(os.path.expanduser(env_data_dir))
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return os.path.join(local_app_data, "auto_shop")
    return os.path.join(os.path.expanduser("~"), ".auto_shop")


def _normalize_jp_match_text(text: str) -> str:
    return (text or "").strip().replace(" ", "").replace("\u3000", "")


def _is_shitei_nashi_text(text: str) -> bool:
    normalized = _normalize_jp_match_text(text)
    return JP_SHITEI_NASHI in normalized or JP_SIZE_SHITEI_NASHI in normalized


def _load_sheet_runtime_config() -> None:
    """로컬에서 저장한 시트 설정파일을 읽어 기본값을 반영한다."""
    global SPREADSHEET_ID, SHEET_GIDS, SHEET_NAME, ROW_START
    data_dir = get_runtime_data_dir()

    cfg_path = os.path.join(data_dir, 'sheets_config.json')
    if not os.path.exists(cfg_path):
        return

    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return

        sid = common_sheet_source_mod.extract_spreadsheet_id(cfg.get('spreadsheet_id') or '')
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

BUYMA_SELL_URL = buyma_selectors.BUYMA_SELL_URL

# Chrome 프로필 경로 (세션/쿠키 유지)
CHROME_PROFILE_DIR = os.path.join(get_runtime_data_dir(), "chrome_profile")


BUYMA_COMMENT_TEMPLATE = """
カテゴリ, ファミリーページ, 親子リンク
国際便（OCS）：商品準備2-5日＋発送～到着7-9日
平常時は安定ですが、繁忙期・異常時は到着日が前後する場合もございます。詳しくはお問い合わせください。
当店で万一不良・不具合がある場合は交換対応しております。当理由でお時間頂く場合は都度ご報告させていただきます。

お荷物追跡番号ありにて発送しますので、随時配送状況をご確認いただけます。
土日祝は休務、休明けに順次対応します。

海外製品はMADE IN JAPANの製品と比べて若干見劣りする場合がございます。
返品・交換にあたって不具合案件に関してはお取引ついてをご確認ください。

当店では即日完売品や日本未入荷アイテム、限定品など
メンズ、レディース、キッズ、シューズ（スニーカー等）や衣類をメインに取り扱っております。
【ご注意事項】
・海外製品は日本製品と比べて検品基準が低い場合がございます。
・縫製の甘さ、縫い終わり部分の糸が残っている場合がございます。
・生地のムラ、プリントのズレ、若干のシミ、製造過程での小さな傷等がある場合がございます。
・製品のサイズ測定方法によっては、1～3cm程度の誤差が生じる場合がございます。
・返品・交換に関する規定はBUYMA規定に準じます。お客様都合による返品はお受けできかねますので、ご購入は慎重にお願いいたします。
・不良品・誤配送は交換または返品が可能です。
""".strip()

# 시트 컬럼 인덱스(A=0, B=1, ..., M=12)
COL = {
    'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5,
    'G': 6, 'H': 7, 'I': 8, 'J': 9, 'K': 10, 'L': 11,
    'M': 12, 'N': 13, 'O': 14, 'P': 15, 'Q': 16, 'R': 17,
    'S': 18, 'T': 19, 'U': 20, 'V': 21, 'W': 22, 'X': 23,
    'Y': 24, 'Z': 25,
}


def get_credentials_path() -> str:
    """자격증명 파일 경로 반환"""
    cred = os.path.join(get_runtime_data_dir(), "credentials.json")
    if os.path.exists(cred):
        return cred
    fallback = os.path.join(os.path.dirname(__file__), 'credentials.json')
    if os.path.exists(fallback):
        return fallback
    raise FileNotFoundError("credentials.json 파일을 찾을 수 없습니다")


def get_sheets_service():
    """Create Google Sheets API service."""
    creds = Credentials.from_service_account_file(
        get_credentials_path(),
        scopes=['https://www.googleapis.com/auth/spreadsheets'],
    )
    return build('sheets', 'v4', credentials=creds)


def get_sheet_name(service) -> str:
    """Find sheet name from configured GID."""
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta.get('sheets', []):
        if s['properties']['sheetId'] == SHEET_GIDS[0]:
            return s['properties']['title']
    return SHEET_NAME


def read_upload_rows(service, sheet_name: str, specific_row: int = 0) -> List[Dict[str, str]]:
    """Read upload target rows from sheet. Only rows with BUYMA price are included."""
    header_map = get_sheet_header_map(service, sheet_name)
    status_index = header_map.get(PROGRESS_STATUS_HEADER)
    last_index = max(COL['Y'], status_index if status_index is not None else COL['Y'])
    last_col_letter = column_index_to_letter(last_index)

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!A{ROW_START}:{last_col_letter}1000",
        ).execute()
    except Exception as e:
        print(f"시트 읽기 실패: {e}")
        return []

    rows_data = []
    for idx, row in enumerate(result.get('values', []), start=ROW_START):
        if specific_row and idx != specific_row:
            continue

        def cell(col_letter: str) -> str:
            i = COL[col_letter]
            return row[i].strip() if i < len(row) and row[i] else ""

        def cell_by_index(index: int | None) -> str:
            if index is None:
                return ""
            return row[index].strip() if index < len(row) and row[index] else ""

        # 최소 조건: URL + 상품명 + 바이마 판매가 있어야 출품 대상
        url = cell('B')
        product_name = cell('E')
        buyma_price = cell('M')

        if not url or not product_name or not buyma_price:
            if specific_row and idx == specific_row:
                missing = []
                if not url:
                    missing.append("URL(B열)")
                if not product_name:
                    missing.append("상품명(E열)")
                if not buyma_price:
                    missing.append("바이마판매가(M열)")
                print(f"  {idx}행 제외: 필수값 누락 -> {', '.join(missing)}")
            continue

        progress_status = cell_by_index(status_index)
        normalized_status = (progress_status or "").strip()
        # 특정 행 테스트 모드에서는 상태 필터를 우회한다.
        if not specific_row:
            if normalized_status == STATUS_COMPLETED:
                print(f"  {idx}행 건너뜀 (진행상태: {progress_status})")
                continue

            if normalized_status in {STATUS_UPLOADING, "UPLOADING"}:
                continue

            if status_index is not None and normalized_status not in {
                STATUS_UPLOAD_READY,
                STATUS_THUMBNAILS_DONE,
                "THUMBNAILS_DONE",
                "업로드진행대기",
            }:
                continue

        v_cat = cell('V')
        w_cat = cell('W')
        x_cat = cell('X')
        y_cat = cell('Y')

        def _looks_price_like(text: str) -> bool:
            t = (text or '').strip()
            if not t:
                return False
            if any(sym in t for sym in ['₩', '¥', '$']):
                return True
            digits = sum(ch.isdigit() for ch in t)
            return digits >= max(4, len(t) // 2)

        # 최신 시트: W/X/Y(대/중/소), 구형 시트: V/W/X
        if w_cat or x_cat or y_cat:
            cat_large, cat_middle, cat_small = w_cat, x_cat, y_cat
        else:
            cat_large, cat_middle, cat_small = v_cat, w_cat, x_cat

        rows_data.append({
            'row_num': idx,
            'url': url,
            'brand': cell('C'),
            'brand_en': cell('D'),
            'product_name_kr': product_name,
            'product_name_en': cell('F'),
            'musinsa_sku': cell('G'),
            'color_kr': cell('H'),
            'color_en': cell('I'),
            'size': cell('J'),
            'actual_size': cell('K'),
            'price_krw': cell('L'),
            'buyma_price': buyma_price,
            'image_paths': cell('N'),
            'shipping_cost': cell('O'),
            'musinsa_category_large': cat_large,
            'musinsa_category_middle': cat_middle,
            'musinsa_category_small': cat_small,
            'progress_status': progress_status,
        })


    return rows_data

def scan_form_structure(driver):
    """Scan and print BUYMA form structure (debug)."""
    driver.get(BUYMA_SELL_URL)
    _sleep(5)

    print("\n=== 바이마 출품 폼 구조 스캔 ===\n")

    # input ?소
    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[type='file']")
    print(f"[INPUT 입력] ({len(inputs)}개)")
    for inp in inputs:
        name = inp.get_attribute('name') or ''
        id_attr = inp.get_attribute('id') or ''
        placeholder = inp.get_attribute('placeholder') or ''
        input_type = inp.get_attribute('type') or ''
        print(f"  name={name}, id={id_attr}, type={input_type}, placeholder={placeholder}")

    # textarea
    textareas = driver.find_elements(By.TAG_NAME, "textarea")
    print(f"\n[TEXTAREA] ({len(textareas)}개)")
    for ta in textareas:
        name = ta.get_attribute('name') or ''
        id_attr = ta.get_attribute('id') or ''
        print(f"  name={name}, id={id_attr}")

    # select
    selects = driver.find_elements(By.TAG_NAME, "select")
    print(f"\n[SELECT] ({len(selects)}개)")
    for sel in selects:
        name = sel.get_attribute('name') or ''
        id_attr = sel.get_attribute('id') or ''
        options = sel.find_elements(By.TAG_NAME, "option")
        opt_texts = [o.text.strip() for o in options[:10]]
        print(f"  name={name}, id={id_attr}, options(~10): {opt_texts}")

    # button/submit
    buttons = driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
    print(f"\n[BUTTON] ({len(buttons)}개)")
    for btn in buttons:
        text = btn.text.strip() or btn.get_attribute('value') or ''
        btn_type = btn.get_attribute('type') or ''
        btn_class = btn.get_attribute('class') or ''
        print(f"  text={text}, type={btn_type}, class={btn_class[:60]}")

    # 임시 HTML 저장(디버그용)
    html_path = os.path.join(os.path.dirname(__file__), '_buyma_form_scan.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(driver.page_source)
    print(f"\n폼 HTML 저장: {html_path}")


def resolve_image_files(image_paths_cell: str) -> List[str]:
    """Resolve image file list from sheet cell path string."""
    if not image_paths_cell:
        return []

    # 이미지가 저장된 기본 경로
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    data_dir = os.path.join(local_app_data, 'auto_shop') if local_app_data else os.path.expanduser('~/.auto_shop')
    images_root = os.path.join(data_dir, 'images')
    workspace_images_root = os.path.join(os.path.dirname(__file__), 'images')

    files = []
    candidate_dirs = []
    for part in image_paths_cell.split(','):
        path = part.strip()
        if not path:
            continue

        norm_path = path.replace('\\', '/').lstrip('./')
        if norm_path.lower().startswith('images/'):
            # 시트에 images/가 두 번 들어가면 루트 중복 방지
            norm_path = norm_path[len('images/'):]

        # 상대경로는 images_root 기준 경로
        if os.path.isabs(path):
            candidate_paths = [path]
        else:
            candidate_paths = [
                os.path.join(images_root, norm_path),
                os.path.join(workspace_images_root, norm_path),
            ]

        for full_path in candidate_paths:
            if os.path.isfile(full_path):
                files.append(os.path.abspath(full_path))
                candidate_dirs.append(os.path.dirname(os.path.abspath(full_path)))
                break
            if os.path.isdir(full_path):
                # 폴더라면 하위 이미지 모두
                for ext in ('*.jpg', '*.jpeg', '*.png', '*.webp'):
                    files.extend(sorted(glob.glob(os.path.join(full_path, ext))))
                candidate_dirs.append(os.path.abspath(full_path))
                break

    # 우선 썸네일이 폴더에 있으면 첫번째로 올림
    priority_names = [
        '00_thumb_main.jpg',
        '00_thumbnail.jpg',
        '00_main.jpg',
    ]
    prepend = []
    seen_dirs = set()
    for d in candidate_dirs:
        if not d or d in seen_dirs:
            continue
        seen_dirs.add(d)
        for name in priority_names:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                prepend.append(os.path.abspath(p))
                break

    if prepend:
        existing = set(prepend)
        files = prepend + [f for f in files if f not in existing]

    return files


def _scroll_and_click(driver, element):
    """Scroll element into view and click safely."""
    return buyma_ui_mod.scroll_and_click(driver, element, sleep_fn=_sleep)


def _infer_color_system(color_text: str) -> str:
    """Map color text to BUYMA color system labels."""
    c = (color_text or '').strip().lower()
    if not c or c == 'none':
        return '色指定なし'
    if any(k in c for k in ['black', '블랙', '검정']):
        return 'ブラック系'
    if any(k in c for k in ['white', 'ivory', '오프화이트', '아이보리', '흰']):
        return 'ホワイト系'
    if any(k in c for k in ['gray', 'grey', '그레이', '회색']):
        return 'グレー系'
    if any(k in c for k in ['beige', 'camel', '베이지', '카멜']):
        return 'ベージュ系'
    if any(k in c for k in ['brown', '브라운', '갈색']):
        return 'ブラウン系'
    if any(k in c for k in ['pink', '핑크']):
        return 'ピンク系'
    if any(k in c for k in ['red', '레드', '빨강']):
        return 'レッド系'
    if any(k in c for k in ['orange', '오렌지']):
        return 'オレンジ系'
    if any(k in c for k in ['yellow', '옐로우', '노랑']):
        return 'イエロー系'
    if any(k in c for k in ['green', 'khaki', 'olive', '그린', '카키', '올리브']):
        return 'グリーン系'
    if any(k in c for k in ['blue', 'navy', '블루', '네이비']):
        return 'ブルー系'
    if any(k in c for k in ['purple', 'violet', '퍼플', '보라']):
        return 'パープル系'
    if any(k in c for k in ['gold', '실버', 'silver', 'metal', '메탈']):
        return 'シルバー・ゴールド系'
    return 'マルチカラー'


def _select_color_system(driver, color_system: str, row_index: int = 0) -> bool:
    """색상계통 Select에서 컬러에 맞는 옵션을 선택한다."""
    try:
        color_selects = driver.find_elements(By.CSS_SELECTOR, ".sell-color-table .Select")
        if not color_selects:
            return False
        color_select = color_selects[min(row_index, len(color_selects) - 1)]
        control = color_select.find_element(By.CSS_SELECTOR, ".Select-control")
        _scroll_and_click(driver, control)
        _sleep(0.4)

        # 드롭다운 옵션에서 목표 색상 우선 선택
        options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
        if options:
            target = color_system.replace('系', '')
            for opt in options:
                txt = opt.text.strip()
                if color_system in txt or target in txt:
                    _scroll_and_click(driver, opt)
                    return True
            # 색상 매핑 실패 시 'その他' 또는 첫 옵션 선택
            for opt in options:
                txt = opt.text.strip()
                if 'その他' in txt:
                    _scroll_and_click(driver, opt)
                    return True
            _scroll_and_click(driver, options[0])
            return True

        # 옵션이 바로 안 뜨는 경우 키보드 fallback
        active = driver.switch_to.active_element
        for _ in range(25):
            focused = driver.execute_script(
                "var el=document.querySelector('.Select-menu-outer .Select-option.is-focused');"
                "return el?el.textContent.trim():'';"
            )
            if focused and (color_system in focused or color_system.replace('系', '') in focused):
                active.send_keys(Keys.ENTER)
                return True
            active.send_keys(Keys.ARROW_DOWN)
            _sleep(0.05)
        active.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def _split_color_values(color_text: str) -> List[str]:
    """색상 문자열을 구분자로 분리한다."""
    if not color_text:
        return []
    parts = re.split(r'[,/|]|\s+and\s+|\s*&\s*', color_text)
    out = []
    for p in parts:
        v = p.strip()
        if v:
            out.append(v)
    return out


COLOR_ABBR_MAP: Dict[str, str] = {
    "bk": "Black",
    "br": "Brown",
    "dg": "Dark Gray",
    "lg": "Light Gray",
    "cg": "Charcoal Gray",
    "mg": "Melange Gray",
    "gy": "Gray",
    "iv": "Ivory",
    "na": "Navy",
    "nv": "Navy",
    "wh": "White",
    "wt": "White",
    "be": "Beige",
    "kh": "Khaki",
    "ol": "Olive",
    "rd": "Red",
    "pk": "Pink",
    "ye": "Yellow",
    "gr": "Green",
    "bl": "Blue",
    "pu": "Purple",
    "or": "Orange",
}


def _expand_color_abbreviations(color_text: str) -> str:
    """약어 색상코드(bk, cg 등)를 BUYMA 입력용 색상명으로 확장한다."""
    normalized_text = (color_text or "").strip()
    dot_parts = [p.strip() for p in normalized_text.split(".") if p.strip()]
    if len(dot_parts) >= 2 and all(re.fullmatch(r"[A-Za-z]{1,3}", p) for p in dot_parts):
        values = dot_parts
    else:
        values = _split_color_values(normalized_text)
    if not values:
        return color_text

    expanded: List[str] = []
    for raw in values:
        key = re.sub(r'[^a-z0-9]', '', raw.strip().lower())
        mapped = COLOR_ABBR_MAP.get(key)
        value = mapped if mapped else raw.strip()
        if value and value not in expanded:
            expanded.append(value)
    return ", ".join(expanded)


def _try_add_color_row(driver) -> bool:
    """색상 행 추가 버튼을 찾아 클릭한다."""
    try:
        area = driver.find_element(By.CSS_SELECTOR, ".sell-color-table")
        candidates = area.find_elements(By.CSS_SELECTOR, "button, a, [role='button'], [class*='add']")
        for c in candidates:
            txt = (c.text or '').strip()
            cls = (c.get_attribute('class') or '')
            if ('追加' in txt) or ('add' in cls.lower()) or ('plus' in cls.lower()):
                _scroll_and_click(driver, c)
                _sleep(0.4)
                return True
    except Exception:
        return False
    return False


def _try_add_size_row(driver, scope=None) -> bool:
    """사이즈 행 추가 버튼을 찾아 클릭한다."""
    try:
        root = scope or driver
        before = len(root.find_elements(By.CSS_SELECTOR, ".Select"))
        candidates = root.find_elements(
            By.CSS_SELECTOR,
            "button, a, [role='button'], [class*='add'], [class*='plus'], "
            "[aria-label*='追加'], [title*='追加'], [data-testid*='add']"
        )
        for c in candidates:
            txt = (c.text or '').strip()
            cls = (c.get_attribute('class') or '')
            aria = (c.get_attribute('aria-label') or '')
            title = (c.get_attribute('title') or '')
            if (
                ('追加' in txt) or ('add' in cls.lower()) or ('plus' in cls.lower())
                or ('追加' in aria) or ('追加' in title)
            ):
                _scroll_and_click(driver, c)
                _sleep(0.4)


        # 리스트 없는 사이즈버튼 fallback
        icon_buttons = root.find_elements(By.CSS_SELECTOR, "button, [role='button']")
        for b in icon_buttons:
            txt = (b.text or '').strip()
            if txt:
                continue
            cls = (b.get_attribute('class') or '').lower()
            if any(k in cls for k in ['plus', 'add', 'icon']):
                _scroll_and_click(driver, b)
                _sleep(0.4)
                after = len(root.find_elements(By.CSS_SELECTOR, ".Select"))
                if after > before:
                    return True
    except Exception:
        return False
    return False


def _select_size_by_select_controls(driver, scope, size_text: str) -> int:
    """사이즈 라벨 체크박스 대신 React Select 컨트롤에서 사이즈를 선택한다."""
    if not size_text:
        return 0
    try:
        t0 = time.time()
        sizes = [s.strip() for s in size_text.split(',') if s.strip()]
        if not sizes:
            return 0

        # 필요 옵션 개수만큼 Select 추가장 시도
        for _ in range(10):
            if time.time() - t0 > 8:
                break
            current_selects = scope.find_elements(By.CSS_SELECTOR, ".Select")
            if len(current_selects) >= len(sizes):
                break
            if not _try_add_size_row(driver, scope=scope):
                break

        selected = 0
        for idx, sz in enumerate(sizes):
            if time.time() - t0 > 12:
                break
            selects = scope.find_elements(By.CSS_SELECTOR, ".Select")
            if not selects:
                break

            if idx >= len(selects):
                if not _try_add_size_row(driver, scope=scope):
                    break
                selects = scope.find_elements(By.CSS_SELECTOR, ".Select")
                if idx >= len(selects):
                    break

            sel = selects[idx]
            try:
                control = sel.find_element(By.CSS_SELECTOR, ".Select-control")
            except Exception:
                continue

            _scroll_and_click(driver, control)
            _sleep(0.25)

            variants = [v.lower().replace(' ', '') for v in _build_size_variants(sz)]
            options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
            picked = False

            if options:
                for opt in options:
                    txt = (opt.text or '').strip()
                    if any(_size_match(v, txt) for v in variants):
                        _scroll_and_click(driver, opt)
                        selected += 1
                        picked = True
                        _sleep(0.2)
                        break

            if not picked:
                # 쇼핑 파트너 옵션 강제입력(특정 ENTER로 매칭 안될 때)
                try:
                    sel_input = sel.find_element(By.CSS_SELECTOR, "input")
                    sel_input.clear()
                    # cm 표기 변환용 쇼핑 시도 (예: "215" → "21.5")
                    only_num = re.sub(r"[^0-9]", "", sz)
                    type_candidates = [sz]
                    if only_num and 200 <= int(only_num) <= 350:
                        cm_val = int(only_num) / 10.0
                        type_candidates.append(f"{cm_val:.1f}")
                        type_candidates.append(str(int(cm_val)) if cm_val == int(cm_val) else f"{cm_val}")
                    for query in type_candidates:
                        sel_input.clear()
                        sel_input.send_keys(query)
                        _sleep(0.4)
                        filtered = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
                        for opt in filtered:
                            txt = (opt.text or '').strip()
                            if any(_size_match(v, txt) for v in variants):
                                _scroll_and_click(driver, opt)
                                selected += 1
                                picked = True
                                break
                        if picked:
                            break
                    if not picked:
                        sel_input.send_keys(Keys.ESCAPE)
                except Exception:
                    pass

            if not picked:
                # ArrowDown으로 매칭 옵션 탐색 (특정 ENTER)
                try:
                    driver.execute_script("arguments[0].click()", control)
                    _sleep(0.3)
                    active = driver.switch_to.active_element
                    for _ in range(50):
                        if time.time() - t0 > 15:
                            break
                        focused = driver.execute_script(
                            "var el=document.querySelector('.Select-menu-outer .Select-option.is-focused');"
                            "return el?el.textContent.trim():'';"
                        )
                        fnorm = (focused or '').lower().replace(' ', '')
                        if focused and any(_size_match(v, fnorm) for v in variants):
                            active.send_keys(Keys.ENTER)
                            selected += 1
                            picked = True
                            break
                        active.send_keys(Keys.ARROW_DOWN)
                        _sleep(0.05)
                    if not picked:
                        active.send_keys(Keys.ESCAPE)
                except Exception:
                    pass

        return selected
    except Exception:
        return 0


def _fill_size_supplement(driver, size_text: str) -> bool:
    """사이즈 선택 옵션이 없을 때 보충정보 textarea에 사이즈를 기록한다."""
    if not size_text:
        return False
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        areas = variation.find_elements(By.CSS_SELECTOR, "textarea.bmm-c-textarea")
        if not areas:
            return False
        target = areas[0]
        _scroll_and_click(driver, target)
        existing = (target.get_attribute('value') or '').strip()
        line = f"サイズ {size_text}"
        if existing:
            if line not in existing:
                target.clear()
                target.send_keys(existing + "\n" + line)
        else:
            target.clear()
            target.send_keys(line)
        return True
    except Exception:
        return False


def _fill_color_supplement(driver, color_text_en: str) -> bool:
    """색상 입력란이 비활성일 때 보충정보 textarea에 색상명을 기록한다."""
    if not color_text_en:
        return False
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        areas = variation.find_elements(By.CSS_SELECTOR, "textarea.bmm-c-textarea")
        if not areas:
            return False
        target = areas[0]
        _scroll_and_click(driver, target)
        existing = (target.get_attribute('value') or '').strip()
        colors = _split_color_values(color_text_en)
        line = f"COLOR: {', '.join(colors) if colors else color_text_en}"
        if existing:
            if line not in existing:
                target.clear()
                target.send_keys(existing + "\n" + line)
        else:
            target.clear()
            target.send_keys(line)
        return True
    except Exception:
        return False


def _build_size_variants(size_raw: str) -> List[str]:
    """시트 사이즈를 BUYMA 라벨 비교용 후보로 확장한다."""
    sz = (size_raw or '').strip()
    if not sz:
        return []

    variants = [sz]
    szu = sz.upper().replace(' ', '')

    # 복합 표기(예: 220/M3W5, US7/250)도 분해해서 후보로 추가
    parts = [p.strip() for p in re.split(r'[/|]', sz) if p.strip()]
    for p in parts:
        if p not in variants:
            variants.append(p)

    # F/FREE/OS 계열(프리사이즈)
    if szu in {'F', 'FREE', 'FREESIZE', 'OS', 'ONESIZE', 'O/S'}:
        variants.extend([
            'F', 'FREE', 'FREE SIZE', 'ONE SIZE', 'ONESIZE', 'OS', 'O/S',
            'フリー', 'フリーサイズ', 'ワンサイズ', 'サイズ指定なし', '指定なし'
        ])


    # 신발 숫자 표기 확장 (예: 240, 24.0, 24cm, JP24)
    numeric_seeds = []
    for token in [sz] + parts:
        only_num = re.sub(r"[^0-9.]", "", token)
        if not only_num:
            continue
        try:
            if '.' in only_num:
                val = float(only_num)
                # 20~35는 cm로 간주, 200~350은 mm로 간주
                if 20 <= val <= 35:
                    numeric_seeds.append(int(round(val * 10)))
                elif 200 <= val <= 350:
                    numeric_seeds.append(int(round(val)))
            else:
                iv = int(only_num)
                if 200 <= iv <= 350:
                    numeric_seeds.append(iv)
                elif 20 <= iv <= 35:
                    numeric_seeds.append(iv * 10)
        except Exception:
            continue

    for numeric in numeric_seeds:
        cm = numeric / 10.0
        cm_str = f"{cm:.1f}".rstrip('0').rstrip('.')
        variants.extend([
            str(numeric),
            f"{cm:.1f}",
            cm_str,
            f"{cm_str}cm",
            f"{numeric}mm",
            f"JP{cm_str}",
            f"KR{cm_str}",
        ])

    # 중복 제거(순서 유지)
    seen = set()
    out = []
    for v in variants:
        k = v.lower()
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _normalize_size_token_for_match(s: str) -> str:
    """Normalize size tokens for matching."""
    t = (s or '').lower().strip()
    if not t:
        return ''
    t = t.replace('?', ' ')
    t = t.replace('ｃｍ', 'cm').replace('㎝', 'cm').replace('センチ', 'cm')
    t = t.replace('サイズ', '').replace('size', '')
    t = t.replace('cm', '').replace('mm', '')
    t = t.replace('jp', '').replace('kr', '').replace('us', '').replace('uk', '').replace('eu', '').replace('it', '')
    t = re.sub(r"[\s\-_/\(\)\[\]\{\}:;,+]", '', t)
    # 23.5 == 235 형태 비교를 위해 점 제거
    t = t.replace('.', '')
    return t


def _size_match(a: str, b: str) -> bool:
    """사이즈 표기 a와 b가 실질적으로 같은지 판별한다."""
    na = _normalize_size_token_for_match(a)
    nb = _normalize_size_token_for_match(b)
    if not na or not nb:
        return False
    if na == nb:
        return True

    fixed_tokens = {'xxs', 'xs', 's', 'm', 'l', 'xl', 'xxl', 'xxxl'}
    if na in fixed_tokens or nb in fixed_tokens:
        return na == nb

    return (na in nb) or (nb in na)


def _is_free_size_text(size_text: str) -> bool:
    """프리사이즈 계열 표기인지 판별한다. (예: free size, one size, f)"""
    raw = (size_text or '').strip()
    if not raw:
        return False

    tokens = [t.strip() for t in re.split(r'[,/|]+', raw) if t.strip()]
    if not tokens:
        return False

    normalized_tokens = []
    for t in tokens:
        n = t.lower().strip()
        n = n.replace('?', ' ')
        n = re.sub(r'\s+', '', n)
        n = n.replace('-', '').replace('_', '').replace('.', '')
        normalized_tokens.append(n)

    free_aliases = {
        'f', 'free', 'freesize', 'onesize', 'os', 'o/s'.replace('/', ''),
        'none', 'n/a', 'na', 'no', 'nosize', 'nosizes', 'notapplicable',
        '지정없음', '사이즈없음', '없음', '해당없음',
        'サイズ指定なし', '指定なし', 'サイズなし', 'なし',
        '프리', '프리사이즈',
        'フリー', 'フリーサイズ', 'ワンサイズ'
    }

    return all(t in free_aliases for t in normalized_tokens)


def _check_no_variation_option(driver, prefer_shitei_nashi: bool = False) -> bool:
    """사이즈/색상 옵션이 없을 때 '변형없음/지정なし' 계열 옵션을 선택한다."""
    if prefer_shitei_nashi:
        keywords = [
            '指定なし', 'サイズ指定なし', 'サイズなし',
            '変動なし', '変形なし', 'バリエーションなし', 'バリエーション無し', '변형없음'
        ]
    else:
        keywords = [
            '変動なし', '変形なし', 'バリエーションなし', 'バリエーション無し', 'サイズなし',
            'サイズ指定なし', '指定なし', '변형없음'
        ]
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        labels = variation.find_elements(By.CSS_SELECTOR, "label")
        for kw in keywords:
            for lb in labels:
                txt = (lb.text or '').strip()
                if not txt:
                    continue
                if kw in txt:
                    _scroll_and_click(driver, lb)
                    return True

        # 사이즈 기반으로 클릭 가능한 요소를 탐색
        nodes = variation.find_elements(By.XPATH, ".//*[normalize-space(text())!='']")
        for kw in keywords:
            for node in nodes:
                txt = (node.text or '').strip()
                if not txt:
                    continue
                if kw in txt:
                    clicked = driver.execute_script(
                        "var el=arguments[0];"
                        "while(el){"
                        "  if(el.tagName==='LABEL' || el.tagName==='BUTTON' || el.getAttribute('role')==='button' || el.onclick){"
                        "    el.click(); return true;"
                        "  }"
                        "  el=el.parentElement;"
                        "}"
                        "arguments[0].click(); return true;",
                        node
                    )
                    if clicked:
                        return True

        # 라벨 박스가 비어있는 경우 input 이름으로 fallback
        inputs = variation.find_elements(By.CSS_SELECTOR, "input[type='checkbox'], input[type='radio']")
        for ipt in inputs:
            meta = ' '.join([
                ipt.get_attribute('value') or '',
                ipt.get_attribute('name') or '',
                ipt.get_attribute('id') or ''
            ])
            if any(k in meta for k in ['none', 'unspecified', 'no_variation', 'variation_none']):
                if not ipt.is_selected():
                    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
                    return True

        # React Select 모드 선택 fallback
        selects = variation.find_elements(By.CSS_SELECTOR, ".Select")
        targets = ['指定なし', 'サイズ指定なし', 'バリエーションなし', '在庫変動なし'] if prefer_shitei_nashi else ['バリエーションなし', '在庫変動なし', 'サイズ指定なし', '指定なし']
        for sel in selects:
            for target in targets:
                if _select_option_in_select_control(driver, sel, target):
                    return True
    except Exception:
        return False
    return False


def _force_select_shitei_nashi(driver) -> bool:
    """프리사이즈에서 '指定なし' 정확 일치만 선택한다."""
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")

        # 1) 라벨 텍스트 기반 클릭
        labels = variation.find_elements(By.CSS_SELECTOR, "label")
        for lb in labels:
            if _is_shitei_nashi_text(lb.text or ''):
                _scroll_and_click(driver, lb)
                return True

        # 2) 텍스트 노드 기반 클릭
        nodes = variation.find_elements(By.XPATH, ".//*[normalize-space(text())!='']")
        for node in nodes:
            if not _is_shitei_nashi_text(node.text or ''):
                continue
            clicked = driver.execute_script(
                "var el=arguments[0];"
                "while(el){"
                "  if(el.tagName==='LABEL' || el.tagName==='BUTTON' || el.getAttribute('role')==='button' || el.onclick){"
                "    el.click(); return true;"
                "  }"
                "  el=el.parentElement;"
                "}"
                "arguments[0].click(); return true;",
                node
            )
            if clicked:
                return True

        # 3) React Select에서 정확 옵션 선택
        selects = variation.find_elements(By.CSS_SELECTOR, ".Select")
        for sel in selects:
            if _select_option_in_select_control(driver, sel, JP_SHITEI_NASHI):
                return True
            if _select_option_in_select_control(driver, sel, JP_SIZE_SHITEI_NASHI):
                return True
    except Exception:
        return False
    return False


def _force_select_shitei_nashi_global(driver) -> bool:
    """프리사이즈에서 모든 영역에서 '指定なし'를 찾아 선택한다."""
    # 1) 기본 영역 우선
    if _force_select_shitei_nashi(driver):
        return True

    # 2) 사이즈/일본사이즈 Select(일본사이즈 없을 때 선택 시도)
    try:
        selects = driver.find_elements(By.CSS_SELECTOR, ".sell-size-table .Select, .sell-variation .Select")
        for sel in selects:
            if _select_option_in_select_control(driver, sel, JP_SHITEI_NASHI):
                return True
            if _select_option_in_select_control(driver, sel, JP_SIZE_SHITEI_NASHI):
                return True
    except Exception:
        pass

    # 3) 영역 사이즈 정확 일치 클릭 시도
    try:
        nodes = driver.find_elements(By.XPATH, "//*[normalize-space(text())!='']")
        for node in nodes:
            if not _is_shitei_nashi_text(node.text or ''):
                continue
            clicked = driver.execute_script(
                "var el=arguments[0];"
                "while(el){"
                "  if(el.tagName==='LABEL' || el.tagName==='BUTTON' || el.getAttribute('role')==='button' || el.onclick){"
                "    el.click(); return true;"
                "  }"
                "  el=el.parentElement;"
                "}"
                "arguments[0].click(); return true;",
                node
            )
            if clicked:
                return True
    except Exception:
        pass

    return False


def _force_reference_size_shitei_nashi(driver, panel=None) -> bool:
    """사이즈 테이블의 일본사이즈 Select에서 '指定なし' 강제 선택한다."""
    try:
        root = panel if panel is not None else driver
        # BUYMA 화면 구조 변경을 대비해 여러 셀렉터를 시도함
        selects = root.find_elements(By.CSS_SELECTOR, ".sell-size-table .Select")
        if not selects:
            selects = root.find_elements(By.CSS_SELECTOR, ".sell-variation .sell-size-table .Select")
        if not selects:
            return False

        changed = 0
        for sel in selects:
            try:
                # 값 없을 때 skip
                current = sel.find_elements(By.CSS_SELECTOR, ".Select-value-label")
                if current and _is_shitei_nashi_text(current[0].text or ''):
                    changed += 1
                    continue

                # 1? ?반 ?택 ?수
                if _select_option_in_select_control(driver, sel, JP_SHITEI_NASHI):
                    changed += 1
                    continue
                if _select_option_in_select_control(driver, sel, JP_SIZE_SHITEI_NASHI):
                    changed += 1
                    continue

                # 2) 직접 쇼핑/Enter 선택
                try:
                    control = sel.find_element(By.CSS_SELECTOR, ".Select-control")
                    _scroll_and_click(driver, control)
                    _sleep(0.2)
                    inp = sel.find_element(By.CSS_SELECTOR, ".Select-input input")
                    inp.clear()
                    inp.send_keys(JP_SHITEI_NASHI)
                    _sleep(0.35)
                    opts = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
                    exact = None
                    for o in opts:
                        if _is_shitei_nashi_text(o.text or ''):
                            exact = o
                            break
                    if exact is not None:
                        _scroll_and_click(driver, exact)
                        changed += 1
                        continue
                    inp.send_keys(Keys.ENTER)
                    _sleep(0.2)
                    current2 = sel.find_elements(By.CSS_SELECTOR, ".Select-value-label")
                    if current2 and _is_shitei_nashi_text(current2[0].text or ''):
                        changed += 1
                        continue
                except Exception:
                    pass
            except Exception:
                continue
        return changed > 0
    except Exception:
        return False


def _force_select_variation_none_sequence(driver, panel=None) -> bool:
    """요청 순서 강제: サイズ 탭 내 Select(選択してください) -> バリエーションなし 선택."""
    try:
        root = panel if panel is not None else driver
        selects = root.find_elements(By.CSS_SELECTOR, ".sell-variation .Select, .sell-size-table .Select")
        if not selects:
            selects = driver.find_elements(By.CSS_SELECTOR, ".sell-variation .Select, .sell-size-table .Select")
        if not selects:
            return False

        targets = ["バリエーションなし", "バリエーション無し", "指定なし", "サイズ指定なし"]

        # 1) placeholder/value가 "選択してください"인 Select 우선
        prioritized = []
        others = []
        for sel in selects:
            try:
                txt = (sel.text or "").strip()
                if "選択してください" in txt:
                    prioritized.append(sel)
                else:
                    others.append(sel)
            except Exception:
                others.append(sel)

        for sel in prioritized + others:
            for t in targets:
                if _select_option_in_select_control(driver, sel, t):
                    return True
        return False
    except Exception:
        return False


def _enable_size_selection_ui(driver) -> bool:
    """사이즈 선택 UI가 접혀 있을 때 '사이즈 지정' 계열 토글을 클릭해 펼친다."""
    keywords = ['サイズを指定', 'サイズあり', 'サイズを選択', 'サイズを入力', 'バリエーションあり']
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        nodes = variation.find_elements(By.XPATH, ".//*[normalize-space(text())!='']")
        for node in nodes:
            txt = (node.text or '').strip()
            if not txt:
                continue
            if any(k in txt for k in keywords):
                try:
                    _scroll_and_click(driver, node)
                except Exception:
                    driver.execute_script("arguments[0].click();", node)
                _sleep(0.6)
                return True
    except Exception:
        return False
    return False


def _fill_size_text_inputs(driver, size_text: str) -> int:
    """체크박스 없는 경우 사이즈 입력칸에 값을 입력한다."""
    if not size_text:
        return 0
    sizes = [s.strip() for s in size_text.split(',') if s.strip()]
    if not sizes:
        return 0
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, ".sell-variation input.bmm-c-text-field, .sell-variation input[type='text']")
        visible_inputs = [i for i in inputs if i.is_displayed() and i.is_enabled()]
        if not visible_inputs:
            return 0
        count = 0
        for idx, sz in enumerate(sizes):
            target = visible_inputs[min(idx, len(visible_inputs) - 1)]
            _scroll_and_click(driver, target)
            target.clear()
            target.send_keys(sz)
            count += 1
            _sleep(0.15)
        return count
    except Exception:
        return 0


def _select_option_in_select_control(driver, select_el, target_text: str) -> bool:
    """Select target_text in a React Select control with exact match preference."""
    try:
        control = select_el.find_element(By.CSS_SELECTOR, ".Select-control")
        _scroll_and_click(driver, control)
        _sleep(0.2)
        options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")

        def _norm(s: str) -> str:
            t = (s or '').strip().replace('　', ' ').lower()
            t = t.replace('サイズ', '').replace('size', '').replace('cm', '').replace('㎝', '')
            t = re.sub(r'\s+', '', t)
            return t

        def _to_mm(s: str):
            """Normalize numeric size text to mm integer. (21.5 -> 215, 215 -> 215)"""
            t = (s or '').strip().lower()
            if not t:
                return None
            t = t.replace('　', ' ').replace('㎝', 'cm')
            num = re.sub(r"[^0-9.]", "", t)
            if not num:
                return None
            try:
                if '.' in num:
                    val = float(num)
                    if 20 <= val <= 35:
                        return int(round(val * 10))
                    if 200 <= val <= 350:
                        return int(round(val))
                else:
                    iv = int(num)
                    if 200 <= iv <= 350:
                        return iv
                    if 20 <= iv <= 35:
                        return iv * 10
            except Exception:
                return None
            return None

        target_norm = _norm(target_text)
        target_mm = _to_mm(target_text)
        has_range_suffix = ('以上' in (target_text or '')) or ('以下' in (target_text or ''))

        # 1) ?확 매칭 ?선
        for opt in options:
            txt = (opt.text or '').strip()
            if _norm(txt) == target_norm:
                _scroll_and_click(driver, opt)
                _sleep(0.3)
                return True

        # 1-1) 숫자 사이즈는 mm 기준으로 가격 매치
        if target_mm is not None and not has_range_suffix:
            for opt in options:
                txt = (opt.text or '').strip()
                if _to_mm(txt) == target_mm:
                    _scroll_and_click(driver, opt)
                    _sleep(0.3)
                    return True

            # 복잡한 옵션 렌더링하는 경우, 수동입력으로 패턴 시도
            try:
                query_candidates = [str(target_text).strip()]
                # 275 -> 27.5 형태로 변환
                query_from_mm = target_mm / 10.0
                query_candidates.append(f"{query_from_mm:.1f}")
                if abs(query_from_mm - int(query_from_mm)) < 1e-9:
                    query_candidates.append(str(int(query_from_mm)))

                sel_input = select_el.find_element(By.CSS_SELECTOR, ".Select-input input")
                for query in query_candidates:
                    if not query:
                        continue
                    sel_input.clear()
                    sel_input.send_keys(query)
                    _sleep(0.35)
                    filtered = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
                    for opt in filtered:
                        txt = (opt.text or '').strip()
                        if _to_mm(txt) == target_mm:
                            _scroll_and_click(driver, opt)
                            _sleep(0.3)
                            return True
                sel_input.send_keys(Keys.ESCAPE)
            except Exception:
                pass
            return False

        # 2) 일본 사이즈(S/M/L)와 매칭 금지 (S가 XS에 걸리는 문제 방지)
        if target_norm in {'s', 'm', 'l'}:
            return False

        # 3) ?매칭 fallback
        for opt in options:
            txt = (opt.text or '').strip()
            txt_norm = _norm(txt)
            if target_norm and target_norm in txt_norm:
                # S XS?매칭?는 ?탐 방?
                if target_norm == 's' and 'xs' in txt_norm:
                    continue
                _scroll_and_click(driver, opt)
                _sleep(0.3)
                return True
        return False
    except Exception:
        return False


def _infer_reference_jp_size(size_raw: str) -> str:
    """?이?문자?을 ?日?サ?ズ Select ?벨?매핑?다."""
    # 프리사이즈 NONE 계열은 반드시 '指定なし' 고정
    if _is_free_size_text(size_raw):
        return JP_SHITEI_NASHI

    s = (size_raw or '').strip().upper()
    if not s:
        return ''

    # 복합 표기(예: 220/M3W5) 양쪽 사이즈에 적용
    if '/' in s:
        s = s.split('/')[0].strip()

    # 숫자 라벨이 붙은 의류 사이즈(예: 0 (S), 1 (M))는 괄호 안 영문 사이즈를 우선 사용
    paren_alpha = re.search(r"\(([A-Z]{1,4})\)", s)
    if paren_alpha:
        s = paren_alpha.group(1)

    # 일반 영문 의류 사이즈 토큰도 숫자 처리보다 먼저 해석
    alpha_match = re.search(r"(?<![A-Z])(XXXS|XXS|XS|S|M|L|XL|XXL|XXXL)(?![A-Z])", s)
    if alpha_match:
        s = alpha_match.group(1)

    if s in {'XXS', 'XS'}:
        return 'XS以下'
    if s == 'S':
        return 'S'
    if s == 'M':
        return 'M'
    if s == 'L':
        return 'L'
    if s in {'XL', 'XXL', 'XXXL'}:
        return 'XL以上'

    # 숫자 표기 변환 규칙: 215 -> 21.5, 250 -> 25.0, 25 -> 25
    only_num = re.sub(r"[^0-9.]", "", s)
    if only_num:
        try:
            if '.' in only_num:
                fv = float(only_num)
                if 200 <= fv <= 350:
                    cm = fv / 10.0
                elif 20 <= fv <= 35:
                    cm = fv
                else:
                    return s
            else:
                iv = int(only_num)
                if 200 <= iv <= 350:
                    cm = iv / 10.0
                elif 20 <= iv <= 35:
                    cm = float(iv)
                else:
                    return s

            # ?청 반영: 275(mm) ?상? '27cm以上'?로 버킷 처리
            mm_val = int(round(cm * 10))
            if mm_val >= 275:
                return '27cm以上'

            if abs(cm - round(cm)) < 1e-9:
                return str(int(round(cm)))
            return f"{cm:.1f}"
        except Exception:
            return s

    return s


def _fill_size_table_rows(driver, panel, size_text: str) -> int:
    """판매자용 사이즈(sell-size-table)에서 사이즈명을 지정 위치에 입력한다."""
    if not size_text:
        return 0
    try:
        sizes = [s.strip() for s in size_text.split(',') if s.strip()]
        if not sizes:
            return 0

        # 상단 모드 Select를 'バリエーションあり'로 설정
        mode_selects = panel.find_elements(By.CSS_SELECTOR, ".bmm-l-grid-no-bottom .Select")
        if mode_selects:
            _select_option_in_select_control(driver, mode_selects[0], 'バリエーションあり')
            _sleep(0.4)

        table = panel.find_elements(By.CSS_SELECTOR, ".sell-size-table")
        if not table:
            return 0

        # 필요 옵션만 추가 (고정 12개 제한으로 일부 사이즈 누락되는 문제 방지)
        max_add_attempts = max(len(sizes) * 2, 24)
        for _ in range(max_add_attempts):
            rows = panel.find_elements(By.CSS_SELECTOR, ".sell-size-table tbody tr")
            if len(rows) >= len(sizes):
                break
            add_links = panel.find_elements(By.XPATH, ".//div[contains(@class,'bmm-c-form-table__foot')]//a")
            clicked = False
            for a in add_links:
                txt = (a.text or '').strip()
                if '新しいサイズを追加' in txt or 'サイズ' in txt:
                    _scroll_and_click(driver, a)
                    _sleep(0.35)
                    clicked = True
                    break
            if not clicked:
                break

        rows = panel.find_elements(By.CSS_SELECTOR, ".sell-size-table tbody tr")
        filled = 0
        for idx, sz in enumerate(sizes):
            if idx >= len(rows):
                break
            try:
                name_input = rows[idx].find_element(By.CSS_SELECTOR, "td:nth-child(2) input.bmm-c-text-field")
                _scroll_and_click(driver, name_input)
                name_input.clear()
                name_input.send_keys(sz)

                # 다른 영역(일본사이즈)에서 선택
                try:
                    ref_select = rows[idx].find_element(By.CSS_SELECTOR, "td:nth-child(3) .Select")
                    ref_target = _infer_reference_jp_size(sz)
                    if ref_target:
                        _select_option_in_select_control(driver, ref_select, ref_target)
                except Exception:
                    pass

                filled += 1
                _sleep(0.15)
            except Exception:
                continue

        return filled
    except Exception:
        return 0


def _normalize_actual_size_for_upload(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in {"none", "n/a", "na"}:
        return ""
    if text in {"못찾음", "없음", "-"}:
        return ""
    return text


def _extract_actual_measure_map(actual_size_text: str) -> Dict[str, str]:
    if not actual_size_text:
        return {}

    pairs: Dict[str, str] = {}
    normalized = actual_size_text.replace("\n", " ").replace("\r", " ")
    for key, val in re.findall(r"([가-힣A-Za-z ]{1,20})\s*[:：]?\s*(-?\d+(?:\.\d+)?)", normalized):
        k = key.strip()
        v = val.strip()
        if k and v and k not in pairs:
            pairs[k] = v
    return pairs


def _extract_actual_size_rows(actual_size_text: str) -> Dict[str, Dict[str, str]]:
    """'00: 총장 103, 허리단면 35.5 | 01: ...' 형태를 사이즈별 측정 맵으로 파싱."""
    rows: Dict[str, Dict[str, str]] = {}
    text = (actual_size_text or "").strip()
    if not text:
        return rows

    for chunk in [c.strip() for c in text.split("|") if c.strip()]:
        m = re.match(r"^([^:]+)\s*:\s*(.+)$", chunk)
        if not m:
            continue
        size_name = m.group(1).strip()
        body = m.group(2).strip()
        measure_map: Dict[str, str] = {}
        for part in [p.strip() for p in body.split(",") if p.strip()]:
            mm = re.match(r"^(.+?)\s+(-?\d+(?:\.\d+)?)$", part)
            if not mm:
                continue
            measure_map[mm.group(1).strip()] = mm.group(2).strip()
        if measure_map:
            rows[size_name] = measure_map
    return rows


MEASURE_ALIASES: Dict[str, List[str]] = {
    "총장": ["총장", "着丈", "総丈", "全長", "length"],
    "어깨너비": ["어깨너비", "肩幅", "shoulder"],
    "가슴단면": ["가슴단면", "가슴", "身幅", "胸囲", "バスト", "chest"],
    "소매길이": ["소매길이", "袖丈", "裄丈", "sleeve"],
    "허리단면": ["허리단면", "허리", "ウエスト", "胴囲", "waist"],
    "엉덩이단면": ["엉덩이단면", "엉덩이", "ヒップ", "hip"],
    "허벅지단면": ["허벅지단면", "허벅지", "ワタリ", "もも", "thigh"],
    "밑위": ["밑위", "股上", "rise"],
    "밑단단면": ["밑단단면", "밑단", "裾幅", "hem"],
    "발길이": ["발길이", "足長", "アウトソール"],
    "발볼": ["발볼", "足幅", "ワイズ", "幅"],
    "굽높이": ["굽높이", "힐", "ヒール高", "heel"],
}


def _pick_measure_value_by_label(label_text: str, measure_map: Dict[str, str]) -> str:
    if not measure_map:
        return ""
    lt = (label_text or "").strip().lower()
    if not lt:
        return ""

    # direct key hit
    for key, value in measure_map.items():
        if key and key.lower() in lt:
            return value

    # alias hit (KR/JP mixed)
    for base_key, aliases in MEASURE_ALIASES.items():
        if not any(alias.lower() in lt for alias in aliases):
            continue
        if base_key in measure_map:
            return measure_map[base_key]
        # fallback: alias itself present as key in map
        for alias in aliases:
            if alias in measure_map:
                return measure_map[alias]
    return ""


def _fill_size_edit_details(driver, actual_size_text: str) -> int:
    all_rows = _extract_actual_size_rows(actual_size_text)
    fallback_pairs = _extract_actual_measure_map(actual_size_text)
    if not all_rows and not fallback_pairs:
        print("  [actual-size] skip: no parsed measurement rows")
        return 0

    try:
        debug_dir = os.path.join(os.path.dirname(__file__), "_debug")
        try:
            os.makedirs(debug_dir, exist_ok=True)
        except Exception:
            debug_dir = os.path.dirname(__file__)

        def _dump_edit_debug(tag: str) -> None:
            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                html_path = os.path.join(debug_dir, f"edit_debug_{tag}_{ts}.html")
                png_path = os.path.join(debug_dir, f"edit_debug_{tag}_{ts}.png")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(driver.page_source or "")
                try:
                    driver.save_screenshot(png_path)
                except Exception:
                    pass
                print(f"  [actual-size] debug dump saved: {html_path}")
            except Exception:
                pass

        def _pick_best_dialog(dialogs):
            if not dialogs:
                return None
            best = None
            best_score = -1
            for d in dialogs:
                try:
                    txt = (d.text or "").strip()
                    score = 0
                    if any(k in txt for k in ["着丈", "ウエスト", "股上", "ヒップ", "サイズ", "cm"]):
                        score += 5
                    inputs = d.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[type='tel'], textarea")
                    editable = [i for i in inputs if i.get_attribute("disabled") is None]
                    score += len(editable)
                    if score > best_score:
                        best = d
                        best_score = score
                except Exception:
                    continue
            return best or dialogs[-1]

        # size table area only (avoid unrelated 編集 buttons in other sections)
        edit_buttons = driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'sell-size-table')]//*[self::button or self::a][contains(normalize-space(.), '編集')]",
        )
        if not edit_buttons:
            edit_buttons = driver.find_elements(
                By.XPATH,
                "//div[contains(@class,'sell-variation')]//*[self::button or self::a][contains(normalize-space(.), '編集')]",
            )
        print(f"  [actual-size] edit buttons found: total={len(edit_buttons)}")
        filled_count = 0
        main_handle = driver.current_window_handle
        ordered_size_keys = list(all_rows.keys())
        for btn_idx, btn in enumerate(edit_buttons):
            try:
                if not btn.is_displayed():
                    continue

                # try to detect current size row text (e.g. 00/01/02)
                current_size_key = ""
                try:
                    row_node = driver.execute_script(
                        "let e=arguments[0]; while(e && e.tagName!=='TR'){e=e.parentElement;} return e;", btn
                    )
                    row_text = (row_node.text if row_node else "") or ""
                    for sname in all_rows.keys():
                        if sname and sname in row_text:
                            current_size_key = sname
                            break
                except Exception:
                    current_size_key = ""

                if not current_size_key and btn_idx < len(ordered_size_keys):
                    current_size_key = ordered_size_keys[btn_idx]
                selected_pairs = all_rows.get(current_size_key) or (next(iter(all_rows.values())) if all_rows else fallback_pairs)
                print(f"  [actual-size] open edit: size_key='{current_size_key or 'N/A'}' pairs={len(selected_pairs or {})}")
                before_handles = set(driver.window_handles)
                before_modal_count = len(driver.find_elements(By.CSS_SELECTOR, "[role='dialog'], .ReactModal__Content, .bmm-c-modal"))
                before_url = driver.current_url
                _scroll_and_click(driver, btn)
                _sleep(0.25)

                dialog = driver
                popup_handle = None
                for _ in range(10):
                    now_handles = set(driver.window_handles)
                    new_handles = [h for h in now_handles if h not in before_handles]
                    if new_handles:
                        popup_handle = new_handles[0]
                        break
                    _sleep(0.15)
                if popup_handle:
                    driver.switch_to.window(popup_handle)
                    _sleep(0.5)
                    print("  [actual-size] popup window detected")
                    dialog = driver
                else:
                    dialogs = driver.find_elements(By.CSS_SELECTOR, "[role='dialog'], .ReactModal__Content, .bmm-c-modal")
                    dialog = _pick_best_dialog(dialogs) if dialogs else driver
                    # fallback: if nothing opened, force JS click on edit trigger hierarchy
                    if len(dialogs) <= before_modal_count and driver.current_url == before_url:
                        try:
                            js_opened = driver.execute_script(
                                "var el=arguments[0];"
                                "if(!el) return false;"
                                "el.click();"
                                "var p=el.parentElement;"
                                "for(var i=0;i<4 && p;i++){"
                                " if(p.tagName==='BUTTON' || p.tagName==='A' || p.getAttribute('role')==='button'){ p.click(); }"
                                " p=p.parentElement;"
                                "}"
                                "return true;",
                                btn
                            )
                            if js_opened:
                                _sleep(0.35)
                                dialogs = driver.find_elements(By.CSS_SELECTOR, "[role='dialog'], .ReactModal__Content, .bmm-c-modal")
                                dialog = _pick_best_dialog(dialogs) if dialogs else driver
                                print(f"  [actual-size] js-click fallback dialogs: {len(dialogs)}")
                        except Exception:
                            pass
                visible_inputs = []
                for _ in range(10):
                    visible_inputs = [
                        i for i in dialog.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[type='tel'], textarea")
                        if i.get_attribute("disabled") is None
                    ]
                    if visible_inputs:
                        break
                    _sleep(0.2)

                active_frame = None
                if not visible_inputs:
                    # Some edit popups are rendered inside an iframe. Try switching and probing.
                    try:
                        driver.switch_to.default_content()
                        top_frames = driver.find_elements(By.CSS_SELECTOR, "iframe")
                        for fi, frame in enumerate(top_frames):
                            try:
                                driver.switch_to.default_content()
                                driver.switch_to.frame(frame)
                                probe_inputs = [
                                    i for i in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[type='tel'], textarea")
                                    if i.get_attribute("disabled") is None
                                ]
                                if probe_inputs:
                                    visible_inputs = probe_inputs
                                    active_frame = fi
                                    print(f"  [actual-size] iframe inputs detected: frame={fi} count={len(probe_inputs)}")
                                    break
                            except Exception:
                                continue
                        if active_frame is None and popup_handle is None:
                            driver.switch_to.default_content()
                    except Exception:
                        pass
                print(f"  [actual-size] dialog inputs: {len(visible_inputs)}")
                row_scope = driver if active_frame is not None else dialog
                rows = row_scope.find_elements(By.CSS_SELECTOR, "tr, .bmm-c-field, .bmm-c-form-table__table tbody tr")
                local_filled = 0
                used_inputs = set()
                for row in rows:
                    try:
                        label = (row.text or "").strip()
                        if not label:
                            continue
                        picked_value = _pick_measure_value_by_label(label, selected_pairs)
                        inputs = row.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], textarea")
                        if not inputs:
                            continue
                        target = next((i for i in inputs if i.get_attribute("disabled") is None), None)
                        if not target:
                            continue
                        if not picked_value:
                            continue
                        target_id = target.get_attribute("id") or target.get_attribute("name") or str(id(target))
                        if target_id in used_inputs:
                            continue
                        _scroll_and_click(driver, target)
                        target.send_keys(Keys.CONTROL, "a")
                        target.send_keys(Keys.BACKSPACE)
                        target.send_keys(picked_value)
                        used_inputs.add(target_id)
                        local_filled += 1
                    except Exception:
                        continue

                # fallback: no label-matched field found, fill visible inputs in order
                if local_filled == 0 and selected_pairs:
                    try:
                        values_in_order = list(selected_pairs.values())
                        if not visible_inputs:
                            visible_inputs = [
                                i for i in row_scope.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], textarea")
                                if i.get_attribute("disabled") is None
                            ]
                        for idx, inp in enumerate(visible_inputs):
                            if idx >= len(values_in_order):
                                break
                            _scroll_and_click(driver, inp)
                            inp.send_keys(Keys.CONTROL, "a")
                            inp.send_keys(Keys.BACKSPACE)
                            inp.send_keys(values_in_order[idx])
                            local_filled += 1
                    except Exception:
                        pass

                if local_filled > 0:
                    filled_count += local_filled
                    print(f"  [actual-size] filled fields: {local_filled}")
                    save_scope = driver if active_frame is not None else dialog
                    save_buttons = save_scope.find_elements(
                        By.XPATH,
                        ".//button[contains(normalize-space(.), '保存')]"
                        " | .//button[contains(normalize-space(.), '完了')]"
                        " | .//button[contains(normalize-space(.), '決定')]"
                        " | .//button[contains(normalize-space(.), 'OK')]",
                    )
                    print(f"  [actual-size] save buttons: {len(save_buttons)}")
                    if save_buttons:
                        _scroll_and_click(driver, save_buttons[0])
                        _sleep(0.2)
                else:
                    print("  [actual-size] no fields filled in this dialog")
                    _dump_edit_debug(f"nofield_{btn_idx}")

                if active_frame is not None and popup_handle is None:
                    try:
                        driver.switch_to.default_content()
                    except Exception:
                        pass

                if popup_handle:
                    try:
                        driver.close()
                    except Exception:
                        pass
                    try:
                        if main_handle in driver.window_handles:
                            driver.switch_to.window(main_handle)
                    except Exception:
                        pass
            except Exception:
                try:
                    if main_handle in driver.window_handles and driver.current_window_handle != main_handle:
                        driver.switch_to.window(main_handle)
                except Exception:
                    pass
                continue

        if filled_count == 0:
            print("  [actual-size] result: 0 fields filled")
        return filled_count
    except Exception:
        print("  [actual-size] failed: unexpected error")
        return 0


# ---- 카테고리 추론 매핑 ----
FEMALE_KEYWORDS = [
    'women', 'womens', "women's",
    '여성', '여자',
    'レディース',
    'skirt', '치마',
    'dress', '원피스',
    'blouse', '블라우스',
    'heel', '힐',
    'crop', '크롭',
    'mini', '미니'
]

MALE_KEYWORDS = [
    'men', 'mens', "men's",
    '남성', '남자',
    'メンズ'
]

BUYMA_GENDER_CATEGORY_MAP = {
    'F': 'レディースファッション',
    'M': 'メンズファッション',
    'U': 'メンズファッション',
}


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
        print(f"헤더 조회 실패: {e}")
        return {}


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
        print(f"  {row_num}행 {header_name} 업데이트 실패: {e}")
        return False

CATEGORY_KEYWORDS = [
    # ---------------- 신발 ----------------
    (['indoor', '인도어', '인도어화', 'indoorization', 'libre'], None, '靴', 'スニーカー'),
    (['sneaker', '스니커즈', '운동화', 'old skool', '올드스쿨'], None, '靴', 'スニーカー'),
    (['running', '러닝화'], None, '靴', 'ランニングシューズ'),
    (['sandal', '샌들', 'slide', '슬라이드'], None, '靴', 'サンダル'),
    (['boot', '부츠', '워커'], None, '靴', 'ブーツ'),
    (['loafer', '로퍼'], None, '靴', 'ローファー'),

    # ---------------- 상의 ----------------
    (['t-shirt', 'tee', '티셔츠', '반팔'], None, 'トップス', 'Tシャツ・カットソー'),
    (['long sleeve', '긴팔'], None, 'トップス', '長袖Tシャツ'),
    (['hoodie', '후드', '후드티'], None, 'トップス', 'パーカー・フーディ'),
    (['zip-up', '집업'], None, 'トップス', 'ジップパーカー'),
    (['sweatshirt', '맨투맨', 'mtm'], None, 'トップス', 'スウェット'),
    (['shirt', '셔츠'], None, 'トップス', 'シャツ'),
    (['knit', '니트'], None, 'トップス', 'ニット・セーター'),

    # ---------------- 하의 ----------------
    (['jeans', 'denim', '청바지'], None, 'ボトムス', 'デニム・ジーンズ'),
    (['slacks', '슬랙스'], None, 'ボトムス', 'スラックス'),
    (['pants', '팬츠'], None, 'ボトムス', 'パンツ'),
    (['jogger', '조거'], None, 'ボトムス', 'ジョガーパンツ'),
    (['cargo', '카고'], None, 'ボトムス', 'カーゴパンツ'),
    (['shorts', '반바지'], None, 'ボトムス', 'ショーツ'),

    # ---------------- 아우터 ----------------
    (['padding', '패딩', '다운'], None, 'アウター', 'ダウンジャケット'),
    (['coat', '코트'], None, 'アウター', 'コート'),
    (['jacket', '자켓'], None, 'アウター', 'ジャケット'),
    (['blazer', '블레이저'], None, 'アウター', 'テーラードジャケット'),
    (['cardigan', '가디건'], None, 'アウター', 'カーディガン'),
    (['windbreaker', '바람막이'], None, 'アウター', 'ナイロンジャケット'),

    # ---------------- 원피스 ----------------
    (['dress', '원피스'], 'レディースファッション', 'ワンピース', 'ワンピース'),

    # ---------------- 가방 ----------------
    (['backpack', '백팩'], None, 'バッグ', 'バックパック'),
    (['crossbag', '크로스백'], None, 'バッグ', 'ショルダーバッグ'),
    (['tote', '토트'], None, 'バッグ', 'トートバッグ'),

    # ---------------- 악세 ----------------
    (['cap', '모자'], None, 'アクセサリー', '帽子'),
    (['beanie', '비니'], None, 'アクセサリー', 'ニット帽'),
    (['belt', '벨트'], None, 'アクセサリー', 'ベルト'),
    (['socks', '양말'], None, 'アクセサリー', 'ソックス'),
]


def detect_gender_raw(title: str) -> str:
    """상품명 기반으로 성별을 M/F/U 로 분류한다."""
    text = (title or '').lower()

    if any(keyword in text for keyword in FEMALE_KEYWORDS):
        return 'F'

    if any(keyword in text for keyword in MALE_KEYWORDS):
        return 'M'

    return 'U'


def convert_gender_for_buyma(gender: str) -> str:
    """내부 성별 코드를 BUYMA 성별 라벨로 변환한다."""
    if gender == 'F':
        return 'レディース'
    if gender == 'M':
        return 'メンズ'
    return 'メンズ'


def detect_gender(title: str) -> str:
    """상품명 기반 성별을 BUYMA 업로드용 라벨로 변환한다."""
    raw_gender = detect_gender_raw(title)

    # TODO: 추후 AI 분류 연결 가능
    # if raw_gender == 'U':
    #     raw_gender = detect_gender_ai(title)

    return convert_gender_for_buyma(raw_gender)


def _get_buyma_fashion_category_from_gender(title: str) -> str:
    """상품명에서 감지한 성별을 BUYMA 상위 패션 카테고리로 변환한다."""
    raw_gender = detect_gender_raw(title)
    return BUYMA_GENDER_CATEGORY_MAP.get(raw_gender, BUYMA_GENDER_CATEGORY_MAP['U'])


def _infer_buyma_category(product_name_kr: str, product_name_en: str, brand: str = '') -> Tuple[str, str, str]:
    """상품명에서 BUYMA 카테고리 3단계를 추론한다."""
    title = f"{product_name_kr} {product_name_en}".strip()
    text = f"{product_name_kr} {product_name_en} {brand}".lower()
    fashion_category = _get_buyma_fashion_category_from_gender(title)
    if any(token in text for token in ['new balance', '뉴발란스', 'mr530', '530lg', '530sg', '530ka', 'm1906', '1906r', '2002r', '327', '990v', '991', '992', '993']):
        return (fashion_category, '靴', 'スニーカー')
    for keywords, cat1, cat2, cat3 in CATEGORY_KEYWORDS:
        if any(kw.lower() in text for kw in keywords):
            if cat1 is None:
                cat1 = fashion_category
            return (cat1, cat2 or '', cat3 or '')
    return ('', '', '')


def _normalize_sheet_category_labels(cat1: str, cat2: str, cat3: str) -> Tuple[str, str, str]:
    """시트 카테고리(한글/혼용)를 BUYMA 라벨 형태로 보정한다."""
    c1 = (cat1 or '').strip()
    c2 = (cat2 or '').strip()
    c3 = (cat3 or '').strip()

    top_map = {
        '여성': 'レディースファッション',
        '여자': 'レディースファッション',
        '레이디스': 'レディースファッション',
        '레ディース': 'レディースファッション',
        '남성': 'メンズファッション',
        '남자': 'メンズファッション',
        '멘즈': 'メンズファッション',
        'メンズ': 'メンズファッション',
        'レディース': 'レディースファッション',
    }
    mid_map = {
        '상의': 'トップス',
        '하의': 'ボトムス',
        '바지': 'ボトムス',
        '신발': '靴',
        '슈즈': '靴',
        '운동화': '靴',
        '아우터': 'アウター',
        '가방': 'バッグ',
        '악세서리': 'アクセサリー',
        '악세사리': 'アクセサリー',
        '원피스': 'ワンピース',
    }
    sub_map = {
        '데님 팬츠': 'デニム・ジーンズ',
        '데님팬츠': 'デニム・ジーンズ',
        '청바지': 'デニム・ジーンズ',
        '슬랙스': 'スラックス',
        '팬츠': 'パンツ',
        '조거팬츠': 'ジョガーパンツ',
        '카고팬츠': 'カーゴパンツ',
        '반바지': 'ショーツ',
        '스니커즈': 'スニーカー',
        '러닝화': 'ランニングシューズ',
        '샌들': 'サンダル',
        '부츠': 'ブーツ',
        '로퍼': 'ローファー',
        '티셔츠': 'Tシャツ・カットソー',
        '후드': 'パーカー・フーディ',
        '후드티': 'パーカー・フーディ',
        '맨투맨': 'スウェット',
        '셔츠': 'シャツ',
        '니트': 'ニット・セーター',
        '코트': 'コート',
        '자켓': 'ジャケット',
        '블레이저': 'テーラードジャケット',
        '가디건': 'カーディガン',
        '바람막이': 'ナイロンジャケット',
    }

    c1 = top_map.get(c1, c1)
    c2 = mid_map.get(c2, c2)
    c3 = sub_map.get(c3, c3)
    return c1, c2, c3


def _normalize_gender_label_for_sheet(text: str) -> str:
    t = (text or '').strip().lower()
    if not t:
        return ''
    if t in {'여성', '여자', '레ディース', 'レディース', 'w', 'female', 'women', 'womens'}:
        return '여성'
    if t in {'남성', '남자', 'メンズ', 'm', 'male', 'men', 'mens'}:
        return '남성'
    if '여성' in t or 'レディース' in t or 'women' in t or 'female' in t:
        return '여성'
    if '남성' in t or 'メンズ' in t or 'men' in t or 'male' in t:
        return '남성'
    return ''


def _remap_sheet_categories_with_gender(cat1: str, cat2: str, cat3: str) -> Tuple[str, str, str]:
    """시트 카테고리를 대=성별, 중/소=나머지 순으로 재배치한다."""
    values = [(cat1 or '').strip(), (cat2 or '').strip(), (cat3 or '').strip()]
    gender = ''
    rest: List[str] = []
    for v in values:
        if not v:
            continue
        g = _normalize_gender_label_for_sheet(v)
        if g and not gender:
            gender = g
            continue
        if g:
            continue
        rest.append(v)

    if not gender:
        return cat1, cat2, cat3
    new_mid = rest[0] if len(rest) > 0 else ''
    new_small = rest[1] if len(rest) > 1 else ''
    return gender, new_mid, new_small


def _select_category_by_typing(driver, item_index: int, target_label: str) -> bool:
    return buyma_category_mod.select_category_by_typing(
        driver,
        item_index,
        target_label,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


# ArrowDown 대체 수단: 타이핑 방식 fallback으로 사용, 잘 안될 때 대체
_select_category_by_arrow = _select_category_by_typing


def _find_best_option_by_arrow(driver, item_index: int, target_keyword: str,
                               fallback_other: bool = True) -> bool:
    return buyma_category_mod.find_best_option_by_arrow(
        driver,
        item_index,
        target_keyword,
        fallback_other=fallback_other,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


def _dismiss_overlay(driver):
    """?라?버 ?업/?버?이 ?거"""
    return buyma_ui_mod.dismiss_overlay(driver, sleep_fn=_sleep)


def _safe_input(prompt: str) -> str:
    """비대화형 실행에서는 입력 대기 대신 빈 문자열을 반환한다."""
    try:
        return input(prompt)
    except EOFError:
        print("  입력 대기를 건너뜁니다. (비대화형 실행)")
        return ''


def _detect_title_input_issue(name_input, intended_title: str) -> str:
    return buyma_uploader_mod.detect_title_input_issue(name_input, intended_title)


def _normalize_buyma_title_text(text: str) -> str:
    return buyma_mapper_mod.normalize_buyma_title_text(text)


def _truncate_buyma_title_text(text: str, limit: int) -> str:
    return buyma_mapper_mod.truncate_buyma_title_text(text, limit)


def _buyma_char_units(ch: str) -> int:
    return buyma_mapper_mod.buyma_char_units(ch)


def _buyma_title_units(text: str) -> int:
    return buyma_mapper_mod.buyma_title_units(text)


def _slice_buyma_title_by_units(text: str, limit_units: int) -> str:
    return buyma_mapper_mod.slice_buyma_title_by_units(text, limit_units)


def _build_buyma_product_title(brand_en: str, name_en: str, color_en: str, max_length: int = 0) -> str:
    return buyma_mapper_mod.build_buyma_product_title(brand_en, name_en, color_en, max_length)


def _set_text_input_value(driver, input_el, text: str) -> None:
    return buyma_uploader_mod.set_text_input_value(
        driver,
        input_el,
        text,
        scroll_and_click=_scroll_and_click,
    )


def _build_buyma_title_retry_candidates(brand_en: str, name_en: str, color_en: str, max_length: int) -> List[str]:
    return buyma_mapper_mod.build_buyma_title_retry_candidates(brand_en, name_en, color_en, max_length)


# Phase 1 marketplace refactor:
# bind low-risk responsibilities to extracted marketplace modules while preserving
# the existing function names/call sites in this legacy entrypoint.
get_runtime_data_dir = common_get_runtime_data_dir


def get_credentials_path() -> str:
    return common_sheet_source_mod.get_credentials_path(os.path.dirname(__file__))


def get_sheets_service():
    return common_sheet_source_mod.get_sheets_service(get_credentials_path())


def get_sheet_name(service) -> str:
    return common_sheet_source_mod.resolve_sheet_name(service, SPREADSHEET_ID, SHEET_GIDS, SHEET_NAME)


column_index_to_letter = common_sheet_source_mod.column_index_to_letter


def get_sheet_header_map(service, sheet_name: str) -> Dict[str, int]:
    return common_sheet_source_mod.get_sheet_header_map(service, SPREADSHEET_ID, sheet_name, HEADER_ROW)


def update_cell_by_header(
    service,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_name: str,
    value: str,
) -> bool:
    return common_sheet_source_mod.update_cell_by_header(
        service,
        SPREADSHEET_ID,
        sheet_name,
        row_num,
        header_map,
        header_name,
        value,
    )


def read_upload_rows(service, sheet_name: str, specific_row: int = 0) -> List[Dict[str, str]]:
    return common_sheet_source_mod.read_upload_rows(
        service,
        spreadsheet_id=SPREADSHEET_ID,
        sheet_name=sheet_name,
        row_start=ROW_START,
        header_row=HEADER_ROW,
        col_map=COL,
        progress_status_header=PROGRESS_STATUS_HEADER,
        status_completed=STATUS_COMPLETED,
        status_upload_ready=STATUS_UPLOAD_READY,
        status_thumbnails_done=STATUS_THUMBNAILS_DONE,
        specific_row=specific_row,
    )

_infer_color_system = buyma_options_mod.infer_color_system
_split_color_values = buyma_options_mod.split_color_values
_expand_color_abbreviations = buyma_options_mod.expand_color_abbreviations
_build_size_variants = buyma_options_mod.build_size_variants
_normalize_size_token_for_match = buyma_options_mod.normalize_size_token_for_match
_size_match = buyma_options_mod.size_match
_is_free_size_text = buyma_options_mod.is_free_size_text

_normalize_actual_size_for_upload = buyma_validate_mod.normalize_actual_size_for_upload
_extract_actual_measure_map = buyma_validate_mod.extract_actual_measure_map
_extract_actual_size_rows = buyma_validate_mod.extract_actual_size_rows
_pick_measure_value_by_label = buyma_validate_mod.pick_measure_value_by_label

detect_gender_raw = buyma_category_mod.detect_gender_raw
convert_gender_for_buyma = buyma_category_mod.convert_gender_for_buyma
detect_gender = buyma_category_mod.detect_gender
_get_buyma_fashion_category_from_gender = buyma_category_mod.get_buyma_fashion_category_from_gender
_infer_buyma_category = buyma_category_mod.infer_buyma_category
_normalize_sheet_category_labels = buyma_category_mod.normalize_sheet_category_labels
_normalize_gender_label_for_sheet = buyma_category_mod.normalize_gender_label_for_sheet
_remap_sheet_categories_with_gender = buyma_category_mod.remap_sheet_categories_with_gender

_normalize_buyma_title_text = buyma_mapper_mod.normalize_buyma_title_text
_truncate_buyma_title_text = buyma_mapper_mod.truncate_buyma_title_text
_buyma_char_units = buyma_mapper_mod.buyma_char_units
_buyma_title_units = buyma_mapper_mod.buyma_title_units
_slice_buyma_title_by_units = buyma_mapper_mod.slice_buyma_title_by_units
_build_buyma_product_title = buyma_mapper_mod.build_buyma_product_title
_build_buyma_title_retry_candidates = buyma_mapper_mod.build_buyma_title_retry_candidates

resolve_image_files = buyma_images_mod.resolve_image_files
BUYMA_ROW_MAPPER = buyma_mapper_mod.BuymaRowMapper(
    normalize_actual_size_for_upload=_normalize_actual_size_for_upload,
    expand_color_abbreviations=_expand_color_abbreviations,
    split_color_values=_split_color_values,
    resolve_image_files=resolve_image_files,
)


def _save_buyma_credentials(email: str, password: str):
    return buyma_login_mod.save_buyma_credentials(email, password)


def _load_buyma_credentials() -> tuple:
    return buyma_login_mod.load_buyma_credentials()


def _prompt_buyma_credentials() -> tuple:
    return buyma_login_mod.prompt_buyma_credentials()


def setup_visible_chrome_driver():
    return buyma_login_mod.setup_visible_chrome_driver()


def wait_for_buyma_login(driver) -> bool:
    return buyma_login_mod.wait_for_buyma_login(
        driver,
        safe_input_fn=_safe_input,
        scroll_and_click_fn=_scroll_and_click,
        wait_scale=WAIT_SCALE,
    )


def _find_buyma_button_by_keywords(driver, keywords: List[str], timeout: float = 0.0):
    return buyma_submit_mod.find_buyma_button_by_keywords(
        driver,
        keywords,
        timeout=timeout,
        sleep_fn=_sleep,
    )


def _click_buyma_button(driver, button, success_message: str) -> bool:
    return buyma_submit_mod.click_buyma_button(
        driver,
        button,
        success_message,
        click_fallback=_scroll_and_click,
    )


def _submit_buyma_listing(driver, row_num: int) -> bool:
    return buyma_submit_mod.submit_buyma_listing(
        driver,
        row_num,
        click_fallback=_scroll_and_click,
        sleep_fn=_sleep,
    )


def _finalize_buyma_listing(driver, row_num: int) -> bool:
    return buyma_submit_mod.finalize_buyma_listing(
        driver,
        row_num,
        click_fallback=_scroll_and_click,
        sleep_fn=_sleep,
    )


def _handle_success_after_fill(driver, row_num: int, upload_mode: str, interactive: bool = True) -> Tuple[bool, bool]:
    return buyma_submit_mod.handle_success_after_fill(
        driver,
        row_num,
        upload_mode,
        interactive=interactive,
        safe_input_fn=_safe_input,
        sleep_fn=_sleep,
        click_fallback=_scroll_and_click,
    )


def _fill_buyma_form_via_modules(driver, row_data: Dict[str, str]) -> str:
    """Assemble BUYMA form-fill from marketplace modules."""
    return buyma_uploader_mod.fill_buyma_form(
        driver,
        row_data,
        build_buyma_form_payload=BUYMA_ROW_MAPPER.map_row,
        build_buyma_category_plan=buyma_category_mod.build_buyma_category_plan,
        apply_buyma_category_selection=buyma_category_mod.apply_buyma_category_selection,
        apply_buyma_option_selection=buyma_options_mod.apply_buyma_option_selection,
        apply_buyma_post_option_fields=buyma_uploader_mod.apply_buyma_post_option_fields,
        upload_product_images=buyma_images_mod.upload_product_images,
        normalize_actual_size_for_upload=_normalize_actual_size_for_upload,
        expand_color_abbreviations=_expand_color_abbreviations,
        split_color_values=_split_color_values,
        resolve_image_files=resolve_image_files,
        category_corrector=correct_buyma_category,
        select_category_by_arrow=_select_category_by_arrow,
        find_best_option_by_arrow=_find_best_option_by_arrow,
        buyma_sell_url=BUYMA_SELL_URL,
        dismiss_overlay=_dismiss_overlay,
        sleep_fn=_sleep,
        comment_template=BUYMA_COMMENT_TEMPLATE,
        scroll_and_click=_scroll_and_click,
        set_text_input_value=_set_text_input_value,
        detect_title_input_issue=_detect_title_input_issue,
        build_buyma_title_retry_candidates=_build_buyma_title_retry_candidates,
        select_color_system=_select_color_system,
        try_add_color_row=_try_add_color_row,
        fill_color_supplement=_fill_color_supplement,
        select_size_by_select_controls=_select_size_by_select_controls,
        fill_size_table_rows=_fill_size_table_rows,
        force_select_variation_none_sequence=_force_select_variation_none_sequence,
        force_select_shitei_nashi_global=_force_select_shitei_nashi_global,
        check_no_variation_option=_check_no_variation_option,
        force_reference_size_shitei_nashi=_force_reference_size_shitei_nashi,
        fill_size_edit_details=_fill_size_edit_details,
        enable_size_selection_ui=_enable_size_selection_ui,
        fill_size_text_inputs=_fill_size_text_inputs,
        fill_size_supplement=_fill_size_supplement,
    )


def _upload_buyma_rows_via_modules(
    specific_row: int = 0,
    upload_mode: str = 'auto',
    max_items: int = 0,
    interactive: bool = True,
):
    """Assemble BUYMA upload loop from marketplace modules."""
    return buyma_uploader_mod.upload_products(
        specific_row=specific_row,
        upload_mode=upload_mode,
        max_items=max_items,
        interactive=interactive,
        get_sheets_service=get_sheets_service,
        get_sheet_name=get_sheet_name,
        get_sheet_header_map=get_sheet_header_map,
        read_upload_rows=read_upload_rows,
        setup_visible_chrome_driver=setup_visible_chrome_driver,
        wait_for_buyma_login=wait_for_buyma_login,
        update_cell_by_header=update_cell_by_header,
        fill_buyma_form=fill_buyma_form,
        handle_success_after_fill=_handle_success_after_fill,
        safe_input=_safe_input,
        progress_status_header=PROGRESS_STATUS_HEADER,
        status_uploading=STATUS_UPLOADING,
        status_completed=STATUS_COMPLETED,
    )


BUYMA_UPLOADER = buyma_uploader_mod.BuymaUploaderAdapter(
    fill_form_fn=_fill_buyma_form_via_modules,
    upload_rows_fn=_upload_buyma_rows_via_modules,
)


def fill_buyma_form(driver, row_data: Dict[str, str]) -> str:
    """바이마 출품 시 상품 정보를 자동 입력한다.
    바이마는 React 기반 bmm-c-* 컴포넌트를 사용하며 name/id 속성이 없음."""
    return BUYMA_UPLOADER.fill_form(driver, row_data)


def upload_products(specific_row: int = 0, upload_mode: str = 'auto', max_items: int = 0, interactive: bool = True):
    """메인 업로드 루프: 시트 읽기 → 로그 → 각 행별 입력 자동화 엔트리"""
    return BUYMA_UPLOADER.upload_rows(
        specific_row=specific_row,
        upload_mode=upload_mode,
        max_items=max_items,
        interactive=interactive,
    )


def main():
    parser = argparse.ArgumentParser(description="바이마 출품 자동화")
    parser.add_argument("--scan", action="store_true", help="출품 페이지 폼 구조 스캔 (개발용)")
    parser.add_argument("--row", type=int, default=0, help="특정 행만 출품 (예: --row 3)")
    parser.add_argument(
        "--mode",
        choices=["review", "auto"],
        default="auto",
        help="review=사람 확인 후 제출, auto=오류 없으면 자동 제출",
    )
    parser.add_argument("--watch", action="store_true", help="업로드 워커 감시 모드")
    parser.add_argument("--interval", type=int, default=20, help="감시 간격(초)")
    args = parser.parse_args()

    if args.scan:
        driver = setup_visible_chrome_driver()
        try:
            if not wait_for_buyma_login(driver):
                return
            scan_form_structure(driver)
        finally:
            _safe_input("\nEnter를 눌러 브라우저를 닫습니다...")
            driver.quit()
    else:
        if args.watch:
            interval = max(5, int(args.interval))
            print(f"업로드 워커 감시 시작: {interval}초 간격")
            watch_row = 0
            if args.row:
                print(f"감시 모드에서는 --row({args.row})를 고정하지 않고 전체 대기 행을 순차 처리합니다.")
            while True:
                upload_products(specific_row=watch_row, upload_mode=args.mode, max_items=1, interactive=False)
                print(f"다음 업로드 점검까지 {interval}초 대기...")
                time.sleep(interval)
        else:
            upload_products(specific_row=args.row, upload_mode=args.mode, interactive=True)


if __name__ == "__main__":
    main()
