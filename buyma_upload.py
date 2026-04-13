"""
BUYMA 異쒗뭹 ?먮룞??紐⑤뱢.

Google Sheets???곹뭹 ?뺣낫瑜?BUYMA 異쒗뭹 ?섏씠吏???먮룞 ?낅젰?쒕떎.

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
import tempfile

# Windows cp949 ?섍꼍?먯꽌 ?좊땲肄붾뱶 異쒕젰 ?ㅻ쪟 諛⑹?
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") in ("cp949", "euckr"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

# ?꾩껜 ?湲곗떆媛??ㅼ??쇰쭅: ?섍꼍蹂??AUTO_SHOP_WAIT_SCALE (湲곕낯 0.6)
_RAW_SLEEP = time.sleep
try:
    WAIT_SCALE = float(os.environ.get('AUTO_SHOP_WAIT_SCALE', '0.6'))
except Exception:
    WAIT_SCALE = 0.6
if WAIT_SCALE <= 0:
    WAIT_SCALE = 0.1


def _sleep(seconds: float) -> None:
    _RAW_SLEEP(max(0.0, seconds * WAIT_SCALE))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# main.py? ?숈씪???쒗듃 ?뺣낫
SPREADSHEET_ID = "1mTV-Fcybov-0uC7tNyM_GXGDoth8F_7wM__zaC1fAjs"
SHEET_GIDS = [1698424449]
SHEET_NAME = "?쒗듃1"
ROW_START = 2
HEADER_ROW = 1
PROGRESS_STATUS_HEADER = "진행상태"
STATUS_UPLOAD_READY = "썸네일완료"
STATUS_THUMBNAILS_DONE = "썸네일완료"
STATUS_UPLOADING = "업로드중"
STATUS_COMPLETED = "출품완료"


def _load_sheet_runtime_config() -> None:
    """濡쒖뺄?먯꽌 ??ν븳 ?쒗듃 ?ㅼ젙?뚯씪???쎌뼱 湲곕낯媛믪쓣 諛섏쁺?쒕떎."""
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
        # URL ?꾩껜 ?꾨떖??寃쎌슦?먮룄 /d/<id>/?먯꽌 ID留?異붿텧
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
        print(f"?쒗듃 ?ㅼ젙 濡쒕뱶 ?ㅽ뙣: {e}")


_load_sheet_runtime_config()

BUYMA_SELL_URL = "https://www.buyma.com/my/sell/new?tab=b"
BUYMA_LOGIN_URL = "https://www.buyma.com/login/"

# 諛붿씠留?濡쒓렇???뺣낫 ??κ꼍濡?(濡쒖뺄)
BUYMA_CRED_PATH = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
    'auto_shop', 'buyma_credentials.json'
)
# Chrome ?꾨줈??寃쎈줈 (?몄뀡/荑좏궎 ?좎?)
CHROME_PROFILE_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
    'auto_shop', 'chrome_profile'
)


BUYMA_COMMENT_TEMPLATE = """
?ャ깇?담꺁, ?뺛궊?잆꺁?쇈깪?쇈궦, 誤ゅ춴?ゃ꺍??
?썽슋堊울펷OCS竊됵폏?녶뱚繹뽩굺2-5?ο펻?븅곻퐵?곁?7-9??
亮녑만?귙겘若됧츣?㎯걲?뚣곭퉩恙숁쐿?사빊躍멩셽??댆??γ걣?띶풄?쇻굥?닷릦?귙걫?뽧걚?얇걲?귟㈂?쀣걦??걡?뤵걚?덀굩?쎼걦?졼걬?꾠?
壤볟틭?㏛툏訝訝띹돬?삡툖?룟릦?뚣걗?뗥졃?덀겘雅ㅶ룢野얍퓶?쀣겍?듽굤?얇걲?귛퐪?녺뵳?㎯걡?귡뼋?귙걦?닷릦??꺗佯╉걫?긷몜?뺛걵?╉걚?잆걽?띲겲?쇻?

?딂뜼?⑵옙瓮←빁?룔걗?듽겓??쇇?곥걮?얇걲??겎?곲쉹?귡뀓?곭듁力곥굮?붺▶沃띲걚?잆걽?묆겲?쇻?
?잍뿥曄앫겘鴉묈떃?곦폂?롢걨?ラ젂轝▼?恙쒌걮?얇걲??

役룟쨼獒썲뱚?츼ADE IN JAPAN??＝?곥겏驪붵겧??떏亮꿱쫳?ｃ굤?쇻굥?닷릦?뚣걫?뽧걚?얇걲??
瓦붷뱚?삡벡?쎼겓?귙걼?ｃ겍訝띶끁?덃죭餓뜰겓?㏂걮?╉겘?듿룚凉뺛겇?꾠겍?믡걫閻븃첀?뤵걽?뺛걚??

壤볟틭?㎯겘?녔뿥若뚦２?곥굜?ζ쑍?ゅ뀯?룔궋?ㅳ깇?졼곲솏若싧뱚?ゃ겑
?▲꺍?뷩곥꺃?뉎궍?쇈궧?곥궘?껁궨?곥궥?γ꺖?븝펷?밤깑?쇈궖?쇘춬竊됥굜烏ｉ줊?믡깳?ㅳ꺍?ュ룚?딀돮?ｃ겍?듽굤?얇걲??
?먦걫力ⓩ꼷雅뗩쟿??
?삥돈鸚뽬＝?곥겘?ζ쑍獒썲뱚?ⓩ캈?밤겍濾쒎뱚?뷸틬?뚥퐥?꾢졃?덀걣?붵걭?꾠겲?쇻?
?사릊獒썬겗?섅걬?곭릊?꾤탞?뤵굤?ⓨ늽??낯?뚧츐?ｃ겍?꾠굥?닷릦?뚣걫?뽧걚?얇걲??
?사뵟?겹겗?졼꺀?곥깤?ゃ꺍?덀겗?뷩꺃?곮떏亮꿔겗?룔깱?곮＝?좈걥葉뗣겎??컦?뺛겒?루춬?뚣걗?뗥졃?덀걣?붵걭?꾠겲?쇻?
?삭＝?곥겗?듐궎?뷸릍若싨뼶力뺛겓?덀겂?╉겘??節?cm葉뗥벧??い藥?걣?잆걯?뗥졃?덀걣?붵걭?꾠겲?쇻?
?삭퓭?곥꺕雅ㅶ룢?ラ뼟?쇻굥誤뤷츣?츭UYMA誤뤷츣?ユ틬?섅겲?쇻귙걡若€쭣?썲릦?ャ굠?뗨퓭?곥겘?듿룛?묆겎?띲걢??겲?쇻겗?㎯곥걫蘊쇔뀯??뀕?띲겓?딃줁?꾠걚?잆걮?얇걲??
?삡툖??뱚?삭い?띺곥겘雅ㅶ룢?얇걼??퓭?곥걣??꺗?㎯걲??
""".strip()

# ?쒗듃 而щ읆 ?몃뜳??A=0, B=1, ..., M=12)
COL = {
    'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5,
    'G': 6, 'H': 7, 'I': 8, 'J': 9, 'K': 10, 'L': 11,
    'M': 12, 'N': 13, 'O': 14,
    'W': 22, 'X': 23, 'Y': 24,
}


def get_credentials_path() -> str:
    """?먭꺽利앸챸 ?뚯씪 寃쎈줈 諛섑솚"""
    local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
    if local_app_data:
        cred = os.path.join(local_app_data, 'auto_shop', 'credentials.json')
        if os.path.exists(cred):
            return cred
    fallback = os.path.join(os.path.dirname(__file__), 'credentials.json')
    if os.path.exists(fallback):
        return fallback
    raise FileNotFoundError("credentials.json ?뚯씪??李얠쓣 ???놁뒿?덈떎")


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
        print(f"?쒗듃 ?쎄린 ?ㅽ뙣: {e}")
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

        # 理쒖냼 議곌굔: URL + ?곹뭹紐?+ 諛붿씠留??먮ℓ媛 ?덉뼱??異쒗뭹 ???
        url = cell('B')
        product_name = cell('E')
        buyma_price = cell('M')

        if not url or not product_name or not buyma_price:
            continue

        progress_status = cell_by_index(status_index)
        normalized_status = (progress_status or "").strip()
        if normalized_status == STATUS_COMPLETED:
            print(f"  {idx}??嫄대꼫? (吏꾪뻾?곹깭: {progress_status})")
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
            'musinsa_category_large': cell('W'),
            'musinsa_category_middle': cell('X'),
            'musinsa_category_small': cell('Y'),
            'progress_status': progress_status,
        })


    return rows_data


def _save_buyma_credentials(email: str, password: str):
    """諛붿씠留?濡쒓렇???뺣낫瑜?濡쒖뺄????ν븳??""
    os.makedirs(os.path.dirname(BUYMA_CRED_PATH), exist_ok=True)
    import base64
    data = {
        'email': base64.b64encode(email.encode()).decode(),
        'password': base64.b64encode(password.encode()).decode(),
    }
    with open(BUYMA_CRED_PATH, 'w') as f:
        json.dump(data, f)
    print("  濡쒓렇???뺣낫媛 ??λ릺?덉뒿?덈떎.")


def _load_buyma_credentials() -> tuple:
    """??λ맂 諛붿씠留?濡쒓렇???뺣낫媛 ?놁쑝硫?(None, None) 諛섑솚"""
    if not os.path.exists(BUYMA_CRED_PATH):
        return None, None
    try:
        import base64
        with open(BUYMA_CRED_PATH, 'r') as f:
            data = json.load(f)
        email = base64.b64decode(data['email']).decode()
        password = base64.b64decode(data['password']).decode()
        return email, password
    except Exception:
        return None, None


def _prompt_buyma_credentials() -> tuple:
    """?ъ슜?먯뿉寃?諛붿씠留?濡쒓렇???뺣낫瑜??낅젰諛쏄퀬 ??ν븳??""
    print("\n諛붿씠留?濡쒓렇???뺣낫瑜??낅젰?댁＜?몄슂 (理쒖큹 1?뚮쭔):")
    email = input("  ?대찓?? ").strip()
    password = input("  鍮꾨?踰덊샇: ").strip()
    if email and password:
        _save_buyma_credentials(email, password)
    return email, password


def setup_visible_chrome_driver():
    """Create visible Chrome driver for BUYMA upload automation."""
    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
    def _build_options(user_data_dir: str) -> ChromeOptions:
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1400,900")
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        # ?먮룞 ?먯? 諛⑹? ?듭뀡
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        return chrome_options

    chrome_options = _build_options(CHROME_PROFILE_DIR)

    driver_path = None
    cached_candidates = sorted(
        glob.glob(
            os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver", "**", "chromedriver.exe"),
            recursive=True,
        )
    )
    if cached_candidates:
        driver_path = cached_candidates[-1]

    try:
        service = Service(driver_path or ChromeDriverManager().install())
    except PermissionError:
        if not driver_path:
            raise
        service = Service(driver_path)

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except SessionNotCreatedException as e:
        if 'failed to write prefs file' not in str(e).lower():
            raise
        fallback_profile = tempfile.mkdtemp(prefix='buyma_profile_', dir=os.path.dirname(CHROME_PROFILE_DIR))
        print(f"Chrome 湲곕낯 ?꾨줈?꾩씠 ?좉꺼 ?덉뼱 ?꾩떆 ?꾨줈?꾨줈 ?ъ떆?꾪빀?덈떎: {fallback_profile}")
        driver = webdriver.Chrome(service=service, options=_build_options(fallback_profile))

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

def wait_for_buyma_login(driver) -> bool:
    """Handle BUYMA login flow with saved credentials and manual fallback."""
    driver.get(BUYMA_SELL_URL)
    _sleep(3)

    # ?대? 濡쒓렇???곹깭硫??듦낵
    if '/login' not in driver.current_url:
        print("?대? 濡쒓렇???곹깭?낅땲??")
        return True

    # ??λ맂 怨꾩젙 ?뺣낫 濡쒕뱶 (?놁쑝硫??낅젰 諛쏄린)
    email, password = _load_buyma_credentials()
    if not email or not password:
        email, password = _prompt_buyma_credentials()

    if email and password:
        # ?먮룞 濡쒓렇???쒕룄
        print("?먮룞 濡쒓렇???쒕룄 以?..")
        try:
            driver.get(BUYMA_LOGIN_URL)
            _sleep(2)

            # ?대찓???낅젰
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "input[name='txtLoginId'], input[type='email'], "
                    "input[name='email'], input[id*='login'], input[id*='email']"
                ))
            )


            email_input.clear()

            # 鍮꾨?踰덊샇 ?낅젰
            pw_input = driver.find_element(By.CSS_SELECTOR,
                "input[name='txtLoginPass'], input[type='password'], "
                "input[name='password']"
            )
            pw_input.clear()
            pw_input.send_keys(password)

            # 濡쒓렇??踰꾪듉 ?대┃
            login_btn = driver.find_element(By.CSS_SELECTOR,
                "input[type='submit'][value*='?뷴뱚'], "
                "button[type='submit'], input[type='submit'], "
                ".login-btn, button[class*='login']"
            )
            login_btn.click()
            _sleep(5)

            # 濡쒓렇???깃났 ?뺤씤
            if '/login' not in driver.current_url:
                print("???먮룞 濡쒓렇???깃났!")
                driver.get(BUYMA_SELL_URL)
                _sleep(2)
                return True
            else:
                print("???먮룞 濡쒓렇???ㅽ뙣 (鍮꾨?踰덊샇 ?ㅻ쪟 ?먮뒗 罹≪감 ?꾩슂)")
                print("  ??λ맂 濡쒓렇???뺣낫媛 ?由щ㈃ ?ㅼ쓬???ㅼ떆 ?낅젰?댁＜?몄슂.")
                try:
                    os.remove(BUYMA_CRED_PATH)
                except Exception:
                    pass
        except Exception as e:
            print(f"???먮룞 濡쒓렇???ㅻ쪟: {e}")

    # ?섎룞 濡쒓렇???덈궡
    print("\n" + "=" * 60)
    print("  諛붿씠留?濡쒓렇?몄씠 ?꾩슂?⑸땲??")
    print("  釉뚮씪?곗??먯꽌 吏곸젒 濡쒓렇???댁＜?몄슂.")
    print("  濡쒓렇???꾨즺 媛먯??섎㈃ ?먮룞?쇰줈 吏꾪뻾?⑸땲??")
    print("=" * 60 + "\n")

    for _ in range(300):
        _sleep(1)
        try:
            current_url = driver.current_url
            if '/login' not in current_url:
                print("濡쒓렇???깃났! 異쒗뭹 ?섏씠吏濡??대룞?⑸땲??.")
                # ?먮룞 濡쒓렇???깃났 ??怨꾩젙 ?뺣낫 ????щ? 臾산린
                save = input("  ??怨꾩젙 ?뺣낫瑜???ν븯寃좎뒿?덇퉴? (y/n): ").strip().lower()
                if save == 'y':
                    new_email = input("  ?대찓?? ").strip()
                    new_pw = input("  鍮꾨?踰덊샇: ").strip()
                    if new_email and new_pw:
                        _save_buyma_credentials(new_email, new_pw)
                _sleep(2)
                return True
        except Exception:
            pass

    print("濡쒓렇???湲곗떆媛?珥덇낵 (5遺?")
    return False


def scan_form_structure(driver):
    """Scan and print BUYMA form structure (debug)."""
    driver.get(BUYMA_SELL_URL)
    _sleep(5)

    print("\n=== 諛붿씠留?異쒗뭹 ??援ъ“ ?ㅼ틪 ===\n")

    # input ???
    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[type='file']")
    print(f"[INPUT ?낅젰] ({len(inputs)}媛?")
    for inp in inputs:
        name = inp.get_attribute('name') or ''
        id_attr = inp.get_attribute('id') or ''
        placeholder = inp.get_attribute('placeholder') or ''
        input_type = inp.get_attribute('type') or ''
        print(f"  name={name}, id={id_attr}, type={input_type}, placeholder={placeholder}")

    # textarea
    textareas = driver.find_elements(By.TAG_NAME, "textarea")
    print(f"\n[TEXTAREA] ({len(textareas)}媛?")
    for ta in textareas:
        name = ta.get_attribute('name') or ''
        id_attr = ta.get_attribute('id') or ''
        print(f"  name={name}, id={id_attr}")

    # select
    selects = driver.find_elements(By.TAG_NAME, "select")
    print(f"\n[SELECT] ({len(selects)}媛?")
    for sel in selects:
        name = sel.get_attribute('name') or ''
        id_attr = sel.get_attribute('id') or ''
        options = sel.find_elements(By.TAG_NAME, "option")
        opt_texts = [o.text.strip() for o in options[:10]]
        print(f"  name={name}, id={id_attr}, options(~10): {opt_texts}")

    # button/submit
    buttons = driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
    print(f"\n[BUTTON] ({len(buttons)}媛?")
    for btn in buttons:
        text = btn.text.strip() or btn.get_attribute('value') or ''
        btn_type = btn.get_attribute('type') or ''
        btn_class = btn.get_attribute('class') or ''
        print(f"  text={text}, type={btn_type}, class={btn_class[:60]}")

    # ?꾩떆 HTML ????붾쾭洹몄슜)
    html_path = os.path.join(os.path.dirname(__file__), '_buyma_form_scan.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(driver.page_source)
    print(f"\n??HTML ??? {html_path}")


def resolve_image_files(image_paths_cell: str) -> List[str]:
    """Resolve image file list from sheet cell path string."""
    if not image_paths_cell:
        return []

    # ?대?吏媛 ??λ맂 湲곕낯 寃쎈줈
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
            # ?쒗듃??images/媛 ??踰??ㅼ뼱媛硫?猷⑦듃 以묐났 諛⑹?
            norm_path = norm_path[len('images/'):]

        # ?곷?寃쎈줈??images_root 湲곗? 寃쎈줈
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
                # ?대뜑?쇰㈃ ?섏쐞 ?대?吏 紐⑤몢
                for ext in ('*.jpg', '*.jpeg', '*.png', '*.webp'):
                    files.extend(sorted(glob.glob(os.path.join(full_path, ext))))
                candidate_dirs.append(os.path.abspath(full_path))
                break

    # ?곗꽑 ?몃꽕?쇱씠 ?대뜑???덉쑝硫?泥ル쾲吏몃줈 ?щ┝
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
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", element)
    driver.execute_script("window.scrollBy(0, -120);")
    _sleep(0.3)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def _infer_color_system(color_text: str) -> str:
    """Map color text to BUYMA color system labels."""
    c = (color_text or '').strip().lower()
    if not c or c == 'none':
        return '?꿩뙁若싥겒??
    if any(k in c for k in ['black', '釉붾옓', '寃??]):
        return '?뽧꺀?껁궚楹?
    if any(k in c for k in ['white', 'ivory', '?ㅽ봽?붿씠??, '?꾩씠蹂대━', '??]):
        return '?쎼꺈?ㅳ깉楹?
    if any(k in c for k in ['gray', 'grey', '洹몃젅??, '?뚯깋']):
        return '?겹꺃?쇘내'
    if any(k in c for k in ['beige', 'camel', '踰좎씠吏', '移대찞']):
        return '?쇻꺖?멥깷楹?
    if any(k in c for k in ['brown', '釉뚮씪??, '媛덉깋']):
        return '?뽧꺀?╉꺍楹?
    if any(k in c for k in ['pink', '?묓겕']):
        return '?붵꺍??내'
    if any(k in c for k in ['red', '?덈뱶', '鍮④컯']):
        return '?с긿?됬내'
    if any(k in c for k in ['orange', '?ㅻ젋吏']):
        return '?ゃ꺃?녈궦楹?
    if any(k in c for k in ['yellow', '?먮줈??, '?몃옉']):
        return '?ㅳ궓??꺖楹?
    if any(k in c for k in ['green', 'khaki', 'olive', '洹몃┛', '移댄궎', '?щ━釉?]):
        return '?겹꺁?쇈꺍楹?
    if any(k in c for k in ['blue', 'navy', '釉붾（', '?ㅼ씠鍮?]):
        return '?뽧꺂?쇘내'
    if any(k in c for k in ['purple', 'violet', '?쇳뵆', '蹂대씪']):
        return '?묆꺖?쀣꺂楹?
    if any(k in c for k in ['gold', '?ㅻ쾭', 'silver', 'metal', '硫뷀깉']):
        return '?룔꺂?먦꺖?삠궡?쇈꺂?됬내'
    return '?욁꺂?곥궖?⒲꺖'


def _select_color_system(driver, color_system: str, row_index: int = 0) -> bool:
    """?됱긽怨꾪넻 Select?먯꽌 而щ윭??留욌뒗 ?듭뀡???좏깮?쒕떎."""
    try:
        color_selects = driver.find_elements(By.CSS_SELECTOR, ".sell-color-table .Select")
        if not color_selects:
            return False
        color_select = color_selects[min(row_index, len(color_selects) - 1)]
        control = color_select.find_element(By.CSS_SELECTOR, ".Select-control")
        _scroll_and_click(driver, control)
        _sleep(0.4)

        # ?쒕∼?ㅼ슫 ?듭뀡?먯꽌 紐⑺몴 ?됱긽 ?곗꽑 ?좏깮
        options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
        if options:
            target = color_system.replace('楹?, '')
            for opt in options:
                txt = opt.text.strip()
                if color_system in txt or target in txt:
                    _scroll_and_click(driver, opt)
                    return True
            # ?됱긽 留ㅽ븨 ?ㅽ뙣 ??'?앫겗餓? ?먮뒗 泥??듭뀡 ?좏깮
            for opt in options:
                txt = opt.text.strip()
                if '?앫겗餓? in txt:
                    _scroll_and_click(driver, opt)
                    return True
            _scroll_and_click(driver, options[0])
            return True

        # ?듭뀡??諛붾줈 ???⑤뒗 寃쎌슦 ?ㅻ낫??fallback
        active = driver.switch_to.active_element
        for _ in range(25):
            focused = driver.execute_script(
                "var el=document.querySelector('.Select-menu-outer .Select-option.is-focused');"
                "return el?el.textContent.trim():'';"
            )
            if focused and (color_system in focused or color_system.replace('楹?, '') in focused):
                active.send_keys(Keys.ENTER)
                return True
            active.send_keys(Keys.ARROW_DOWN)
            _sleep(0.05)
        active.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def _split_color_values(color_text: str) -> List[str]:
    """?됱긽 臾몄옄?댁쓣 援щ텇?먮줈 遺꾨━?쒕떎."""
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
    """?쎌뼱 ?됱긽肄붾뱶(bk, cg ??瑜?BUYMA ?낅젰???됱긽紐낆쑝濡??뺤옣?쒕떎."""
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
    """?됱긽 ??異붽? 踰꾪듉??李얠븘 ?대┃?쒕떎."""
    try:
        area = driver.find_element(By.CSS_SELECTOR, ".sell-color-table")
        candidates = area.find_elements(By.CSS_SELECTOR, "button, a, [role='button'], [class*='add']")
        for c in candidates:
            txt = (c.text or '').strip()
            cls = (c.get_attribute('class') or '')
            if ('瓦썲뒥' in txt) or ('add' in cls.lower()) or ('plus' in cls.lower()):
                _scroll_and_click(driver, c)
                _sleep(0.4)
                return True
    except Exception:
        return False
    return False


def _try_add_size_row(driver, scope=None) -> bool:
    """?ъ씠利???異붽? 踰꾪듉??李얠븘 ?대┃?쒕떎."""
    try:
        root = scope or driver
        before = len(root.find_elements(By.CSS_SELECTOR, ".Select"))
        candidates = root.find_elements(
            By.CSS_SELECTOR,
            "button, a, [role='button'], [class*='add'], [class*='plus'], "
            "[aria-label*='瓦썲뒥'], [title*='瓦썲뒥'], [data-testid*='add']"
        )
        for c in candidates:
            txt = (c.text or '').strip()
            cls = (c.get_attribute('class') or '')
            aria = (c.get_attribute('aria-label') or '')
            title = (c.get_attribute('title') or '')
            if (
                ('瓦썲뒥' in txt) or ('add' in cls.lower()) or ('plus' in cls.lower())
                or ('瓦썲뒥' in aria) or ('瓦썲뒥' in title)
            ):
                _scroll_and_click(driver, c)
                _sleep(0.4)


        # 由ъ뒪???녿뒗 ?ъ씠利덈쾭??fallback
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
    """?ъ씠利??쇰꺼 泥댄겕諛뺤뒪 ???React Select 而⑦듃濡ㅼ뿉???ъ씠利덈? ?좏깮?쒕떎."""
    if not size_text:
        return 0
    try:
        t0 = time.time()
        sizes = [s.strip() for s in size_text.split(',') if s.strip()]
        if not sizes:
            return 0

        # ?꾩슂 ?듭뀡 媛쒖닔留뚰겮 Select 異붽????쒕룄
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
                # ?쇳븨 ?뚰듃???듭뀡 媛뺤젣?낅젰(?뱀젙 ENTER濡?留ㅼ묶 ?덈맆 ??
                try:
                    sel_input = sel.find_element(By.CSS_SELECTOR, "input")
                    sel_input.clear()
                    # cm ?쒓린 蹂?섏슜 ?쇳븨 ?쒕룄 (?? "215" ??"21.5")
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
                # ArrowDown?쇰줈 留ㅼ묶 ?듭뀡 ?먯깋 (?뱀젙 ENTER)
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
    """?ъ씠利??좏깮 ?듭뀡???놁쓣 ??蹂댁땐?뺣낫 textarea???ъ씠利덈? 湲곕줉?쒕떎."""
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
        line = f"?듐궎??{size_text}"
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
    """?됱긽 ?낅젰???鍮꾪솢?깆씪 ??蹂댁땐?뺣낫 textarea???됱긽紐낆쓣 湲곕줉?쒕떎."""
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
    """?쒗듃 ?ъ씠利덈? BUYMA ?쇰꺼 鍮꾧탳???꾨낫濡??뺤옣?쒕떎."""
    sz = (size_raw or '').strip()
    if not sz:
        return []

    variants = [sz]
    szu = sz.upper().replace(' ', '')

    # 蹂듯빀 ?쒓린(?? 220/M3W5, US7/250)??遺꾪빐?댁꽌 ?꾨낫濡?異붽?
    parts = [p.strip() for p in re.split(r'[/|]', sz) if p.strip()]
    for p in parts:
        if p not in variants:
            variants.append(p)

    # F/FREE/OS 怨꾩뿴(?꾨━?ъ씠利?
    if szu in {'F', 'FREE', 'FREESIZE', 'OS', 'ONESIZE', 'O/S'}:
        variants.extend([
            'F', 'FREE', 'FREE SIZE', 'ONE SIZE', 'ONESIZE', 'OS', 'O/S',
            '?뺛꺁??, '?뺛꺁?쇈궢?ㅳ궨', '??꺍?듐궎??, '?듐궎?뷸뙁若싥겒??, '?뉐츣?ゃ걮'
        ])


    # ?좊컻 ?レ옄 ?쒓린 ?뺤옣 (?? 240, 24.0, 24cm, JP24)
    numeric_seeds = []
    for token in [sz] + parts:
        only_num = re.sub(r"[^0-9.]", "", token)
        if not only_num:
            continue
        try:
            if '.' in only_num:
                val = float(only_num)
                # 20~35??cm濡?媛꾩＜, 200~350? mm濡?媛꾩＜
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

    # 以묐났 ?쒓굅(?쒖꽌 ?좎?)
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
    t = t.replace('節껓퐤', 'cm').replace('??, 'cm').replace('?삠꺍??, 'cm')
    t = t.replace('?듐궎??, '').replace('size', '')
    t = t.replace('cm', '').replace('mm', '')
    t = t.replace('jp', '').replace('kr', '').replace('us', '').replace('uk', '').replace('eu', '').replace('it', '')
    t = re.sub(r"[\s\-_/\(\)\[\]\{\}:;,+]", '', t)
    # 23.5 == 235 ?뺥깭 鍮꾧탳瑜??꾪빐 ???쒓굅
    t = t.replace('.', '')
    return t


def _size_match(a: str, b: str) -> bool:
    """?ъ씠利??쒓린 a? b媛 ?ㅼ쭏?곸쑝濡?媛숈?吏 ?먮퀎?쒕떎."""
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
    """?꾨━?ъ씠利?怨꾩뿴 ?쒓린?몄? ?먮퀎?쒕떎. (?? free size, one size, f)"""
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
        '吏?뺤뾾??, '?ъ씠利덉뾾??, '?놁쓬', '?대떦?놁쓬',
        '?듐궎?뷸뙁若싥겒??, '?뉐츣?ゃ걮', '?듐궎?뷩겒??, '?ゃ걮',
        '?꾨━', '?꾨━?ъ씠利?,
        '?뺛꺁??, '?뺛꺁?쇈궢?ㅳ궨', '??꺍?듐궎??
    }

    return all(t in free_aliases for t in normalized_tokens)


def _check_no_variation_option(driver, prefer_shitei_nashi: bool = False) -> bool:
    """?ъ씠利??됱긽 ?듭뀡???놁쓣 ??'蹂?뺤뾾??吏?뺛겒?? 怨꾩뿴 ?듭뀡???좏깮?쒕떎."""
    if prefer_shitei_nashi:
        keywords = [
            '?뉐츣?ゃ걮', '?듐궎?뷸뙁若싥겒??, '?듐궎?뷩겒??,
            '鸚됧땿?ゃ걮', '鸚됧숱?ゃ걮', '?먦꺁?ⓦ꺖?룔깾?녈겒??, '?먦꺁?ⓦ꺖?룔깾?녕꽒??, '蹂?뺤뾾??
        ]
    else:
        keywords = [
            '鸚됧땿?ゃ걮', '鸚됧숱?ゃ걮', '?먦꺁?ⓦ꺖?룔깾?녈겒??, '?먦꺁?ⓦ꺖?룔깾?녕꽒??, '?듐궎?뷩겒??,
            '?듐궎?뷸뙁若싥겒??, '?뉐츣?ゃ걮', '蹂?뺤뾾??
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

        # ?ъ씠利?湲곕컲?쇰줈 ?대┃ 媛?ν븳 ?붿냼瑜??먯깋
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

        # ?쇰꺼 諛뺤뒪媛 鍮꾩뼱?덈뒗 寃쎌슦 input ?대쫫?쇰줈 fallback
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

        # React Select 紐⑤뱶 ?좏깮 fallback
        selects = variation.find_elements(By.CSS_SELECTOR, ".Select")
        targets = ['?뉐츣?ゃ걮', '?듐궎?뷸뙁若싥겒??, '?먦꺁?ⓦ꺖?룔깾?녈겒??, '?ⓨ벴鸚됧땿?ゃ걮'] if prefer_shitei_nashi else ['?먦꺁?ⓦ꺖?룔깾?녈겒??, '?ⓨ벴鸚됧땿?ゃ걮', '?듐궎?뷸뙁若싥겒??, '?뉐츣?ゃ걮']
        for sel in selects:
            for target in targets:
                if _select_option_in_select_control(driver, sel, target):
                    return True
    except Exception:
        return False
    return False


def _force_select_shitei_nashi(driver) -> bool:
    """?꾨━?ъ씠利덉뿉??'?뉐츣?ゃ걮' ?뺥솗 ?쇱튂留??좏깮?쒕떎."""
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")

        # 1) ?踰?????移????
        labels = variation.find_elements(By.CSS_SELECTOR, "label")
        for lb in labels:
            txt = (lb.text or '').strip().replace('?', ' ')
            if txt == '?若???:
                _scroll_and_click(driver, lb)
                return True

        # 2) ?ъ씠利??쒕∼?ㅼ슫?먯꽌 '吏?뺛겒?? ?꾩튂 ?대┃
        nodes = variation.find_elements(By.XPATH, ".//*[normalize-space(text())='?若???]")
        for node in nodes:
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

        # 3) React Select?먯꽌 ?뺥솗 ?듭뀡 ?좏깮
        selects = variation.find_elements(By.CSS_SELECTOR, ".Select")
        for sel in selects:
            if _select_option_in_select_control(driver, sel, '?若???):
                return True
    except Exception:
        return False
    return False


def _force_select_shitei_nashi_global(driver) -> bool:
    """?꾨━?ъ씠利덉뿉??紐⑤뱺 ?곸뿭?먯꽌 '?뉐츣?ゃ걮'瑜?李얠븘 ?좏깮?쒕떎."""
    # 1) 湲곕낯 ?곸뿭 ?곗꽑
    if _force_select_shitei_nashi(driver):
        return True

    # 2) ?ъ씠利??쇰낯?ъ씠利?Select(?쇰낯?ъ씠利??놁쓣 ???좏깮 ?쒕룄)
    try:
        selects = driver.find_elements(By.CSS_SELECTOR, ".sell-size-table .Select, .sell-variation .Select")
        for sel in selects:
            if _select_option_in_select_control(driver, sel, '?若???):
                return True
    except Exception:
        pass

    # 3) ?곸뿭 ?ъ씠利??뺥솗 ?쇱튂 ?대┃ ?쒕룄
    try:
        nodes = driver.find_elements(By.XPATH, "//*[normalize-space(text())='?若???]")
        for node in nodes:
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
    """?ъ씠利??뚯씠釉붿쓽 ?쇰낯?ъ씠利?Select?먯꽌 '?뉐츣?ゃ걮' 媛뺤젣 ?좏깮?쒕떎."""
    try:
        root = panel if panel is not None else driver
        # BUYMA ?붾㈃ 援ъ“ 蹂寃쎌쓣 ?鍮꾪빐 ?щ윭 ??됲꽣瑜??쒕룄??
        selects = root.find_elements(By.CSS_SELECTOR, ".sell-size-table .Select")
        if not selects:
            selects = root.find_elements(By.CSS_SELECTOR, ".sell-variation .sell-size-table .Select")
        if not selects:
            return False

        changed = 0
        for sel in selects:
            try:
                # 媛??놁쓣 ??skip
                current = sel.find_elements(By.CSS_SELECTOR, ".Select-value-label")
                if current and (current[0].text or '').strip() == '?若???:
                    changed += 1
                    continue

                # 1? ?諛???????
                if _select_option_in_select_control(driver, sel, '?若???):
                    changed += 1
                    continue

                # 2) 吏곸젒 ?쇳븨/Enter ?좏깮
                try:
                    control = sel.find_element(By.CSS_SELECTOR, ".Select-control")
                    _scroll_and_click(driver, control)
                    _sleep(0.2)
                    inp = sel.find_element(By.CSS_SELECTOR, ".Select-input input")
                    inp.clear()
                    inp.send_keys('?若???)
                    _sleep(0.35)
                    opts = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
                    exact = None
                    for o in opts:
                        if (o.text or '').strip() == '?若???:
                            exact = o
                            break
                    if exact is not None:
                        _scroll_and_click(driver, exact)
                        changed += 1
                        continue
                    inp.send_keys(Keys.ENTER)
                    _sleep(0.2)
                    current2 = sel.find_elements(By.CSS_SELECTOR, ".Select-value-label")
                    if current2 and (current2[0].text or '').strip() == '?若???:
                        changed += 1
                        continue
                except Exception:
                    pass
            except Exception:
                continue
        return changed > 0
    except Exception:
        return False


def _enable_size_selection_ui(driver) -> bool:
    """?ъ씠利??좏깮 UI媛 ?묓? ?덉쓣 ??'?ъ씠利?吏?? 怨꾩뿴 ?좉????대┃???쇱튇??"""
    keywords = ['?듐궎?뷩굮?뉐츣', '?듐궎?뷩걗??, '?듐궎?뷩굮?멩뒢', '?듐궎?뷩굮?ε뒟', '?먦꺁?ⓦ꺖?룔깾?녈걗??]
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
    """泥댄겕諛뺤뒪 ?녿뒗 寃쎌슦 ?ъ씠利??낅젰移몄뿉 媛믪쓣 ?낅젰?쒕떎."""
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
            t = (s or '').strip().replace('?', ' ').lower()
            t = t.replace('?듐궎??, '').replace('size', '').replace('cm', '').replace('??, '')
            t = re.sub(r'\s+', '', t)
            return t

        def _to_mm(s: str):
            """Normalize numeric size text to mm integer. (21.5 -> 215, 215 -> 215)"""
            t = (s or '').strip().lower()
            if not t:
                return None
            t = t.replace('?', ' ').replace('??, 'cm')
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
        has_range_suffix = ('餓δ툓' in (target_text or '')) or ('餓δ툔' in (target_text or ''))

        # 1) ???留ㅼ묶 ???
        for opt in options:
            txt = (opt.text or '').strip()
            if _norm(txt) == target_norm:
                _scroll_and_click(driver, opt)
                _sleep(0.3)
                return True

        # 1-1) ?レ옄 ?ъ씠利덈뒗 mm 湲곗??쇰줈 媛寃?留ㅼ튂
        if target_mm is not None and not has_range_suffix:
            for opt in options:
                txt = (opt.text or '').strip()
                if _to_mm(txt) == target_mm:
                    _scroll_and_click(driver, opt)
                    _sleep(0.3)
                    return True

            # 蹂듭옟???듭뀡 ?뚮뜑留곹븯??寃쎌슦, ?섎룞?낅젰?쇰줈 ?⑦꽩 ?쒕룄
            try:
                query_candidates = [str(target_text).strip()]
                # 275 -> 27.5 ?뺥깭濡?蹂??
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

        # 2) ?쇰낯 ?ъ씠利?S/M/L)? 留ㅼ묶 湲덉? (S媛 XS??嫄몃━??臾몄젣 諛⑹?)
        if target_norm in {'s', 'm', 'l'}:
            return False

        # 3) ?留ㅼ묶 fallback
        for opt in options:
            txt = (opt.text or '').strip()
            txt_norm = _norm(txt)
            if target_norm and target_norm in txt_norm:
                # S XS?留ㅼ묶??????諛?
                if target_norm == 's' and 'xs' in txt_norm:
                    continue
                _scroll_and_click(driver, opt)
                _sleep(0.3)
                return True
        return False
    except Exception:
        return False


def _infer_reference_jp_size(size_raw: str) -> str:
    """???臾몄옄??????????Select ?踰?留ㅽ븨???"""
    # ?꾨━?ъ씠利?NONE 怨꾩뿴? 諛섎뱶??'?뉐츣?ゃ걮' 怨좎젙
    if _is_free_size_text(size_raw):
        return '?若???

    s = (size_raw or '').strip().upper()
    if not s:
        return ''

    # 蹂듯빀 ?쒓린(?? 220/M3W5) ?묒そ ?ъ씠利덉뿉 ?곸슜
    if '/' in s:
        s = s.split('/')[0].strip()

    # ?レ옄 ?쇰꺼??遺숈? ?섎쪟 ?ъ씠利??? 0 (S), 1 (M))??愿꾪샇 ???곷Ц ?ъ씠利덈? ?곗꽑 ?ъ슜
    paren_alpha = re.search(r"\(([A-Z]{1,4})\)", s)
    if paren_alpha:
        s = paren_alpha.group(1)

    # ?쇰컲 ?곷Ц ?섎쪟 ?ъ씠利??좏겙???レ옄 泥섎━蹂대떎 癒쇱? ?댁꽍
    alpha_match = re.search(r"(?<![A-Z])(XXXS|XXS|XS|S|M|L|XL|XXL|XXXL)(?![A-Z])", s)
    if alpha_match:
        s = alpha_match.group(1)

    if s in {'XXS', 'XS'}:
        return 'XS餓δ툔'
    if s == 'S':
        return 'S'
    if s == 'M':
        return 'M'
    if s == 'L':
        return 'L'
    if s in {'XL', 'XXL', 'XXXL'}:
        return 'XL餓δ툓'

    # ?レ옄 ?쒓린 蹂??洹쒖튃: 215 -> 21.5, 250 -> 25.0, 25 -> 25
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

            # ?泥?諛섏쁺: 275(mm) ??? '27cm餓δ툓'?濡?踰꾪궥 泥섎━
            mm_val = int(round(cm * 10))
            if mm_val >= 275:
                return '27cm餓δ툓'

            if abs(cm - round(cm)) < 1e-9:
                return str(int(round(cm)))
            return f"{cm:.1f}"
        except Exception:
            return s

    return s


def _fill_size_table_rows(driver, panel, size_text: str) -> int:
    """?먮ℓ?먯슜 ?ъ씠利?sell-size-table)?먯꽌 ?ъ씠利덈챸??吏???꾩튂???낅젰?쒕떎."""
    if not size_text:
        return 0
    try:
        sizes = [s.strip() for s in size_text.split(',') if s.strip()]
        if not sizes:
            return 0

        # ?곷떒 紐⑤뱶 Select瑜?'?먦꺁?ⓦ꺖?룔깾?녈걗??濡??ㅼ젙
        mode_selects = panel.find_elements(By.CSS_SELECTOR, ".bmm-l-grid-no-bottom .Select")
        if mode_selects:
            _select_option_in_select_control(driver, mode_selects[0], '?먦꺁?ⓦ꺖?룔깾?녈걗??)
            _sleep(0.4)

        table = panel.find_elements(By.CSS_SELECTOR, ".sell-size-table")
        if not table:
            return 0

        # ?꾩슂 ?듭뀡留?異붽? (怨좎젙 12媛??쒗븳?쇰줈 ?쇰? ?ъ씠利??꾨씫?섎뒗 臾몄젣 諛⑹?)
        max_add_attempts = max(len(sizes) * 2, 24)
        for _ in range(max_add_attempts):
            rows = panel.find_elements(By.CSS_SELECTOR, ".sell-size-table tbody tr")
            if len(rows) >= len(sizes):
                break
            add_links = panel.find_elements(By.XPATH, ".//div[contains(@class,'bmm-c-form-table__foot')]//a")
            clicked = False
            for a in add_links:
                txt = (a.text or '').strip()
                if '?겹걮?꾠궢?ㅳ궨?믦옙?? in txt or '?듐궎?? in txt:
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

                # ?ㅻⅨ ?곸뿭(?쇰낯?ъ씠利??먯꽌 ?좏깮
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


# ---- 移댄뀒怨좊━ 異붾줎 留ㅽ븨 ----
MEASURE_LABEL_KEYWORDS: Dict[str, List[str]] = {
    "珥앹옣": ["?訝?, "渶뤶툑", "?③빓", "訝?],
    "?닿묠?덈퉬": ["?⒴퉭"],
    "媛?대떒硫?: ["翁ュ퉭", "?멨쎊", "?멨퉭", "?먦궧??],
    "?뚮ℓ湲몄씠": ["熬뽨툑", "獒꾡툑", "?녴걤訝?],
    "?덈━?⑤㈃": ["?╉궓?밤깉", "?닷쎊"],
    "?됰뜦?대떒硫?: ["?믡긿??],
    "?덈쾮吏?⑤㈃": ["?뤵걼??, "歷▲굤", "鸚ゃ굚??],
    "諛묒쐞": ["?▽툓"],
    "諛묐떒?⑤㈃": ["獒얍퉭", "?쇻걹亮?],
    "諛쒕낵": ["??궎??, "擁녑퉭"],
    "援쎈넂??: ["?믡꺖?ラ쳵", "?믡꺖??],
}


def _format_measure_value(v: str) -> str:
    try:
        f = float(v)
        if abs(f - round(f)) < 1e-9:
            return str(int(round(f)))
        return f"{f:.1f}".rstrip("0").rstrip(".")
    except Exception:
        return (v or "").strip()


def _extract_actual_measure_map(actual_size_text: str) -> Dict[str, str]:
    raw = (actual_size_text or "").strip()
    if not raw:
        return {}
    out: Dict[str, str] = {}
    for key in MEASURE_LABEL_KEYWORDS.keys():
        m = re.search(rf"{re.escape(key)}\s*([-+]?\d+(?:\.\d+)?)", raw)
        if m:
            out[key] = _format_measure_value(m.group(1))
    return out


def _normalize_actual_size_for_upload(actual_size_text: str) -> str:
    text = (actual_size_text or "").strip()
    lowered = text.lower()
    if not text or lowered in {"none", "n/a", "na", "-", "?놁쓬"}:
        return ""
    return text


def _fill_size_edit_details(driver, panel, actual_size_text: str, max_rows: int = 0) -> int:
    """?ъ씠利?渶③썓 ?앹뾽?먯꽌 ?쇰꺼-?ㅼ륫 留ㅼ묶?쇰줈 媛믪쓣 ?낅젰?쒕떎."""
    measure_map = _extract_actual_measure_map(actual_size_text)
    if not measure_map:
        return 0
    try:
        rows = panel.find_elements(By.CSS_SELECTOR, ".sell-size-table tbody tr")
        if not rows:
            return 0
        if max_rows > 0:
            rows = rows[:max_rows]

        filled_rows = 0
        for row in rows:
            try:
                edit_btn = None
                for c in row.find_elements(By.CSS_SELECTOR, "a, button, [role='button']"):
                    t = (c.text or "").strip()
                    if "渶③썓" in t or "?몄쭛" in t:
                        edit_btn = c
                        break
                if edit_btn is None:
                    continue

                _scroll_and_click(driver, edit_btn)
                _sleep(0.5)

                modal_root = None
                for root in driver.find_elements(By.CSS_SELECTOR, ".ReactModalPortal, .bmm-c-modal, [role='dialog']"):
                    try:
                        if root.is_displayed():
                            modal_root = root
                            break
                    except Exception:
                        continue
                if modal_root is None:
                    modal_root = driver

                input_pairs: List[Tuple[object, str]] = []
                for ipt in modal_root.find_elements(By.CSS_SELECTOR, "input.bmm-c-text-field, input[type='text'], input[type='number']"):
                    try:
                        if not ipt.is_displayed() or not ipt.is_enabled():
                            continue
                    except Exception:
                        continue
                    label_text = driver.execute_script(
                        "var el=arguments[0];"
                        "var row=el.closest('tr,li,.bmm-l-grid,.bmm-c-field,div')||el.parentElement;"
                        "if(!row) return '';"
                        "var lbl=row.querySelector('th,label,.bmm-c-field__label,p,span,td');"
                        "var txt=(lbl?lbl.textContent:row.textContent)||'';"
                        "return txt.replace(/\\s+/g,' ').trim();",
                        ipt
                    ) or ""
                    input_pairs.append((ipt, str(label_text)))

                if not input_pairs:
                    continue

                used_keys = set()
                ok_count = 0
                unmatched_inputs: List[object] = []

                for ipt, lbl in input_pairs:
                    label = (lbl or "").strip()
                    matched_key = None
                    for key, jp_keys in MEASURE_LABEL_KEYWORDS.items():
                        if key in used_keys:
                            continue
                        if any(jk in label for jk in jp_keys):
                            matched_key = key
                            break
                    if matched_key and matched_key in measure_map:
                        val = measure_map[matched_key]
                        ok = driver.execute_script(
                            "var el=arguments[0], val=arguments[1];"
                            "el.removeAttribute('disabled');"
                            "el.removeAttribute('readonly');"
                            "var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                            "setter.call(el, val);"
                            "el.dispatchEvent(new Event('input',{bubbles:true}));"
                            "el.dispatchEvent(new Event('change',{bubbles:true}));"
                            "el.dispatchEvent(new Event('blur',{bubbles:true}));"
                            "return ((el.value||'').trim()===(val||'').trim());",
                            ipt, val
                        )
                        if ok:
                            ok_count += 1
                            used_keys.add(matched_key)
                    else:
                        unmatched_inputs.append(ipt)

                remaining_values = [v for k, v in measure_map.items() if k not in used_keys]
                for i, ipt in enumerate(unmatched_inputs):
                    if i >= len(remaining_values):
                        break
                    val = remaining_values[i]
                    ok = driver.execute_script(
                        "var el=arguments[0], val=arguments[1];"
                        "el.removeAttribute('disabled');"
                        "el.removeAttribute('readonly');"
                        "var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                        "setter.call(el, val);"
                        "el.dispatchEvent(new Event('input',{bubbles:true}));"
                        "el.dispatchEvent(new Event('change',{bubbles:true}));"
                        "el.dispatchEvent(new Event('blur',{bubbles:true}));"
                        "return ((el.value||'').trim()===(val||'').trim());",
                        ipt, val
                    )
                    if ok:
                        ok_count += 1

                for b in modal_root.find_elements(By.CSS_SELECTOR, "button, a, [role='button']"):
                    bt = (b.text or "").strip()
                    if any(k in bt for k in ["岳앭춼", "若뚥틙", "OK", "?⑴뵪", "?삯뙯"]):
                        _scroll_and_click(driver, b)
                        _sleep(0.3)
                        break

                if ok_count > 0:
                    filled_rows += 1
            except Exception:
                continue
        return filled_rows
    except Exception:
        return 0


FEMALE_KEYWORDS = [
    'women', 'womens', "women's",
    '?ъ꽦', '?ъ옄',
    '?с깈?ｃ꺖??,
    'skirt', '移섎쭏',
    'dress', '?먰뵾??,
    'blouse', '釉붾씪?곗뒪',
    'heel', '??,
    'crop', '?щ∼',
    'mini', '誘몃땲'
]

MALE_KEYWORDS = [
    'men', 'mens', "men's",
    '?⑥꽦', '?⑥옄',
    '?▲꺍??
]

BUYMA_GENDER_CATEGORY_MAP = {
    'F': '?с깈?ｃ꺖?밤깢?▲긿?룔깾??,
    'M': '?▲꺍?뷩깢?▲긿?룔깾??,
    'U': '?▲꺍?뷩깢?▲긿?룔깾??,
}


def column_index_to_letter(index: int) -> str:
    """0-based ???몃뜳?ㅻ? Google Sheets ??臾몄옄濡?蹂?섑븳??"""
    if index < 0:
        raise ValueError("???몃뜳?ㅻ뒗 0 ?댁긽?댁뼱???⑸땲??")
    result = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_sheet_header_map(service, sheet_name: str) -> Dict[str, int]:
    """1???ㅻ뜑紐낆쓣 ?쎌뼱 ?ㅻ뜑紐?-> 0-based ???몃뜳??留듭쓣 諛섑솚?쒕떎."""
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
        print(f"?ㅻ뜑 議고쉶 ?ㅽ뙣: {e}")
        return {}


def update_cell_by_header(
    service,
    sheet_name: str,
    row_num: int,
    header_map: Dict[str, int],
    header_name: str,
    value: str,
) -> bool:
    """?ㅻ뜑紐?湲곗??쇰줈 ?뱀젙 ? 媛믪쓣 ?낅뜲?댄듃?쒕떎."""
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
        print(f"  {row_num}??{header_name} ?낅뜲?댄듃 ?ㅽ뙣: {e}")
        return False

CATEGORY_KEYWORDS = [
    # ---------------- ?좊컻 ----------------
    (['indoor', '?몃룄??, '?몃룄?댄솕', 'indoorization', 'libre'], None, '??, '?밤깑?쇈궖??),
    (['sneaker', '?ㅻ땲而ㅼ쫰', '?대룞??, 'old skool', '?щ뱶?ㅼ엥'], None, '??, '?밤깑?쇈궖??),
    (['running', '?щ떇??], None, '??, '?⒲꺍?뗣꺍?겹궥?γ꺖??),
    (['sandal', '?뚮뱾', 'slide', '?щ씪?대뱶'], None, '??, '?듐꺍???),
    (['boot', '遺痢?, '?뚯빱'], None, '??, '?뽧꺖??),
    (['loafer', '濡쒗띁'], None, '??, '??꺖?뺛궊??),

    # ---------------- ?곸쓽 ----------------
    (['t-shirt', 'tee', '?곗뀛痢?, '諛섑뙏'], None, '?덀긿?쀣궧', 'T?룔깵?꾠꺕?ャ긿?덀궫??),
    (['long sleeve', '湲댄뙏'], None, '?덀긿?쀣궧', '?룩쥤T?룔깵??),
    (['hoodie', '?꾨뱶', '?꾨뱶??], None, '?덀긿?쀣궧', '?묆꺖?ャ꺖?삠깢?쇈깈??),
    (['zip-up', '吏묒뾽'], None, '?덀긿?쀣궧', '?멥긿?쀣깙?쇈궖??),
    (['sweatshirt', '留⑦닾留?, 'mtm'], None, '?덀긿?쀣궧', '?밤궑?㎯긿??),
    (['shirt', '?붿툩'], None, '?덀긿?쀣궧', '?룔깵??),
    (['knit', '?덊듃'], None, '?덀긿?쀣궧', '?뗣긿?덀꺕?삠꺖?욍꺖'),

    # ---------------- ?섏쓽 ----------------
    (['jeans', 'denim', '泥?컮吏'], None, '?쒌깉?졼궧', '?뉎깑?졼꺕?멥꺖?녈궨'),
    (['slacks', '?щ옓??], None, '?쒌깉?졼궧', '?밤꺀?껁궚??),
    (['pants', '?ъ툩'], None, '?쒌깉?졼궧', '?묆꺍??),
    (['jogger', '議곌굅'], None, '?쒌깉?졼궧', '?멥깾?с꺖?묆꺍??),
    (['cargo', '移닿퀬'], None, '?쒌깉?졼궧', '?ャ꺖?담깙?녈깂'),
    (['shorts', '諛섎컮吏'], None, '?쒌깉?졼궧', '?룔깾?쇈깂'),

    # ---------------- ?꾩슦??----------------
    (['padding', '?⑤뵫', '?ㅼ슫'], None, '?㏂궑?욍꺖', '??╉꺍?멥깵?긱긿??),
    (['coat', '肄뷀듃'], None, '?㏂궑?욍꺖', '?녈꺖??),
    (['jacket', '?먯폆'], None, '?㏂궑?욍꺖', '?멥깵?긱긿??),
    (['blazer', '釉붾젅?댁?'], None, '?㏂궑?욍꺖', '?녴꺖?⒲꺖?됥궦?ｃ궞?껁깉'),
    (['cardigan', '媛?붽굔'], None, '?㏂궑?욍꺖', '?ャ꺖?뉎궍?с꺍'),
    (['windbreaker', '諛붾엺留됱씠'], None, '?㏂궑?욍꺖', '?듽궎??꺍?멥깵?긱긿??),

    # ---------------- ?먰뵾??----------------
    (['dress', '?먰뵾??], '?с깈?ｃ꺖?밤깢?▲긿?룔깾??, '??꺍?붵꺖??, '??꺍?붵꺖??),

    # ---------------- 媛諛?----------------
    (['backpack', '諛깊뙥'], None, '?먦긿??, '?먦긿??깙?껁궚'),
    (['crossbag', '?щ줈?ㅻ갚'], None, '?먦긿??, '?룔깾?ャ??쇈깘?껁궛'),
    (['tote', '?좏듃'], None, '?먦긿??, '?덀꺖?덀깘?껁궛'),

    # ---------------- ?낆꽭 ----------------
    (['cap', '紐⑥옄'], None, '?㏂궚?삠궢?ゃ꺖', '躍썲춴'),
    (['beanie', '鍮꾨땲'], None, '?㏂궚?삠궢?ゃ꺖', '?뗣긿?덂맒'),
    (['belt', '踰⑦듃'], None, '?㏂궚?삠궢?ゃ꺖', '?쇻꺂??),
    (['socks', '?묐쭚'], None, '?㏂궚?삠궢?ゃ꺖', '?썬긿??궧'),
]


def detect_gender_raw(title: str) -> str:
    """?곹뭹紐?湲곕컲?쇰줈 ?깅퀎??M/F/U 濡?遺꾨쪟?쒕떎."""
    text = (title or '').lower()

    if any(keyword in text for keyword in FEMALE_KEYWORDS):
        return 'F'

    if any(keyword in text for keyword in MALE_KEYWORDS):
        return 'M'

    return 'U'


def convert_gender_for_buyma(gender: str) -> str:
    """?대? ?깅퀎 肄붾뱶瑜?BUYMA ?깅퀎 ?쇰꺼濡?蹂?섑븳??"""
    if gender == 'F':
        return '?с깈?ｃ꺖??
    if gender == 'M':
        return '?▲꺍??
    return '?▲꺍??


def detect_gender(title: str) -> str:
    """?곹뭹紐?湲곕컲 ?깅퀎??BUYMA ?낅줈?쒖슜 ?쇰꺼濡?蹂?섑븳??"""
    raw_gender = detect_gender_raw(title)

    # TODO: 異뷀썑 AI 遺꾨쪟 ?곌껐 媛??
    # if raw_gender == 'U':
    #     raw_gender = detect_gender_ai(title)

    return convert_gender_for_buyma(raw_gender)


def _get_buyma_fashion_category_from_gender(title: str) -> str:
    """?곹뭹紐낆뿉??媛먯????깅퀎??BUYMA ?곸쐞 ?⑥뀡 移댄뀒怨좊━濡?蹂?섑븳??"""
    raw_gender = detect_gender_raw(title)
    return BUYMA_GENDER_CATEGORY_MAP.get(raw_gender, BUYMA_GENDER_CATEGORY_MAP['U'])



def _get_buyma_fashion_category_from_sheet(category_large: str, fallback_title: str) -> str:
    text = (category_large or "").strip().lower()
    if any(k in text for k in ["여성", "여자", "우먼", "women", "lady", "レディース"]):
        return BUYMA_GENDER_CATEGORY_MAP.get('F', BUYMA_GENDER_CATEGORY_MAP['U'])
    if any(k in text for k in ["남성", "남자", "맨", "men", "メンズ"]):
        return BUYMA_GENDER_CATEGORY_MAP.get('M', BUYMA_GENDER_CATEGORY_MAP['U'])
    return _get_buyma_fashion_category_from_gender(fallback_title)


def _infer_buyma_category(product_name_kr: str, product_name_en: str, brand: str = '', musinsa_category_large: str = '') -> Tuple[str, str, str]:
    """?곹뭹紐낆뿉??BUYMA 移댄뀒怨좊━ 3?④퀎瑜?異붾줎?쒕떎."""
    title = f"{product_name_kr} {product_name_en}".strip()
    text = f"{product_name_kr} {product_name_en} {brand}".lower()
    fashion_category = _get_buyma_fashion_category_from_sheet(musinsa_category_large, title)
    if any(token in text for token in ['new balance', '?대컻???, 'mr530', '530lg', '530sg', '530ka', 'm1906', '1906r', '2002r', '327', '990v', '991', '992', '993']):
        return (fashion_category, '??, '?밤깑?쇈궖??)
    for keywords, cat1, cat2, cat3 in CATEGORY_KEYWORDS:
        if any(kw.lower() in text for kw in keywords):
            if cat1 is None:
                cat1 = fashion_category
            return (cat1, cat2 or '', cat3 or '')
    return ('', '', '')


def _get_category_select_el(driver, item_index: int):
    """item_index???대떦?섎뒗 React-Select ?붿냼瑜?諛섑솚?쒕떎."""
    if item_index == 0:
        return driver.find_element(By.CSS_SELECTOR, '.sell-category-select')
    items = driver.find_elements(By.CSS_SELECTOR, '.sell-category__item')
    if len(items) <= item_index:
        return None
    return items[item_index].find_element(By.CSS_SELECTOR, '.Select')


def _select_category_by_typing(driver, item_index: int, target_label: str) -> bool:
    """而ㅻ━ ?좏깮 ???낅젰媛믪쑝濡??꾪꽣留곹븳 泥?踰덉㎏ ?듭뀡???대┃?쒕떎.
    React-Select????댄븨 ?꾪꽣 諛⑹떇??ArrowDown 諛⑹떇蹂대떎 ?⑥뵮 鍮좊Ⅴ怨??덉젙?대떎."""
    sel_el = _get_category_select_el(driver, item_index)
    if sel_el is None:
        return False

    ctrl = sel_el.find_element(By.CSS_SELECTOR, '.Select-control')
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", ctrl)
    _sleep(0.3)
    driver.execute_script("arguments[0].click()", ctrl)
    _sleep(0.6)

    combo = sel_el.find_element(By.CSS_SELECTOR, '.Select-input > input, .Select-input')
    combo.send_keys(target_label)
    _sleep(0.8)

    # ?꾪꽣留곷맂 ?듭뀡?먯꽌 ?뺥솗?쇱튂??癒쇱?, ?ы븿?섎㈃ 洹??ㅼ쓬 ?대┃
    try:
        options = driver.find_elements(By.CSS_SELECTOR, '.Select-menu-outer .Select-option')
        exact = next((o for o in options if o.text.strip() == target_label), None)
        partial = next((o for o in options if target_label in o.text), None)
        chosen = exact or partial
        if chosen:
            _scroll_and_click(driver, chosen)
            _sleep(1.5)
            return True
    except Exception:
        pass

    # ?꾪꽣 ?⑥뒪: ?낅젰 ?쇱튂 留ㅼ슦 ?곸쑝硫?ArrowDown 蹂댁“二쇨린 (80媛??쒗븳)
    try:
        for _ in range(len(target_label)):
            combo.send_keys(Keys.BACK_SPACE)
        _sleep(0.2)
    except Exception:
        pass

    driver.execute_script("arguments[0].click()", ctrl)
    _sleep(0.6)
    combo = sel_el.find_element(By.CSS_SELECTOR, '.Select-input > input, .Select-input')
    seen = []
    for _ in range(80):
        combo.send_keys(Keys.ARROW_DOWN)
        _sleep(0.12)
        focused = driver.execute_script("""
            var items = document.querySelectorAll('.sell-category__item');
            var sel = arguments[0] === 0
                ? document.querySelector('.sell-category-select')
                : items[arguments[0]].querySelector('.Select');
            var f = sel ? sel.querySelector('.Select-option.is-focused') : null;
            return f ? (f.getAttribute('aria-label') || f.textContent.trim() || '') : '';
        """, item_index)
        if focused == target_label:
            combo.send_keys(Keys.ENTER)
            _sleep(1.5)
            return True
        if focused:
            if focused in seen and len(seen) > 2 and focused == seen[0]:
                break
            if focused not in seen:
                seen.append(focused)
    combo.send_keys(Keys.ESCAPE)
    _sleep(0.3)
    return False


# ArrowDown ?泥??섎떒: ??댄븨 諛⑹떇 fallback?쇰줈 ?ъ슜, ???덈맆 ???泥?
_select_category_by_arrow = _select_category_by_typing


def _find_best_option_by_arrow(driver, item_index: int, target_keyword: str,
                               fallback_other: bool = True) -> bool:
    """sell-category__item??Select?먯꽌 ?ㅼ썙???ы븿?섎뒗 ?듭뀡???좏깮?쒕떎.
    React-Select ??댄븨 ?꾪꽣 癒쇱? ?쒕룄?섍퀬, ?ㅽ뙣 ??ArrowDown ?щ윭 ?? 洹몃옒???ㅽ뙣 ??'?앫겗餓? fallback."""
    sel_el = _get_category_select_el(driver, item_index)
    if sel_el is None:
        return False

    ctrl = sel_el.find_element(By.CSS_SELECTOR, '.Select-control')
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", ctrl)
    _sleep(0.3)
    driver.execute_script("arguments[0].click()", ctrl)
    _sleep(0.6)

    combo = sel_el.find_element(By.CSS_SELECTOR, '.Select-input > input, .Select-input')
    combo.send_keys(target_keyword)
    _sleep(0.8)

    try:
        options = driver.find_elements(By.CSS_SELECTOR, '.Select-menu-outer .Select-option')
        # ?뺥솗 ?쇱튂 癒쇱?, ?ы븿 留ㅼ묶
        exact = next((o for o in options if o.text.strip() == target_keyword), None)
        partial = next((o for o in options if target_keyword in o.text), None)
        chosen = exact or partial
        if chosen:
            _scroll_and_click(driver, chosen)
            _sleep(1.5)
            return True
        # ?꾪꽣 寃곌낵 ?놁쑝硫?'?앫겗餓? fallback
        if fallback_other:
            other = next((o for o in options if '?앫겗餓? in o.text), None)
            if other:
                _scroll_and_click(driver, other)
                _sleep(1.5)
                return True
    except Exception:
        pass

    # 移댄뀒怨좊━ ?낅젰 媛?吏????ArrowDown 諛⑹떇 ?뚰뵾
    try:
        for _ in range(len(target_keyword)):
            combo.send_keys(Keys.BACK_SPACE)
        _sleep(0.2)
    except Exception:
        pass

    driver.execute_script("arguments[0].click()", ctrl)
    _sleep(0.6)
    combo = sel_el.find_element(By.CSS_SELECTOR, '.Select-input > input, .Select-input')
    seen = []
    for _ in range(80):
        combo.send_keys(Keys.ARROW_DOWN)
        _sleep(0.12)
        focused = driver.execute_script("""
            var items = document.querySelectorAll('.sell-category__item');
            var sel = arguments[0] === 0
                ? document.querySelector('.sell-category-select')
                : items[arguments[0]].querySelector('.Select');
            var f = sel ? sel.querySelector('.Select-option.is-focused') : null;
            return f ? (f.getAttribute('aria-label') || f.textContent.trim() || '') : '';
        """, item_index)
        if focused and target_keyword in focused:
            combo.send_keys(Keys.ENTER)
            _sleep(1.5)
            return True
        if focused:
            if focused in seen and len(seen) > 2 and focused == seen[0]:
                break
            if focused not in seen:
                seen.append(focused)
    combo.send_keys(Keys.ESCAPE)
    _sleep(0.3)

    if fallback_other and seen:
        return _find_best_option_by_arrow(driver, item_index, '?앫겗餓?,
                                          fallback_other=False)
    return False


def _dismiss_overlay(driver):
    """???踰?????踰????嫄?""
    driver.execute_script("""
        document.querySelectorAll('#driver-page-overlay, .driver-popover, [id*="driver-"]')
            .forEach(function(el) { el.remove(); });
    """)
    _sleep(0.3)


def _find_section_field(driver, section_title: str, field_css: str):
    """Find a field under a BUYMA form section title."""
    sections = driver.find_elements(By.CSS_SELECTOR, "p.bmm-c-summary__ttl")
    for sec in sections:
        if section_title in sec.text:
            # ?듭뀡 而⑦뀒?대꼫?먯꽌 肄붾뱶 ?먯깋
            parent = sec
            for _ in range(5):
                parent = parent.find_element(By.XPATH, '..')
                fields = parent.find_elements(By.CSS_SELECTOR, field_css)
                if fields:
                    return fields[0]
    return None


def _click_react_select_option(driver, select_container, keyword: str) -> bool:
    """React Select 而댄룷?뚰듃?먯꽌 ?듭뀡???대┃?쒕떎"""
    try:
        # Select 而⑦듃濡??대┃?섏뿬 蹂듭옟???쒓린
        control = select_container.find_element(By.CSS_SELECTOR, ".Select-control, [class*='Select-control']")
        control.click()
        _sleep(0.5)
        # ?듭뀡 紐⑸줉?먯꽌 ?ㅼ썙??留ㅼ묶
        options = select_container.find_elements(By.CSS_SELECTOR, ".Select-option, [class*='Select-option']")
        for opt in options:
            if keyword in opt.text:
                opt.click()
                _sleep(0.5)
                return True
    except Exception:
        pass
    return False


def _safe_input(prompt: str) -> str:
    """鍮꾨??뷀삎 ?ㅽ뻾?먯꽌???낅젰 ?湲????鍮?臾몄옄?댁쓣 諛섑솚?쒕떎."""
    try:
        return input(prompt)
    except EOFError:
        print("  ?낅젰 ?湲곕? 嫄대꼫?곷땲?? (鍮꾨??뷀삎 ?ㅽ뻾)")
        return ''


def _find_buyma_button_by_keywords(driver, keywords: List[str], timeout: float = 0.0):
    """踰꾪듉/submit ?붿냼 以??띿뒪?몃굹 value ???ㅼ썙?쒓? ?ы븿??泥??붿냼瑜?李얜뒗??"""
    end_time = time.time() + max(0.0, timeout)
    while True:
        try:
            candidates = driver.find_elements(
                By.CSS_SELECTOR,
                "button, input[type='submit'], input[type='button'], a[role='button']"
            )
            for candidate in candidates:
                text = (candidate.text or '').strip()
                value = (candidate.get_attribute('value') or '').strip()
                label = f"{text} {value}".strip()
                if any(keyword in label for keyword in keywords):
                    return candidate
        except Exception:
            pass

        if time.time() >= end_time:
            return None
        _sleep(0.5)


def _click_buyma_button(driver, button, success_message: str) -> bool:
    """踰꾪듉???붾㈃ 以묒븰?쇰줈 ?ㅽ겕濡ㅽ븳 ???덉쟾?섍쾶 ?대┃?쒕떎."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        _sleep(0.5)
        driver.execute_script("arguments[0].click();", button)
        print(success_message)
        return True
    except Exception:
        try:
            _scroll_and_click(driver, button)
            print(success_message)
            return True
        except Exception:
            return False


def _submit_buyma_listing(driver, row_num: int) -> bool:
    """?ㅻ쪟 ?놁씠 ???낅젰???앸궃 寃쎌슦 BUYMA ?뺤씤 踰꾪듉???먮룞 ?대┃?쒕떎."""
    try:
        submit_btn = _find_buyma_button_by_keywords(
            driver,
            ['?ε뒟?끻??믥▶沃띲걲??, '?ε뒟?끻?', '閻븃첀']
        )
        if not submit_btn:
            raise RuntimeError("?낅젰 ?댁슜 ?뺤씤 踰꾪듉??李얠? 紐삵뻽?듬땲??")
        if not _click_buyma_button(driver, submit_btn, f"  ??{row_num}??異쒗뭹 ?뺤씤 踰꾪듉 ?먮룞 ?대┃!"):
            raise RuntimeError("?낅젰 ?댁슜 ?뺤씤 踰꾪듉 ?대┃???ㅽ뙣?덉뒿?덈떎.")
        _sleep(3)
        return True
    except Exception as e:
        print(f"  ??異쒗뭹 踰꾪듉 ?먮룞 ?대┃ ?ㅽ뙣: {e}")
        return False


def _finalize_buyma_listing(driver, row_num: int) -> bool:
    """?뺤씤 ?섏씠吏?먯꽌 理쒖쥌 異쒗뭹 踰꾪듉??李얠븘 ?먮룞 ?대┃?쒕떎."""
    try:
        final_btn = _find_buyma_button_by_keywords(
            driver,
            ['?볝겗?끻??㎩눣?곥걲??, '?뷴뱚?쇻굥', '?ч뼀?쇻굥', '?삯뙯?쇻굥', '若뚥틙?쇻굥'],
            timeout=10.0,
        )
        if not final_btn:
            raise RuntimeError("理쒖쥌 異쒗뭹 踰꾪듉??李얠? 紐삵뻽?듬땲??")
        if not _click_buyma_button(driver, final_btn, f"  ??{row_num}??理쒖쥌 異쒗뭹 踰꾪듉 ?먮룞 ?대┃!"):
            raise RuntimeError("理쒖쥌 異쒗뭹 踰꾪듉 ?대┃???ㅽ뙣?덉뒿?덈떎.")
        _sleep(3)
        return True
    except Exception as e:
        print(f"  ??理쒖쥌 異쒗뭹 ?먮룞 ?대┃ ?ㅽ뙣: {e}")
        return False


def _handle_success_after_fill(driver, row_num: int, upload_mode: str) -> Tuple[bool, bool]:
    """???낅젰 ?꾨즺 ??review/auto 紐⑤뱶???곕씪 ?ㅼ쓬 ?숈옉??泥섎━?쒕떎."""
    print(f"\n  ???낅젰???꾨즺?섏뿀?듬땲??")

    if upload_mode == 'auto':
        print("  ?ㅻ쪟媛 ?놁뼱 ?먮룞 ?쒖텧??吏꾪뻾?⑸땲??")
        if not _submit_buyma_listing(driver, row_num):
            print("  釉뚮씪?곗??먯꽌 吏곸젒 異쒗뭹?댁＜?몄슂.")
            _safe_input("  異쒗뭹 ??Enter瑜??뚮윭二쇱꽭??.")
            return True, False
        if not _finalize_buyma_listing(driver, row_num):
            print("  ?뺤씤 ?섏씠吏?먯꽌 吏곸젒 理쒖쥌 異쒗뭹?댁＜?몄슂.")
            _safe_input("  理쒖쥌 異쒗뭹 ??Enter瑜??뚮윭二쇱꽭??.")
            return True, False
        return True, True

    print("  ?뺤씤??紐⑤뱶?낅땲?? 釉뚮씪?곗??먯꽌 ?댁슜??寃?좏븳 ???좏깮?댁＜?몄슂.\n")
    while True:
        choice = _safe_input("  [Enter] ?ㅼ쓬 ?곹뭹?쇰줈  |  [s] ?쒖텧(異쒗뭹)  |  [q] 醫낅즺: ").strip().lower()
        if choice == '':
            print(f"  -> {row_num}??嫄대꼫?")
            return True, False
        if choice == 's':
            if not _submit_buyma_listing(driver, row_num):
                print("  釉뚮씪?곗??먯꽌 吏곸젒 異쒗뭹?댁＜?몄슂.")
                _safe_input("  異쒗뭹 ??Enter瑜??뚮윭二쇱꽭??.")
            return True, False
        if choice == 'q':
            print("異쒗뭹??醫낅즺?⑸땲??)
            return False, False
        print("  ?섎せ ?낅젰?덉뒿?덈떎. Enter/s/q 以묒뿉???좏깮?댁＜?몄슂.")


def _detect_title_input_issue(name_input, intended_title: str) -> str:
    """?곹뭹紐??낅젰媛믪씠 湲몄씠 ?쒗븳 ?깆쑝濡??뺤긽 諛섏쁺?섏? ?딆븯?붿? ?뺤씤?쒕떎."""
    try:
        actual_value = (name_input.get_attribute('value') or '').strip()
        maxlength_raw = (name_input.get_attribute('maxlength') or '').strip()
        validation_message = (name_input.get_attribute('validationMessage') or '').strip()

        maxlength = int(maxlength_raw) if maxlength_raw.isdigit() else 0
        if maxlength and len(intended_title) > maxlength:
            return f"?곹뭹紐?湲몄씠 珥덇낵: {len(intended_title)}??/ ?쒗븳 {maxlength}??

        if actual_value != intended_title:
            if validation_message:
                return f"?곹뭹紐??낅젰 ?쒗븳: {validation_message}"
            if len(actual_value) < len(intended_title):
                return f"?곹뭹紐??낅젰媛믪씠 ?섎졇?듬땲?? ?낅젰 {len(intended_title)}??/ 諛섏쁺 {len(actual_value)}??
            return "?곹뭹紐??낅젰媛믪씠 ?붿껌媛믨낵 ?ㅻ쫭?덈떎"

        if validation_message:
            return f"?곹뭹紐?寃利?硫붿떆吏: {validation_message}"
    except Exception:
        return ""
    return ""


def _normalize_buyma_title_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _truncate_buyma_title_text(text: str, limit: int) -> str:
    text = _normalize_buyma_title_text(text)
    if limit <= 0 or len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _build_buyma_product_title(brand_en: str, name_en: str, color_en: str, max_length: int = 0) -> str:
    brand_en = _normalize_buyma_title_text(brand_en)
    name_en = _normalize_buyma_title_text(name_en)
    color_en = _normalize_buyma_title_text(color_en)

    candidates = []

    full_parts = []
    if brand_en:
        full_parts.append(f"[{brand_en}]")
    if name_en:
        full_parts.append(name_en)
    if color_en:
        full_parts.append(color_en)
    candidates.append(_normalize_buyma_title_text(" ".join(full_parts)))

    no_bracket_parts = []
    if brand_en:
        no_bracket_parts.append(brand_en)
    if name_en:
        no_bracket_parts.append(name_en)
    if color_en:
        no_bracket_parts.append(color_en)
    candidates.append(_normalize_buyma_title_text(" ".join(no_bracket_parts)))

    name_color = _normalize_buyma_title_text(" ".join([p for p in [name_en, color_en] if p]))
    if name_color:
        candidates.append(name_color)

    if name_en:
        candidates.append(name_en)

    seen = set()
    unique_candidates = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)

    if max_length > 0:
        for candidate in unique_candidates:
            if len(candidate) <= max_length:
                return candidate

        if name_en:
            return _truncate_buyma_title_text(name_en, max_length)
        return _truncate_buyma_title_text(unique_candidates[0] if unique_candidates else "", max_length)

    return unique_candidates[0] if unique_candidates else ""


def fill_buyma_form(driver, row_data: Dict[str, str]) -> str:
    """諛붿씠留?異쒗뭹 ???곹뭹 ?뺣낫瑜??먮룞 ?낅젰?쒕떎.
    諛붿씠留덈뒗 React 湲곕컲 bmm-c-* 而댄룷?뚰듃瑜??ъ슜?섎ŉ name/id ?띿꽦???놁쓬."""
    try:
        driver.get(BUYMA_SELL_URL)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".bmm-c-heading__ttl"))
        )
        _sleep(3)

        row_num = row_data['row_num']
        print(f"\n--- [{row_num}踰덉㎏ 諛붿씠留?異쒗뭹 ?먮룞?낅젰 ?쒖옉 ---")
        print(f"  ?곹뭹紐? {row_data['product_name_kr']}")
        print(f"  釉뚮옖?? {row_data['brand']}")
        print(f"  諛붿씠留??먮ℓ媛: {row_data['buyma_price']}")

        # ---- ?ㅻ쾭?덉씠 ?쒓굅 ----
        _dismiss_overlay(driver)

        # ---- ???????????----
        try:
            cat1, cat2, cat3 = _infer_buyma_category(
                row_data.get('product_name_kr', ''),
                row_data.get('product_name_en', ''),
                row_data.get('brand', ''),
                row_data.get('musinsa_category_large', ''),
            )
            if cat1 and cat2:
                print(f"  移댄뀒怨좊━ 異붾줎: {cat1} > {cat2} > {cat3}")
                # ?移댄뀒怨좊━ ???
                if _select_category_by_arrow(driver, 0, cat1):
                    print(f"  ?移댄뀒: {cat1}")
                    # 以묒뭅?뚭퀬由??좏깮
                    if cat2 and _find_best_option_by_arrow(driver, 1, cat2):
                        # ?뚯뭅?뚭퀬由??좏깮 ?뺤씤
                        sel_val = driver.execute_script("""
                            var items = document.querySelectorAll('.sell-category__item');
                            if (items.length < 2) return '';
                            var v = items[1].querySelector('.Select-value-label');
                            return v ? v.textContent.trim() : '';
                        """)
                        if '?앫겗餓? in sel_val and sel_val != cat2:
                            print(f"  ??以묒뭅?? {cat2} -> ?앫겗餓?(湲고?)")
                        else:
                            print(f"  ??以묒뭅?? {sel_val or cat2}")
                        # ?뚯뭅?뚭퀬由??좏깮
                        if cat3:
                            items_count = len(driver.find_elements(By.CSS_SELECTOR, '.sell-category__item'))
                            if items_count >= 3:
                                if _find_best_option_by_arrow(driver, 2, cat3):
                                    sel_val3 = driver.execute_script("""
                                        var items = document.querySelectorAll('.sell-category__item');
                                        if (items.length < 3) return '';
                                        var v = items[2].querySelector('.Select-value-label');
                                        return v ? v.textContent.trim() : '';
                                    """)
                                    if '?앫겗餓? in (sel_val3 or '') and sel_val3 != cat3:
                                        print(f"  ???뚯뭅?? {cat3} -> ?앫겗餓?(湲고?)")
                                    else:
                                        print(f"  ???뚯뭅?? {sel_val3 or cat3}")
                                else:
                                    print(f"  ???뚯뭅??'{cat3}' 誘몃컻寃? ?앫겗餓뽯룄 ?놁쓬")
                    else:
                        print(f"  ??以묒뭅??'{cat2}' 誘몃컻寃? ?앫겗餓뽯룄 ?놁쓬")
                else:
                    print(f"  ???移댄뀒 '{cat1}' 誘몃컻寃? ?먮룞 ?좏깮 ?꾩슂")
            else:
                print(f"  ??移댄뀒怨좊━ 異붾줎 遺덇?, ?먮룞 ?좏깮 ?꾩슂")
        except Exception as e:
            print(f"  ??移댄뀒怨좊━ ?좏깮 ?ㅽ뙣: {e}")

        # ---- ?곹뭹紐??낅젰: "[Brand] ProductNameEN ColorEN" ----
        brand_en = row_data.get('brand_en', '') or row_data.get('brand', '')
        name_en = row_data.get('product_name_en') or row_data['product_name_kr']
        color_en = row_data.get('color_en') or row_data.get('color_kr', '')
        color_en = _expand_color_abbreviations(color_en)
        if color_en.lower() == 'none':
            color_en = ''
        try:
            # 泥ル쾲吏?bmm-c-field ?섏쐞 text input???곹뭹紐??낅젰
            name_fields = driver.find_elements(By.CSS_SELECTOR,
                ".bmm-c-field__input > input.bmm-c-text-field"
            )
            if name_fields:
                maxlength_raw = (name_fields[0].get_attribute('maxlength') or '').strip()
                title_limit = int(maxlength_raw) if maxlength_raw.isdigit() else 0
                product_title = _build_buyma_product_title(brand_en, name_en, color_en, title_limit)
                name_fields[0].clear()
                name_fields[0].send_keys(product_title)
                print(f"  ???곹뭹紐??낅젰: {product_title}")
                title_issue = _detect_title_input_issue(name_fields[0], product_title)
                if title_issue:
                    print(f"  ! ?곹뭹紐??섎룞 ?뺤씤 ?꾩슂: {title_issue}")
                    return "manual_review"
            else:
                print(f"  ???곹뭹紐??낅젰???李얠쓣 ???놁뒿?덈떎")
        except Exception as e:
            print(f"  ???곹뭹紐??낅젰 ?ㅽ뙣: {e}")
            return "manual_review"

        # ---- 釉뚮옖???낅젰 (?곸뼱) ----
        brand = row_data.get('brand_en', '') or row_data.get('brand', '')
        if brand:
            try:
                brand_input = driver.find_element(By.CSS_SELECTOR,
                    "input[placeholder*='?뽧꺀?녈깋?띲굮?ε뒟']"
                )
                _scroll_and_click(driver, brand_input)
                brand_input.clear()
                brand_input.send_keys(brand)
                _sleep(1.2)
                # 異붿쿇 紐⑸줉???꾩뿭 ul怨??욎씠??寃쎌슦媛 ?덉뼱 ?낅젰李?湲곗? ?ㅻ낫???좏깮???곗꽑 ?ъ슜
                brand_input.send_keys(Keys.ARROW_DOWN)
                _sleep(0.2)
                brand_input.send_keys(Keys.ENTER)
                print(f"  ??釉뚮옖???낅젰/?좏깮: {brand}")
            except Exception as e:
                print(f"  ??釉뚮옖???낅젰 ?ㅽ뙣: {e}")

        # ---- ?됱긽: React Select?먯꽌 ?됱긽 ?좏깮 + ?띿뒪???낅젰 ----
        color = row_data.get('color_en') or row_data.get('color_kr', '')
        color = _expand_color_abbreviations(color)
        color_en_input = _expand_color_abbreviations((row_data.get('color_en') or '').strip())
        if color and color.lower() != 'none':
            try:
                color_values = _split_color_values(color_en_input or color)
                if not color_values:
                    color_values = [color]
                color_for_system = color_values[0]
                color_system = _infer_color_system(color_for_system)
                picked = _select_color_system(driver, color_system, row_index=0)

                # 蹂듭닔 ?됱긽??寃쎌슦 異붽? ?됱뿉 怨꾪넻 ?좏깮 ?쒕룄
                if len(color_values) > 1:
                    for idx, cval in enumerate(color_values[1:], start=1):
                        if _try_add_color_row(driver):
                            _select_color_system(driver, _infer_color_system(cval), row_index=idx)

                # ?됱긽?낅젰移몄씠 怨꾪넻 ?좏깮怨??곕룞?섏뼱 ?쒖꽦?붾맆 ?뚮쭔 ?숈옉
                color_name_inputs = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".sell-color-table tbody tr td:nth-child(2) input.bmm-c-text-field, .sell-color-table input.bmm-c-text-field"
                )
                enabled_inputs = [
                    ci for ci in color_name_inputs
                    if ci.is_enabled() and ci.get_attribute('disabled') is None
                ]

                if enabled_inputs:
                    # ?됱긽媛믪쓣 媛곴컖 蹂꾨룄 移몄뿉 ?낅젰
                    for idx, cval in enumerate(color_values):
                        if idx >= len(enabled_inputs):
                            if _try_add_color_row(driver):
                                color_name_inputs = driver.find_elements(
                                    By.CSS_SELECTOR,
                                    ".sell-color-table tbody tr td:nth-child(2) input.bmm-c-text-field, .sell-color-table input.bmm-c-text-field"
                                )
                                enabled_inputs = [
                                    ci for ci in color_name_inputs
                                    if ci.is_enabled() and ci.get_attribute('disabled') is None
                                ]
                            else:
                                break
                        if idx >= len(enabled_inputs):
                            break

                        target_input = enabled_inputs[idx]
                        _scroll_and_click(driver, target_input)
                        target_input.clear()
                        target_input.send_keys(cval)
                        _sleep(0.2)

                    if picked:
                        print(f"  ???됱긽 ?낅젰(媛쒕퀎): {', '.join(color_values)}")
                    else:
                        print(f"  ???됱긽怨꾪넻 誘몄꽑?? ?됱긽留?媛쒕퀎 ?낅젰: {', '.join(color_values)}")
                else:
                    forced = False
                    if color_name_inputs and color_values:
                        try:
                            # 鍮꾪솢??移몃룄 ?덉슜 踰붿쐞?먯꽌 ?됱긽蹂꾨줈 遺꾨━ ?낅젰 ?쒕룄
                            forced_count = 0
                            for idx, cval in enumerate(color_values):
                                if idx >= len(color_name_inputs):
                                    break
                                ok = driver.execute_script(
                                    "var el=arguments[0], val=arguments[1];"
                                    "el.removeAttribute('disabled');"
                                    "var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                                    "setter.call(el, val);"
                                    "el.dispatchEvent(new Event('input',{bubbles:true}));"
                                    "el.dispatchEvent(new Event('change',{bubbles:true}));"
                                    "return (el.value===val);",
                                    color_name_inputs[idx], cval
                                )
                                if ok:
                                    forced_count += 1
                            forced = forced_count > 0
                        except Exception:
                            forced = False

                    if picked and forced:
                        print(f"  ???됱긽 ?낅젰(JS媛뺤젣/媛쒕퀎): {', '.join(color_values)}")
                    elif picked:
                        if _fill_color_supplement(driver, ', '.join(color_values)):
                            print(f"  ???됱긽怨꾪넻 ?좏깮 + 蹂댁땐?뺣낫 ?낅젰: {color_system} / {', '.join(color_values)}")
                        else:
                            print(f"  ???됱긽怨꾪넻 ?좏깮: {color_system} (?됱긽?낅젰? 鍮꾪솢??")
                    else:
                        print(f"  ???됱긽 ?낅젰 ?ㅽ뙣(怨꾪넻/?됱긽), ?섎룞 ?좏깮 ?꾩슂: {color}")
            except Exception as e:
                print(f"  ???됱긽 ?낅젰 ?ㅽ뙣: {e}")

        # ---- ?ъ씠利?而⑦뀒?대꼫 ?대┃ 諛?泥댄겕諛뺤뒪 ?좏깮 ----
        # 二쇱쓽: 移댄뀒怨좊━ 誘몄꽑?????ъ씠利덈ぉ濡앹씠 ?쒖떆?섏? ?딆쓬
        size_text = row_data.get('size', '')
        actual_size_text = _normalize_actual_size_for_upload(row_data.get('actual_size', ''))
        try:
            is_free_size = _is_free_size_text(size_text)

            # '?ъ씠利? ???대┃
            size_tabs = driver.find_elements(By.CSS_SELECTOR, ".sell-variation__tab-item")
            handled_size = False

            # ?ъ씠利?紐⑸줉 ???뺣낫 異쒕젰
            all_tab_texts = [(tab.text or '').strip() for tab in size_tabs]
            all_tab_ids = [(tab.get_attribute('aria-controls') or '').strip() for tab in size_tabs]
            print(f"  [??퀎 ?ъ씠利덈ぉ濡? {list(zip(all_tab_texts, all_tab_ids))}")

            for tab_idx, tab in enumerate(size_tabs):
                tab_text = (tab.text or '').strip()
                tab_panel_id = (tab.get_attribute('aria-controls') or '').strip()
                is_color_tab = ('?ャ꺀?? in tab_text or 'COLOR' in tab_text.upper()
                                or 'color' in tab_panel_id.lower())
                is_size_tab = (
                    '?듐궎?? in tab_text or 'SIZE' in tab_text.upper()
                    or tab_panel_id.endswith('-3')
                    or tab_panel_id.endswith('-size')
                    or (not is_color_tab and tab_idx > 0)
                )
                if not is_size_tab:
                    continue
                print(f"  [?? ?ъ씠利덊꺆 ?대┃: '{tab_text}' (aria-controls={tab_panel_id})")
                driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", tab)
                driver.execute_script("window.scrollBy(0, -180);")
                _scroll_and_click(driver, tab)
                # ?ъ씠利덊뙣?먯씠 ?뚮뜑留곷맆 ?뚭퉴吏 理쒕? 8珥??湲?
                for _ in range(16):
                    v_labels = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                    v_selects = driver.find_elements(By.CSS_SELECTOR, ".sell-variation .Select")
                    v_inputs = [
                        i for i in driver.find_elements(
                            By.CSS_SELECTOR,
                            ".sell-variation input[type='text'], .sell-variation input.bmm-c-text-field"
                        ) if i.is_displayed()
                    ]
                    v_table = driver.find_elements(By.CSS_SELECTOR, ".sell-size-table")
                    # ?ъ씠利늈I 濡쒕뱶??寃껋쑝濡??먮떒
                    if len(v_labels) > 0 or len(v_selects) > 1 or len(v_inputs) > 1 or v_table:
                        break
                    _sleep(0.5)

                panel = None
                if tab_panel_id:
                    try:
                        panel = driver.find_element(By.ID, tab_panel_id)
                    except Exception:
                        panel = None
                if panel is None:
                    panel = driver.find_element(By.CSS_SELECTOR, ".sell-variation")

                panel_html = panel.text.strip()
                if '?ャ깇?담꺁?믧겦?? in panel_html:
                    print(f"  ??移댄뀒怨좊━ 誘몄꽑?앹쑝濡??ъ씠利덈ぉ濡??놁쓬. 移댄뀒怨좊━ ?좏깮 ???먮룞 ?좏깮 ?꾩슂: {size_text}")
                else:
                    # ?ㅼ젣 ?ъ씠利덈씪踰?泥댄겕諛뺤뒪 ?뚮뜑留곷맆 ?뚭퉴吏 理쒕? 5珥?異붽? ?湲?
                    for _ in range(10):
                        if panel.find_elements(By.CSS_SELECTOR, "label, input[type='checkbox']"):
                            break
                        _sleep(0.5)
                    if is_free_size:
                        # ?꾨━?ъ씠利덈뒗 ?쇰컲 ?ъ씠利덈ℓ移?寃쎈줈?먯꽌 紐살갼?쇰㈃ 媛뺤젣 遺꾧린
                        no_var_ok = _force_select_shitei_nashi_global(driver) or _check_no_variation_option(driver, prefer_shitei_nashi=True)
                        ref_ok = _force_reference_size_shitei_nashi(driver, panel=panel)
                        if no_var_ok or ref_ok:
                            print(f"  ???꾨━?ъ씠利?媛먯?, ?뉐츣?ゃ걮 ?좏깮 ({size_text})")
                            if actual_size_text:
                                detail_filled = _fill_size_edit_details(driver, panel, actual_size_text, max_rows=1)
                                if detail_filled:
                                    print(f"  ???ъ씠利?渶③썓 ?곸꽭?낅젰: {detail_filled}媛?)
                                else:
                                    print(f"  ???ъ씠利?渶③썓 ?곸꽭?낅젰 ?ㅽ뙣(?섎룞 ?뺤씤 ?꾩슂)")
                        else:
                            print(f"  ???꾨━?ъ씠利?媛먯?, ?뉐츣?ゃ걮 ?좏깮 ?ㅽ뙣. ?먮룞 ?좏깮 ?꾩슂: {size_text}")
                        handled_size = True
                        break

                    # 0) ?뚯씠釉?湲곕컲 ?ъ씠利??쇨큵 ?낅젰 寃쎈줈 ?곗꽑
                    table_filled = _fill_size_table_rows(driver, panel, size_text)
                    if table_filled:
                        print(f"  ???ъ씠利덉엯???뚯씠釉?: {table_filled}媛?{size_text})")
                        if actual_size_text:
                            detail_filled = _fill_size_edit_details(driver, panel, actual_size_text, max_rows=table_filled)
                            if detail_filled:
                                print(f"  ???ъ씠利?渶③썓 ?곸꽭?낅젰: {detail_filled}媛?)
                            else:
                                print(f"  ???ъ씠利?渶③썓 ?곸꽭?낅젰 ?ㅽ뙣(?섎룞 ?뺤씤 ?꾩슂)")
                        handled_size = True
                        break

                    # 1) ?됱긽/?쇰낯?ъ씠利?React Select 湲곕컲 ?ъ씠利??좏깮 ?곗꽑 ?쒕룄
                    select_matched = _select_size_by_select_controls(driver, panel, size_text)
                    if select_matched:
                        print(f"  ???ъ씠利덉꽑??Select): {select_matched}媛?{size_text})")
                        handled_size = True
                        break

                    items = panel.find_elements(By.CSS_SELECTOR, "label")
                    if not items:
                        items = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                    avail = [it.text.strip() for it in items if it.text.strip()]

                    matched = 0
                    if size_text:
                        sizes = [s.strip() for s in size_text.split(',') if s.strip()]
                        for sz in sizes:
                            sz_variants = _build_size_variants(sz)
                            for item in items:
                                item_text = item.text.strip()
                                if any(
                                    _size_match(v, item_text)
                                    for v in sz_variants
                                    ):
                                        _scroll_and_click(driver, item)
                                        matched += 1
                                        driver.get(BUYMA_SELL_URL)
                                        break

                        if matched:
                            print(f"  ???ъ씠利덉꽑?? {matched}媛?{size_text})")
                        else:
                            if not avail:
                                # 癒쇱? '?ъ씠利? UI 媛뺤젣移섑솚 ?쒕룄
                                expanded = _enable_size_selection_ui(driver)
                                if expanded:
                                    items2 = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                                    avail2 = [it.text.strip() for it in items2 if it.text.strip()][:10]
                                    matched2 = 0
                                    if size_text and items2:
                                        sizes2 = [s.strip() for s in size_text.split(',') if s.strip()]
                                        for sz2 in sizes2:
                                            sz_variants2 = _build_size_variants(sz2)
                                            for item2 in items2:
                                                item_text2 = item2.text.strip()
                                                if any(
                                                    _size_match(v, item_text2)
                                                    for v in sz_variants2
                                                ):
                                                    _scroll_and_click(driver, item2)
                                                    matched2 += 1
                                                    _sleep(0.2)
                                                    break
                                    if matched2:
                                        print(f"  ???ъ씠利덉꽑?? {matched2}媛?{size_text})")
                                        handled_size = True
                                        break

                                if is_free_size:
                                    if _force_select_shitei_nashi_global(driver) or _force_reference_size_shitei_nashi(driver):
                                        print(f"  ???꾨━?ъ씠利?媛먯?, ?뉐츣?ゃ걮 ?좏깮 ({size_text})")
                                    else:
                                        print(f"  ???꾨━?ъ씠利?媛먯?, ?좏깮?놁쓬/?ㅽ뙣: {size_text}")
                                else:
                                    if _check_no_variation_option(driver):
                                        print(f"  ???ъ씠利덉샃???놁쓬, 泥댄겕諛뺤뒪留?泥댄겕")
                                    elif size_text and _fill_size_text_inputs(driver, size_text) > 0:
                                        print(f"  ???ъ씠利덊뀓?ㅽ듃?낅젰: {size_text}")
                                    elif size_text and _fill_size_supplement(driver, size_text):
                                        print(f"  ???ъ씠利덉샃???놁쓬, 蹂댁땐?뺣낫 ?낅젰: {size_text}")
                                    else:
                                        print(f"  ???ъ씠利덉샃???놁쓬(蹂댁땐?뺣낫 泥섎━ ?ㅽ뙣): {size_text}")
                            else:
                                if size_text:
                                    print(f"  ???ъ씠利덈ℓ移??ㅽ뙣 (?듭뀡 ?꾩껜: {avail}), ?먮룞 ?좏깮 ?꾩슂: {size_text}")
                                else:
                                    print(f"  ???ъ씠利덉샃?섏뾾??(?듭뀡: {avail})")
                    handled_size = True
                    break

            if not handled_size:
                if is_free_size:
                    no_var_ok = _force_select_shitei_nashi_global(driver) or _check_no_variation_option(driver, prefer_shitei_nashi=True)
                    ref_ok = _force_reference_size_shitei_nashi(driver)
                    if no_var_ok or ref_ok:
                        print(f"  ???꾨━?ъ씠利?媛먯?, ?뉐츣?ゃ걮 ?좏깮 ({size_text})")
                        if actual_size_text:
                            try:
                                panel_for_edit = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
                            except Exception:
                                panel_for_edit = None
                            if panel_for_edit is not None:
                                detail_filled = _fill_size_edit_details(driver, panel_for_edit, actual_size_text, max_rows=1)
                                if detail_filled:
                                    print(f"  ???ъ씠利?渶③썓 ?곸꽭?낅젰: {detail_filled}媛?)
                                else:
                                    print(f"  ???ъ씠利?渶③썓 ?곸꽭?낅젰 ?ㅽ뙣(?섎룞 ?뺤씤 ?꾩슂)")
                    else:
                        print(f"  ???꾨━?ъ씠利?媛먯?, ?뉐츣?ゃ걮 ?좏깮 ?ㅽ뙣. ?먮룞 ?좏깮 ?꾩슂: {size_text}")
                    handled_size = True

            if not handled_size:
                # ?꾩쓽 ?ㅽ뙣 ?꾩뿉 Select 而⑦듃濡ㅼ뿉???ъ씠利??좏깮 癒쇱? ?쒕룄
                select_matched = _select_size_by_select_controls(
                    driver,
                    driver.find_element(By.CSS_SELECTOR, ".sell-variation"),
                    size_text
                )
                if select_matched:
                    print(f"  ???ъ씠利덉꽑??Select): {select_matched}媛?{size_text})")
                    handled_size = True

            if not handled_size:
                items = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                avail = [it.text.strip() for it in items if it.text.strip()][:10]
                matched = 0
                if size_text:
                    sizes = [s.strip() for s in size_text.split(',') if s.strip()]
                    for sz in sizes:
                        sz_variants = _build_size_variants(sz)
                        for item in items:
                            item_text = item.text.strip()
                            if any(
                                _size_match(v, item_text)
                                for v in sz_variants
                            ):
                                _scroll_and_click(driver, item)
                                matched += 1
                                _sleep(0.2)
                                break
                if matched:
                    print(f"  ???ъ씠利덉꽑?? {matched}媛?{size_text})")
                elif not avail:
                    if _enable_size_selection_ui(driver):
                        items2 = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                        matched2 = 0
                        if size_text and items2:
                            sizes2 = [s.strip() for s in size_text.split(',') if s.strip()]
                            for sz2 in sizes2:
                                sz_variants2 = _build_size_variants(sz2)
                                for item2 in items2:
                                    item_text2 = item2.text.strip()
                                    if any(
                                        _size_match(v, item_text2)
                                        for v in sz_variants2
                                    ):
                                        _scroll_and_click(driver, item2)
                                        matched2 += 1
                                        _sleep(0.2)
                                        break
                        if matched2:
                            print(f"  ???ъ씠利덉꽑?? {matched2}媛?{size_text})")
                        elif is_free_size and (_force_select_shitei_nashi_global(driver) or _force_reference_size_shitei_nashi(driver)):
                            print(f"  ???꾨━?ъ씠利?媛먯?, ?뉐츣?ゃ걮 ?좏깮 ({size_text})")
                        elif _check_no_variation_option(driver):
                            print(f"  ???ъ씠利덉샃???놁쓬, 泥댄겕諛뺤뒪留?泥댄겕")
                        elif (not is_free_size) and size_text and _fill_size_text_inputs(driver, size_text) > 0:
                            print(f"  ???ъ씠利덊뀓?ㅽ듃?낅젰: {size_text}")
                        elif (not is_free_size) and size_text and _fill_size_supplement(driver, size_text):
                            print(f"  ???ъ씠利덉샃???놁쓬, 蹂댁땐?뺣낫 ?낅젰: {size_text}")
                        else:
                            print(f"  ???ъ씠利덉샃???좏깮 誘명깘: {size_text}")
                    elif is_free_size and (_force_select_shitei_nashi_global(driver) or _force_reference_size_shitei_nashi(driver)):
                        print(f"  ???꾨━?ъ씠利?媛먯?, ?뉐츣?ゃ걮 ?좏깮 ({size_text})")
                    elif _check_no_variation_option(driver):
                        print(f"  ???ъ씠利덉샃???놁쓬, 泥댄겕諛뺤뒪留?泥댄겕")
                    elif (not is_free_size) and size_text and _fill_size_text_inputs(driver, size_text) > 0:
                        print(f"  ???ъ씠利덊뀓?ㅽ듃?낅젰: {size_text}")
                    elif (not is_free_size) and size_text and _fill_size_supplement(driver, size_text):
                        print(f"  ???ъ씠利덉샃???놁쓬, 蹂댁땐?뺣낫 ?낅젰: {size_text}")
                    else:
                        print(f"  ???ъ씠利덉샃???좏깮 誘명깘: {size_text}")
                else:
                    if size_text:
                        print(f"  ???ъ씠利덈ℓ移??ㅽ뙣 (?듭뀡: {avail}), ?먮룞 ?좏깮 ?꾩슂: {size_text}")
                    else:
                        print(f"  ???ъ씠利덉샃?섏뾾??(?듭뀡: {avail})")
        except Exception as e:
            print(f"  ???ъ씠利덉꽑???ㅽ뙣: {e}")

        # ---- 援ъ엯湲고븳: react-datepicker (.sell-term) +89??理쒕? ?ㅼ젙 媛??湲곌컙) ----
        try:
            deadline_date = datetime.now() + timedelta(days=89)
            deadline_str = deadline_date.strftime('%Y/%m/%d')
            deadline_input = driver.find_element(By.CSS_SELECTOR, "input.sell-term")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", deadline_input)
            _sleep(0.3)
            # react-datepicker??JS濡??ㅼ젙
            driver.execute_script(
                "var el = arguments[0]; "
                "var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; "
                "nativeInputValueSetter.call(el, arguments[1]); "
                "el.dispatchEvent(new Event('input', { bubbles: true })); "
                "el.dispatchEvent(new Event('change', { bubbles: true }));",
                deadline_input, deadline_str
            )
            _sleep(0.5)
            print(f"  ??援ъ엯湲고븳 ?낅젰: {deadline_str}")
        except Exception as e:
            print(f"  ??援ъ엯湲고븳 ?낅젰 ?ㅽ뙣, ?섎룞 ?낅젰 ?꾩슂: {e}")

        # ---- ????紐??????: ???????恙낂젅) textarea ----
        try:
            target_comment = driver.execute_script("""
                function isProductCommentField(field) {
                    if (!field) return false;
                    var label = field.querySelector('.bmm-c-field__label, label, p');
                    var txt = label ? (label.textContent || '').replace(/\\s+/g, ' ').trim() : '';
                    return txt.indexOf('???????) >= 0;
                }

                // 1) ?곹뭹肄붾찘???쇰꺼??遺숈? ?꾨뱶??textarea瑜?理쒖슦???ъ슜
                var fields = document.querySelectorAll('.bmm-c-field');
                for (var i = 0; i < fields.length; i++) {
                    if (isProductCommentField(fields[i])) {
                        var ta = fields[i].querySelector('textarea.bmm-c-textarea');
                        if (ta && !ta.closest('.sell-variation')) return ta;
                    }
                }

                // 2) ?꾨옒履?議곌툑 ?대젮媛???곹뭹肄붾찘??鍮꾩듂???꾨뱶?먯꽌 ?먯깋
                var allFields = document.querySelectorAll('.bmm-c-field');
                for (var j = 0; j < allFields.length; j++) {
                    if (allFields[j].closest('.sell-variation')) continue;
                    var label2 = allFields[j].querySelector('.bmm-c-field__label, label, p');
                    var txt2 = label2 ? (label2.textContent || '').trim() : '';
                    if (txt2.indexOf('???????) >= 0) {
                        var ta2 = allFields[j].querySelector('textarea.bmm-c-textarea, textarea');
                        if (ta2) return ta2;
                    }
                }

                // 3) ?踰?for ???湲곕컲 ?寃?textarea ???
                var labels = document.querySelectorAll('label[for], .bmm-c-field__label[for]');
                for (var k = 0; k < labels.length; k++) {
                    var lt = (labels[k].textContent || '').trim();
                    if (lt.indexOf('?녶뱚?녈깳?녈깉') < 0) continue;
                    var forId = labels[k].getAttribute('for') || '';
                    if (!forId) continue;
                    var ta3 = document.getElementById(forId);
                    if (ta3 && ta3.tagName === 'TEXTAREA') return ta3;
                }

                // 4) ?띿뒪???몃뱶 洹쇱젒 ?먯깋: '?녶뱚?녈깳?녈깉' 臾멸뎄 二쇰? 議곗긽?먯꽌 textarea 異붿쟻
                var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
                var node;
                while ((node = walker.nextNode())) {
                    var t = (node.nodeValue || '').replace(/\\s+/g, ' ').trim();
                    if (!t || t.indexOf('?녶뱚?녈깳?녈깉') < 0) continue;
                    var cur = node.parentElement;
                    for (var depth = 0; cur && depth < 8; depth++) {
                        if (!cur.closest('.sell-variation')) {
                            var ta4 = cur.querySelector('textarea.bmm-c-textarea, textarea');
                            if (ta4) return ta4;
                        }
                        cur = cur.parentElement;
                    }
                }

                return null;
            """)

            if target_comment:
                _scroll_and_click(driver, target_comment)
                wrote = driver.execute_script(
                    "var el=arguments[0], val=arguments[1];"
                    "if (!el || typeof el.removeAttribute !== 'function') return false;"
                    "el.removeAttribute('disabled');"
                    "el.removeAttribute('readonly');"
                    "var setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
                    "setter.call(el, val);"
                    "el.dispatchEvent(new Event('input',{bubbles:true}));"
                    "el.dispatchEvent(new Event('change',{bubbles:true}));"
                    "el.dispatchEvent(new Event('blur',{bubbles:true}));"
                    "return (el.value || '').trim().length >= Math.min(20, (val || '').trim().length);",
                    target_comment, BUYMA_COMMENT_TEMPLATE
                )
                if wrote:
                    print(f"  ???곹뭹肄붾찘??恙낂젅) ?낅젰 (怨좎젙 ?쒗뵆由?")
                else:
                    print(f"  ???곹뭹肄붾찘???낅젰 ?쒕룄?덉쑝???뺤씤 ?ㅽ뙣")
            else:
                print(f"  ???녶뱚?녈깳?녈깉 ?꾨뱶瑜?李얠? 紐삵뻽?듬땲?? ?섎룞 ?낅젰 ?꾩슂")
        except Exception as e:
            print(f"  ???곹뭹 ?ㅻ챸 ?낅젰 ?ㅽ뙣: {e}")

        # ---- 諛곗넚諛⑸쾿: OCS 泥댄겕諛뺤뒪 泥댄겕 ----
        try:
            ocs_checked = driver.execute_script("""
                // OCS 諛곗넚???ы븿?섎뒗 tr?먯꽌 泥댄겕諛뺤뒪瑜?李얠븘 泥댄겕?쒕떎
                var rows = document.querySelectorAll('.bmm-c-form-table__table tbody tr');
                for (var i = 0; i < rows.length; i++) {
                    if (rows[i].textContent.indexOf('OCS') >= 0) {
                        var cb = rows[i].querySelector('input[type="checkbox"]');
                        if (cb && !cb.checked) {
                            cb.click();
                            return 'clicked';
                        } else if (cb && cb.checked) {
                            return 'already';
                        }
                    }
                }
                return 'not_found';
            """)
            if ocs_checked == 'clicked':
                print(f"  ??諛곗넚諛⑸쾿 OCS 泥댄겕")
            elif ocs_checked == 'already':
                print(f"  ??諛곗넚諛⑸쾿 OCS ?대? 泥댄겕??)
            else:
                print(f"  ??OCS 泥댄겕諛뺤뒪瑜?李얠? 紐삵뻽?듬땲?? ?섎룞 ?좏깮 ?꾩슂")
        except Exception as e:
            print(f"  ??諛곗넚諛⑸쾿 ?좏깮 ?ㅽ뙣: {e}")

        # ---- 媛寃??낅젰: half-size-char ?꾨뱶 (M??媛? ----
        buyma_price = re.sub(r'[^\d]', '', row_data.get('buyma_price', ''))
        if buyma_price:
            try:
                adjusted_price = max(0, int(buyma_price) - 10)
                filled_count = 0

                # '?녶뱚堊→졏' ?쇰꺼???곌껐???낅젰 ?꾨뱶留??낅젰 (?섎웾 ?꾨뱶 ?ㅼ뿼 諛⑹?)
                product_price_input = driver.execute_script("""
                    function findInputFromField(field) {
                        if (!field) return null;
                        var candidates = field.querySelectorAll('input.bmm-c-text-field, input[type="text"], input[type="number"]');
                        for (var k = 0; k < candidates.length; k++) {
                            var c = candidates[k];
                            var meta = ((c.getAttribute('name') || '') + ' ' + (c.getAttribute('id') || '') + ' ' + (c.getAttribute('placeholder') || '') + ' ' + (c.getAttribute('class') || '')).toLowerCase();
                            // ?섎웾/?ш퀬 ?낅젰移몄? ?쒖쇅
                            if (meta.indexOf('?곈뇧') >= 0 || meta.indexOf('qty') >= 0 || meta.indexOf('stock') >= 0 || meta.indexOf('?ⓨ벴') >= 0) {
                                continue;
                            }
                            return c;
                        }
                        return null;
                    }

                    function normText(t) {
                        return (t || '').replace(/\s+/g, ' ').trim();
                    }

                    // 1) bmm-c-field 湲곕컲 ?먯깋
                    var fields = document.querySelectorAll('.bmm-c-field, .bmm-c-form-table__body tr, .bmm-c-form-table tr');
                    for (var i = 0; i < fields.length; i++) {
                        var root = fields[i];
                        var txt = normText(root.textContent || '');
                        var hasPriceKeyword = (txt.indexOf('?녶뱚堊→졏') >= 0 || txt.indexOf('縕⒴２堊→졏') >= 0 || txt.indexOf('堊→졏') >= 0);
                        var hasQtyKeyword = (txt.indexOf('縕룝퍡?㎯걤?뗥릦鼇덃빊??) >= 0 || txt.indexOf('?덅쮫?곈뇧') >= 0 || txt.indexOf('?곈뇧') >= 0 || txt.indexOf('?ⓨ벴') >= 0);
                        if (hasPriceKeyword && !hasQtyKeyword) {
                            var ipt = findInputFromField(fields[i]);
                            if (ipt) return ipt;
                        }
                    }

                    // 2) ?쇰꺼 for ?띿꽦 湲곕컲 fallback
                    var labels = document.querySelectorAll('label[for], .bmm-c-field__label[for]');
                    for (var j = 0; j < labels.length; j++) {
                        var lt = normText(labels[j].textContent || '');
                        var isPrice = (lt.indexOf('?녶뱚堊→졏') >= 0 || lt.indexOf('縕⒴２堊→졏') >= 0 || lt.indexOf('堊→졏') >= 0);
                        var isQty = (lt.indexOf('縕룝퍡?㎯걤?뗥릦鼇덃빊??) >= 0 || lt.indexOf('?덅쮫?곈뇧') >= 0 || lt.indexOf('?곈뇧') >= 0 || lt.indexOf('?ⓨ벴') >= 0);
                        if (!isPrice || isQty) continue;
                        var idv = labels[j].getAttribute('for') || '';
                        if (!idv) continue;
                        var ipt2 = document.getElementById(idv);
                        if (ipt2 && ipt2.tagName === 'INPUT') return ipt2;
                    }

                    // 3) input 硫뷀? 湲곕컲 fallback (媛寃??ㅼ썙???ы븿 + ?섎웾/?ш퀬 ?ㅼ썙???쒖쇅)
                    var allInputs = document.querySelectorAll('input.bmm-c-text-field, input[type="text"], input[type="number"]');
                    for (var m = 0; m < allInputs.length; m++) {
                        var ii = allInputs[m];
                        var mm = ((ii.getAttribute('name') || '') + ' ' + (ii.getAttribute('id') || '') + ' ' + (ii.getAttribute('placeholder') || '') + ' ' + (ii.getAttribute('class') || '')).toLowerCase();
                        var mmPrice = (mm.indexOf('?녶뱚堊→졏') >= 0 || mm.indexOf('縕⒴２堊→졏') >= 0 || mm.indexOf('price') >= 0 || mm.indexOf('堊→졏') >= 0);
                        var mmQty = (mm.indexOf('qty') >= 0 || mm.indexOf('quantity') >= 0 || mm.indexOf('?곈뇧') >= 0 || mm.indexOf('stock') >= 0 || mm.indexOf('?ⓨ벴') >= 0);
                        if (mmPrice && !mmQty) return ii;
                    }
                    return null;
                """)

                if product_price_input is not None:
                    try:
                        _scroll_and_click(driver, product_price_input)
                        product_price_input.clear()
                        product_price_input.send_keys(str(adjusted_price))
                        filled_count += 1
                    except Exception:
                        pass

                # fallback: placeholder 湲곕컲 媛寃??꾨뱶 寃??
                if filled_count == 0:
                    try:
                        price_by_placeholder = driver.find_element(
                            By.CSS_SELECTOR,
                            "input[placeholder*='?녶뱚堊→졏'], input[placeholder*='縕⒴２堊→졏'], input[placeholder*='堊→졏']"
                        )
                        if price_by_placeholder.is_displayed() and price_by_placeholder.is_enabled():
                            _scroll_and_click(driver, price_by_placeholder)
                            price_by_placeholder.clear()
                            price_by_placeholder.send_keys(str(adjusted_price))
                            filled_count += 1
                    except Exception:
                        pass

                if filled_count:
                    print(f"  ???먮ℓ媛 ?낅젰: 짜{adjusted_price} (?묒?媛?10)")
                else:
                    print(f"  ??媛寃??낅젰 ?꾨뱶瑜?李얠쓣 ???놁뒿?덈떎")
            except Exception as e:
                print(f"  ???먮ℓ媛 ?낅젰 ?ㅽ뙣: {e}")

        # ---- 縕룝퍡?㎯걤?뗥릦鼇덃빊???낅젰 (怨좎젙 100) ----
        try:
            qty_value = "100"
            qty_filled = False
            qty_candidates = []

            qty_input = driver.execute_script("""
                function isVisible(el) {
                    if (!el) return false;
                    const s = window.getComputedStyle(el);
                    return s && s.display !== 'none' && s.visibility !== 'hidden';
                }

                function nearestText(el) {
                    var cur = el;
                    for (var depth = 0; cur && depth < 6; depth++) {
                        var txt = (cur.textContent || '').replace(/\s+/g, ' ').trim();
                        if (txt) return txt;
                        cur = cur.parentElement;
                    }
                    return '';
                }

                function metaText(el) {
                    return [
                        el.getAttribute('placeholder') || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('name') || '',
                        el.getAttribute('id') || '',
                        el.getAttribute('class') || '',
                        el.getAttribute('inputmode') || '',
                        el.getAttribute('pattern') || ''
                    ].join(' ');
                }

                function hasQtyHint(text) {
                    return text.indexOf('縕룝퍡?㎯걤?뗥릦鼇덃빊??) >= 0 ||
                           text.indexOf('?덅쮫?곈뇧') >= 0 ||
                           text.indexOf('縕룝퍡??꺗?곈뇧') >= 0 ||
                           text.indexOf('蘊쇔뀯??꺗?곈뇧') >= 0 ||
                           text.indexOf('?곈뇧') >= 0 ||
                           text.indexOf('quantity') >= 0 ||
                           text.indexOf('qty') >= 0;
                }

                // 1) placeholder 吏곸젒 留ㅼ묶
                var byPlaceholder = document.querySelector("input[placeholder*='縕룝퍡?㎯걤?뗥릦鼇덃빊??], input[placeholder*='?덅쮫?곈뇧'], input[placeholder*='縕룝퍡??꺗?곈뇧'], input[placeholder*='蘊쇔뀯??꺗?곈뇧'], input[aria-label*='縕룝퍡?㎯걤?뗥릦鼇덃빊??], input[aria-label*='?덅쮫?곈뇧'], input[aria-label*='縕룝퍡??꺗?곈뇧'], input[aria-label*='蘊쇔뀯??꺗?곈뇧']");
                if (byPlaceholder && isVisible(byPlaceholder)) return byPlaceholder;

                // 2) ?쇰꺼 ?띿뒪??湲곕컲 留ㅼ묶
                var fields = document.querySelectorAll('.bmm-c-field, .bmm-c-form-table__body tr, .bmm-c-form-table tr');
                for (var i = 0; i < fields.length; i++) {
                    var root = fields[i];
                    var txt = (root.textContent || '').replace(/\s+/g, ' ').trim();
                    if (hasQtyHint(txt)) {
                        var ipt = root.querySelector("input.bmm-c-text-field, input[type='text'], input[type='number']");
                        if (ipt && isVisible(ipt)) return ipt;
                    }
                }

                var labels = document.querySelectorAll('label, .bmm-c-field__label, .bmm-c-form-table__header, .bmm-c-form-table__label');
                for (var i2 = 0; i2 < labels.length; i2++) {
                    var label = labels[i2];
                    var labelText = (label.textContent || '').replace(/\s+/g, ' ').trim();
                    if (!hasQtyHint(labelText)) continue;
                    var forId = label.getAttribute('for') || '';
                    if (forId) {
                        var direct = document.getElementById(forId);
                        if (direct && direct.tagName === 'INPUT' && isVisible(direct)) return direct;
                    }
                    var labelInput = label.querySelector("input.bmm-c-text-field, input[type='text'], input[type='number']");
                    if (labelInput && isVisible(labelInput)) return labelInput;
                    var parent = label.parentElement;
                    for (var up0 = 0; parent && up0 < 4; up0++) {
                        var parentInput = parent.querySelector("input.bmm-c-text-field, input[type='text'], input[type='number']");
                        if (parentInput && isVisible(parentInput)) return parentInput;
                        parent = parent.parentElement;
                    }
                }

                // 3) ?꾩껜 input???뚮ŉ 二쇰? ?띿뒪?멸? ?⑷퀎?섎웾??媛由ы궎?붿? ?뺤씤
                var allInputs = document.querySelectorAll("input.bmm-c-text-field, input[type='text'], input[type='number']");
                for (var j = 0; j < allInputs.length; j++) {
                    var ip = allInputs[j];
                    if (!isVisible(ip)) continue;
                    var meta = metaText(ip).toLowerCase();
                    if (meta.indexOf('price') >= 0 || meta.indexOf('?녶뱚堊→졏') >= 0 || meta.indexOf('縕⒴２堊→졏') >= 0) continue;
                    var around = nearestText(ip);
                    if (hasQtyHint(around.toLowerCase())) {
                        return ip;
                    }
                    if (hasQtyHint(meta)) {
                        return ip;
                    }
                }

                // 4) 留덉?留?fallback: ?쒖떆???レ옄 ?낅젰 以?媛寃??ш퀬 愿?⑥씠 ?꾨땶 ?꾨뱶
                for (var k = 0; k < allInputs.length; k++) {
                    var ip2 = allInputs[k];
                    if (!isVisible(ip2)) continue;
                    var meta2 = metaText(ip2).toLowerCase();
                    if (meta2.indexOf('price') >= 0 || meta2.indexOf('?녶뱚堊→졏') >= 0 || meta2.indexOf('縕⒴２堊→졏') >= 0) continue;
                    if (meta2.indexOf('stock') >= 0 || meta2.indexOf('?ⓨ벴') >= 0) continue;
                    if ((ip2.type || '').toLowerCase() === 'number' || (ip2.getAttribute('inputmode') || '').toLowerCase() === 'numeric' || hasQtyHint(meta2)) {
                        return ip2;
                    }
                }

                // 5) 媛寃??꾨뱶? 媛숈? ?뚯씠釉??뱀뀡???덈뒗 ?ㅼ쓬 ?レ옄 ?낅젰 fallback
                var priceInput = null;
                for (var p = 0; p < allInputs.length; p++) {
                    var cand = allInputs[p];
                    var metaP = metaText(cand);
                    var aroundP = nearestText(cand);
                    if (metaP.indexOf('?녶뱚堊→졏') >= 0 || metaP.indexOf('縕⒴２堊→졏') >= 0 || aroundP.indexOf('?녶뱚堊→졏') >= 0 || aroundP.indexOf('縕⒴２堊→졏') >= 0) {
                        priceInput = cand;
                        break;
                    }
                }
                if (priceInput) {
                    var container = priceInput.parentElement;
                    for (var up = 0; container && up < 5; up++) {
                        var nearby = container.querySelectorAll("input.bmm-c-text-field, input[type='text'], input[type='number']");
                        for (var q = 0; q < nearby.length; q++) {
                            var n = nearby[q];
                            if (n === priceInput || !isVisible(n)) continue;
                            var metaN = metaText(n).toLowerCase();
                            if (metaN.indexOf('stock') >= 0 || metaN.indexOf('?ⓨ벴') >= 0) continue;
                            return n;
                        }
                        container = container.parentElement;
                    }
                }

                return null;
            """)

            if qty_input is not None:
                try:
                    _scroll_and_click(driver, qty_input)
                    qty_input.clear()
                    qty_input.send_keys(qty_value)
                    qty_filled = True
                except Exception:
                    try:
                        ok = driver.execute_script(
                            "var el=arguments[0], val=arguments[1];"
                            "if(!el) return false;"
                            "el.removeAttribute('disabled');"
                            "var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                            "setter.call(el, val);"
                            "el.dispatchEvent(new Event('input',{bubbles:true}));"
                            "el.dispatchEvent(new Event('change',{bubbles:true}));"
                            "return el.value===val;",
                            qty_input,
                            qty_value,
                        )
                        qty_filled = bool(ok)
                    except Exception:
                        qty_filled = False

            if not qty_filled:
                qty_candidates = driver.execute_script("""
                    function isVisible(el) {
                        if (!el) return false;
                        const s = window.getComputedStyle(el);
                        return s && s.display !== 'none' && s.visibility !== 'hidden';
                    }
                    function nearestText(el) {
                        var cur = el;
                        for (var depth = 0; cur && depth < 5; depth++) {
                            var txt = (cur.textContent || '').replace(/\s+/g, ' ').trim();
                            if (txt) return txt;
                            cur = cur.parentElement;
                        }
                        return '';
                    }
                    var inputs = document.querySelectorAll("input.bmm-c-text-field, input[type='text'], input[type='number']");
                    var rows = [];
                    for (var i = 0; i < inputs.length; i++) {
                        var el = inputs[i];
                        if (!isVisible(el)) continue;
                        rows.push({
                            type: el.type || '',
                            name: el.getAttribute('name') || '',
                            id: el.getAttribute('id') || '',
                            placeholder: el.getAttribute('placeholder') || '',
                            aria: el.getAttribute('aria-label') || '',
                            inputmode: el.getAttribute('inputmode') || '',
                            cls: el.getAttribute('class') || '',
                            around: nearestText(el).slice(0, 180)
                        });
                    }
                    return rows;
                """)

            if qty_filled:
                print("  ??縕룝퍡?㎯걤?뗥릦鼇덃빊???낅젰: 100")
            else:
                print("  ??縕룝퍡?㎯걤?뗥릦鼇덃빊???낅젰移몄쓣 李얠? 紐삵뻽?듬땲?? ?섎룞 ?낅젰 ?꾩슂")
                if qty_candidates:
                    for idx, cand in enumerate(qty_candidates[:8], 1):
                        around = (cand.get('around') or '')[:120]
                        print(
                            f"    ?꾨낫 {idx}: type={cand.get('type','')} name={cand.get('name','')} id={cand.get('id','')} "
                            f"placeholder={cand.get('placeholder','')} aria={cand.get('aria','')} inputmode={cand.get('inputmode','')} around={around}"
                        )
        except Exception as e:
            print(f"  ???덅쮫?곈뇧 ?낅젰 ?ㅽ뙣: {e}")

        # ---- 援щℓ/諛쒖넚: 紐⑤뱺 ?꾩떆/援??濡?湲곕낯 ?ㅼ젙?섏뼱 ?덉쓬 ----
        # ?꾩떆(?쒖슱) Select ?좏깮: Select-value-label??"?멩뒢?ゃ걮"?대㈃ ?썬궑???좏깮
        try:
            selects = driver.find_elements(By.CSS_SELECTOR, ".Select")
            city_count = 0
            for sel_container in selects:
                try:
                    val_label = sel_container.find_element(By.CSS_SELECTOR, ".Select-value-label")
                    if '?멩뒢?ゃ걮' in val_label.text:
                        _scroll_and_click(driver, sel_container.find_element(By.CSS_SELECTOR, ".Select-control"))
                        _sleep(0.5)
                        opts = driver.find_elements(By.CSS_SELECTOR, ".Select-option")
                        for opt in opts:
                            if '?썬궑?? in opt.text:
                                opt.click()
                                city_count += 1
                                _sleep(0.3)
                                break
                except Exception:
                    continue
            if city_count:
                print(f"  ???꾩떆 ?좏깮: ?썬궑??{city_count}媛?")
        except Exception as e:
            print(f"  ???꾩떆 ?좏깮 ?ㅽ뙣, ?먮룞 ?좏깮 ?꾩슂: {e}")

        # ---- ?대?吏 ?낅줈??----
        image_files = resolve_image_files(row_data.get('image_paths', ''))
        if image_files:
            try:
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if file_inputs:
                    # 泥?踰덉㎏ file input??紐⑤뱺 ?대?吏 寃쎈줈瑜?以꾨컮轅덉쑝濡??꾨떖
                    file_input = file_inputs[0]
                    file_paths_str = "\n".join(image_files)
                    file_input.send_keys(file_paths_str)
                    print(f"  ???대?吏 ?낅줈?? {len(image_files)}??)
                    _sleep(2)
                else:
                    print(f"  ???뚯씪 ?낅줈???꾨뱶瑜?李얠쓣 ???놁뒿?덈떎")
            except Exception as e:
                print(f"  ???대?吏 ?낅줈???ㅽ뙣: {e}")
        else:
            print(f"  ???낅줈?쒗븷 ?대?吏媛 ?놁뒿?덈떎")

        return "success"

    except Exception as e:
        print(f"  ???대?吏 ?낅줈???ㅻ쪟: {e}")
        return "error"


def upload_products(specific_row: int = 0, upload_mode: str = 'auto', max_items: int = 0):
    """硫붿씤 ?낅줈??猷⑦봽: ?쒗듃 ?쎄린 ??濡쒓렇 ??媛??됰퀎 ?낅젰 ?먮룞???뷀듃由?""
    print("諛붿씠留?異쒗뭹 ?먮룞???쒖옉?⑸땲??n")
    print(f"?낅줈??紐⑤뱶: {upload_mode}\n")

    # 1. ?쒗듃?먯꽌 異쒗뭹 ???쎄린
    service = get_sheets_service()
    sheet_name = get_sheet_name(service)
    header_map = get_sheet_header_map(service, sheet_name)
    print(f"??? {sheet_name}")

    rows = read_upload_rows(service, sheet_name, specific_row)

    if not rows:
        print("異쒗뭹 ??곸씠 ?놁뒿?덈떎. (BUYMA URL + DB?곹뭹 + KEY 諛붿씠留덊뙋留ㅺ? ?꾩슂)")
        return

    print(f"異쒗뭹 ?됱닔: {len(rows)}媛쒗뭹\n")
    for r in rows:
        print(f"  {r['row_num']}??{r['brand']} - {r['product_name_kr']} (JPY {r['buyma_price']})")
    print()

    # 2. 釉뚮씪?곗? ?닿린 + 濡쒓렇????
    driver = setup_visible_chrome_driver()
    keep_browser_open = False
    try:
        if not wait_for_buyma_login(driver):
            print("濡쒓렇???ㅽ뙣. 醫낅즺?⑸땲??")
            return

        # 3. ?됰퀎 泥섎━
        processed = 0
        for i, row_data in enumerate(rows):
            if max_items > 0 and processed >= max_items:
                break
            row_num = row_data['row_num']
            print(f"\n{'='*60}")
            print(f"  [{i+1}/{len(rows)}] {row_num}??泥섎━ 以?)
            print(f"{'='*60}")

            if update_cell_by_header(service, sheet_name, row_num, header_map, PROGRESS_STATUS_HEADER, STATUS_UPLOADING):
                print(f"  {row_num}???곹깭 ?낅뜲?댄듃: {STATUS_UPLOADING}")
            processed += 1

            fill_result = fill_buyma_form(driver, row_data)

            if fill_result == "success":
                should_continue, fully_submitted = _handle_success_after_fill(driver, row_num, upload_mode)
                if not should_continue:
                    return
                if fully_submitted:
                    if update_cell_by_header(service, sheet_name, row_num, header_map, PROGRESS_STATUS_HEADER, STATUS_COMPLETED):
                        print(f"  {row_num}???곹깭 ?낅뜲?댄듃: {STATUS_COMPLETED}")
                elif upload_mode == 'auto':
                    if update_cell_by_header(service, sheet_name, row_num, header_map, PROGRESS_STATUS_HEADER, "?ㅻ쪟"):
                        print(f"  {row_num}???곹깭 ?낅뜲?댄듃: ?ㅻ쪟")
            elif fill_result == "manual_review":
                print(f"  {row_num}?됱? ?곹뭹紐????섎룞 ?뺤씤???꾩슂?⑸땲?? ?꾩옱 釉뚮씪?곗? ?붾㈃???뺤씤?댁＜?몄슂.")
                keep_browser_open = True
                _safe_input("  ?섏젙 ?먮뒗 ?뺤씤 ??Enter瑜??뚮윭二쇱꽭??.")
                return
            else:
                print(f"  {row_num}???곹뭹?낅젰 ?ㅽ뙣. 嫄대꼫?곷땲??)
                if update_cell_by_header(service, sheet_name, row_num, header_map, PROGRESS_STATUS_HEADER, "?ㅻ쪟"):
                    print(f"  {row_num}???곹깭 ?낅뜲?댄듃: ?ㅻ쪟")
                _safe_input("  Enter瑜??뚮윭 ?ㅼ쓬?쇰줈 吏꾪뻾...")

        print(f"\n紐⑤뱺 ?곹뭹 泥섎━ ?꾨즺! ({len(rows)}嫄?")

    finally:
        if keep_browser_open:
            print("\n釉뚮씪?곗?瑜??댁뼱???곹깭濡??좎??⑸땲?? ?뺤씤 ??吏곸젒 ?レ븘二쇱꽭??")
        else:
            _safe_input("\n釉뚮씪?곗?瑜?紐⑤몢 ?レ쑝硫?Enter瑜??뚮윭二쇱꽭??..")
            driver.quit()
            print("釉뚮씪?곗?媛 醫낅즺?섏뿀?듬땲??")


def main():
    parser = argparse.ArgumentParser(description="諛붿씠留?異쒗뭹 ?먮룞??)
    parser.add_argument("--scan", action="store_true", help="異쒗뭹 ?섏씠吏 ??援ъ“ ?ㅼ틪 (媛쒕컻??")
    parser.add_argument("--row", type=int, default=0, help="?뱀젙 ?됰쭔 異쒗뭹 (?? --row 3)")
    parser.add_argument(
        "--mode",
        choices=["review", "auto"],
        default="auto",
        help="review=?щ엺 ?뺤씤 ???쒖텧, auto=?ㅻ쪟 ?놁쑝硫??먮룞 ?쒖텧",
    )
    parser.add_argument("--watch", action="store_true", help="?낅줈???뚯빱 媛먯떆 紐⑤뱶")
    parser.add_argument("--interval", type=int, default=20, help="媛먯떆 媛꾧꺽(珥?")
    args = parser.parse_args()

    if args.scan:
        driver = setup_visible_chrome_driver()
        try:
            if not wait_for_buyma_login(driver):
                return
            scan_form_structure(driver)
        finally:
            _safe_input("\nEnter瑜??뚮윭 釉뚮씪?곗?瑜??レ뒿?덈떎...")
            driver.quit()
    else:
        if args.watch:
            interval = max(5, int(args.interval))
            print(f"?낅줈???뚯빱 媛먯떆 ?쒖옉: {interval}珥?媛꾧꺽")
            while True:
                upload_products(specific_row=args.row, upload_mode=args.mode, max_items=1)
                print(f"?ㅼ쓬 ?낅줈???먭?源뚯? {interval}珥??湲?..")
                time.sleep(interval)
        else:
            upload_products(specific_row=args.row, upload_mode=args.mode)


if __name__ == "__main__":
    main()




