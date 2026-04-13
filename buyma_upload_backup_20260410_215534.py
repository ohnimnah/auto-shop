"""
바이마(BUYMA) 출품 자동화 모듈
Google Sheets에서 수집된 상품 정보를 바이마 출품 페이지에 자동 입력한다.

사용법:
    python buyma_upload.py                 # 시트에서 읽어 출품
    python buyma_upload.py --scan          # 출품 페이지 폼 구조 스캔 (개발용)
    python buyma_upload.py --row 2         # 특정 행만 출품
"""

import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# main.py와 동일한 설정 임포트
SPREADSHEET_ID = "1mTV-Fcybov-0uC7tNyM_GXGDoth8F_7wM__zaC1fAjs"
SHEET_GIDS = [1698424449]
SHEET_NAME = "시트1"
ROW_START = 2

BUYMA_SELL_URL = "https://www.buyma.com/my/sell/new?tab=b"
BUYMA_LOGIN_URL = "https://www.buyma.com/login/"

# 바이마 로그인 정보 저장 경로 (로컬)
BUYMA_CRED_PATH = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
    'auto_shop', 'buyma_credentials.json'
)
# Chrome 프로필 경로 (세션/쿠키 유지)
CHROME_PROFILE_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
    'auto_shop', 'chrome_profile'
)

BUYMA_COMMENT_TEMPLATE = """☆☆☆ ご購入前にご確認ください ☆☆☆

◆商品は直営店をはじめ、 デパート、 公式オンラインショップ、ショッピングモールなどの正規品を取り扱う店舗にて買い付けております。100％正規品ですのでご安心ください。

◆「あんしんプラス」へご加入の場合、「サイズがあわない」「イメージと違う」場合に「返品補償制度」をご利用頂けます。
※「返品対象商品」に限ります。詳しくは右記URLをご参照ください。https://qa.buyma.com/trouble/5206.html

◆ご注文～お届けまで
手元在庫有：【ご注文確定】 →【梱包】 → 【発送】 → 【お届け】
手元在庫無し：【ご注文確定】 →【買付】 →【検品】 →【梱包】 →【発送】→【お届け】

◆配送方法/日数
通常国際便（OCS）：【商品準備2-5日 】+ 【発送～お届け5-9日】
※平常時の目安です。繁忙期/非常時はお届け日が前後する場合もございます。詳しくはお問合せください。
※当店では検品時に不良/不具合がある場合は良品に交換をしてお送りしております。当理由でお時間を頂戴する場合は都度ご報告させて頂いております。

◆「お荷物追跡番号あり」にて配送しますので、随時、配送状況をご確認いただけます。
◆土・日・祝日は発送は休務のため、休み明けに順次発送となります。

◆海外製品は「MADE IN JAPAN」の製品に比べて、若干見劣りする場合もございます。
返品・交換にあたる不具合の条件に関しては「お取引について」をご確認ください。

◆当店では、日本完売品、日本未入荷アイテム、限定品、
メンズ、レディース、キッズの シューズ（スニーカー等）や衣類をメインに取り扱っております。
(カップル,ファミリー、ペアルック、親子リンク)
韓国の最新トレンドや新作アイテムを順次出品しており、多くの関心をお願いします。

◆交換・返品・キャンセル
返品と交換に関する規定は、バイマ規定によりお客様の理由による返品はお受けいたしかねますので、ご購入には慎重にお願いいたします。
不良品・誤配送は交換、または返品が可能です。
モニター環境による色違い、サイズ測定方法による1~3cm程度の誤差、糸くず、糸の始末などは欠陥でみなされません。
製品の大きさは測定方法によって1~3cm程度の誤差が生じることがありますが、欠陥ではございません。

◆不良品について
検品は行っておりますが、海外製品は日本商品よりも検品基準が低いです。
下記の理由は返品や交換の原因にはなりません。
- 縫製の粗さ
- 縫い終わり部分の糸が切れていないで残っている
- 生地の色ムラ
- ミリ段位の傷
- 若干の汚れ、シミ
- 製造過程での接着剤の付着など
""".strip()

# 시트 열 인덱스 (A=0, B=1, ..., M=12)
COL = {
    'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5,
    'G': 6, 'H': 7, 'I': 8, 'J': 9, 'K': 10, 'L': 11,
    'M': 12, 'N': 13, 'O': 14,
}


def get_credentials_path() -> str:
    """자격증명 파일 경로를 반환"""
    local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
    if local_app_data:
        cred = os.path.join(local_app_data, 'auto_shop', 'credentials.json')
        if os.path.exists(cred):
            return cred
    fallback = os.path.join(os.path.dirname(__file__), 'credentials.json')
    if os.path.exists(fallback):
        return fallback
    raise FileNotFoundError("credentials.json을 찾을 수 없습니다")


def get_sheets_service():
    """Google Sheets API 서비스 생성"""
    creds = Credentials.from_service_account_file(
        get_credentials_path(),
        scopes=['https://www.googleapis.com/auth/spreadsheets'],
    )
    return build('sheets', 'v4', credentials=creds)


def get_sheet_name(service) -> str:
    """GID로 시트 이름을 찾는다"""
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for s in meta.get('sheets', []):
        if s['properties']['sheetId'] == SHEET_GIDS[0]:
            return s['properties']['title']
    return SHEET_NAME


def read_upload_rows(service, sheet_name: str, specific_row: int = 0) -> List[Dict[str, str]]:
    """시트에서 출품 대상 행을 읽는다. K열(바이마판매가)이 있는 행만 대상."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!A{ROW_START}:O1000",
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

        # 최소 조건: URL + 상품명 + 바이마 판매가가 있어야 출품 가능
        url = cell('B')
        product_name = cell('E')
        buyma_price = cell('L')

        if not url or not product_name or not buyma_price:
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
            'price_krw': cell('K'),
            'buyma_price': buyma_price,
            'image_paths': cell('M'),
            'shipping_cost': cell('N'),
        })

    return rows_data


def _save_buyma_credentials(email: str, password: str):
    """바이마 로그인 정보를 로컬에 저장한다."""
    os.makedirs(os.path.dirname(BUYMA_CRED_PATH), exist_ok=True)
    import base64
    data = {
        'email': base64.b64encode(email.encode()).decode(),
        'password': base64.b64encode(password.encode()).decode(),
    }
    with open(BUYMA_CRED_PATH, 'w') as f:
        json.dump(data, f)
    print("  로그인 정보가 저장되었습니다.")


def _load_buyma_credentials() -> tuple:
    """저장된 바이마 로그인 정보를 읽는다. 없으면 (None, None)"""
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
    """사용자에게 바이마 로그인 정보를 입력받고 저장한다."""
    print("\n바이마 로그인 정보를 입력해주세요 (최초 1회만):")
    email = input("  이메일: ").strip()
    password = input("  비밀번호: ").strip()
    if email and password:
        _save_buyma_credentials(email, password)
    return email, password


def setup_visible_chrome_driver():
    """바이마 출품용 Chrome (헤드리스 아님, 사용자가 볼 수 있어야 함)
    Chrome 프로필을 재사용하여 쿠키/세션이 유지된다."""
    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1400,900")
    chrome_options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # 자동화 감지 방지
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def wait_for_buyma_login(driver) -> bool:
    """바이마 로그인을 처리한다.
    1) Chrome 프로필 쿠키로 이미 로그인 → 즉시 진행
    2) 저장된 계정 정보로 자동 로그인 시도
    3) 실패 시 사용자에게 수동 로그인 대기"""
    driver.get(BUYMA_SELL_URL)
    time.sleep(3)

    # 이미 로그인 상태인지 확인
    if '/login' not in driver.current_url:
        print("이미 로그인 상태입니다.")
        return True

    # 저장된 계정 정보 로드 (없으면 입력 받기)
    email, password = _load_buyma_credentials()
    if not email or not password:
        email, password = _prompt_buyma_credentials()

    if email and password:
        # 자동 로그인 시도
        print("자동 로그인 시도 중...")
        try:
            driver.get(BUYMA_LOGIN_URL)
            time.sleep(2)

            # 이메일 입력
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "input[name='txtLoginId'], input[type='email'], "
                    "input[name='email'], input[id*='login'], input[id*='email']"
                ))
            )
            email_input.clear()
            email_input.send_keys(email)

            # 비밀번호 입력
            pw_input = driver.find_element(By.CSS_SELECTOR,
                "input[name='txtLoginPass'], input[type='password'], "
                "input[name='password']"
            )
            pw_input.clear()
            pw_input.send_keys(password)

            # 로그인 버튼 클릭
            login_btn = driver.find_element(By.CSS_SELECTOR,
                "input[type='submit'][value*='ログイン'], "
                "button[type='submit'], input[type='submit'], "
                ".login-btn, button[class*='login']"
            )
            login_btn.click()
            time.sleep(5)

            # 로그인 성공 확인
            if '/login' not in driver.current_url:
                print("✓ 자동 로그인 성공!")
                driver.get(BUYMA_SELL_URL)
                time.sleep(2)
                return True
            else:
                print("△ 자동 로그인 실패 (비밀번호 변경 또는 캡차 필요)")
                print("  저장된 로그인 정보를 삭제합니다. 다음에 다시 입력해주세요.")
                try:
                    os.remove(BUYMA_CRED_PATH)
                except Exception:
                    pass
        except Exception as e:
            print(f"△ 자동 로그인 중 오류: {e}")

    # 수동 로그인 대기
    print("\n" + "=" * 60)
    print("  바이마 로그인이 필요합니다.")
    print("  브라우저에서 직접 로그인해주세요.")
    print("  로그인 완료를 감지하면 자동으로 진행합니다.")
    print("=" * 60 + "\n")

    for _ in range(300):
        time.sleep(1)
        try:
            current_url = driver.current_url
            if '/login' not in current_url:
                print("로그인 감지! 출품 페이지로 이동합니다...")
                # 수동 로그인 성공 후 계정 정보 저장 여부 묻기
                save = input("  이 계정 정보를 저장하시겠습니까? (y/n): ").strip().lower()
                if save == 'y':
                    new_email = input("  이메일: ").strip()
                    new_pw = input("  비밀번호: ").strip()
                    if new_email and new_pw:
                        _save_buyma_credentials(new_email, new_pw)
                time.sleep(2)
                return True
        except Exception:
            pass

    print("로그인 대기 시간 초과 (5분)")
    return False


def scan_form_structure(driver):
    """출품 페이지의 폼 구조를 스캔하여 출력한다 (개발용)"""
    driver.get(BUYMA_SELL_URL)
    time.sleep(5)

    print("\n=== 바이마 출품 페이지 폼 구조 스캔 ===\n")

    # input 요소
    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[type='file']")
    print(f"[INPUT 필드] ({len(inputs)}개)")
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

    # 페이지 HTML 저장 (디버그용)
    html_path = os.path.join(os.path.dirname(__file__), '_buyma_form_scan.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(driver.page_source)
    print(f"\n페이지 HTML 저장: {html_path}")


def resolve_image_files(image_paths_cell: str) -> List[str]:
    """L열의 이미지 경로 문자열에서 실제 파일 목록을 반환한다"""
    if not image_paths_cell:
        return []

    # 데이터 폴더 기준 이미지 경로
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    data_dir = os.path.join(local_app_data, 'auto_shop') if local_app_data else os.path.expanduser('~/.auto_shop')
    images_root = os.path.join(data_dir, 'images')

    files = []
    for part in image_paths_cell.split(','):
        path = part.strip()
        if not path:
            continue
        # 절대경로 또는 images_root 기준 상대경로
        if os.path.isabs(path):
            full_path = path
        else:
            full_path = os.path.join(images_root, path)

        if os.path.isfile(full_path):
            files.append(os.path.abspath(full_path))
        elif os.path.isdir(full_path):
            # 폴더면 안의 이미지 전부
            for ext in ('*.jpg', '*.jpeg', '*.png', '*.webp'):
                files.extend(sorted(glob.glob(os.path.join(full_path, ext))))

    return files


def _scroll_and_click(driver, element):
    """요소를 뷰포트에 스크롤한 뒤 클릭 (하단 바에 가려지는 문제 방지)"""
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", element)
    driver.execute_script("window.scrollBy(0, -120);")
    time.sleep(0.3)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def _infer_color_system(color_text: str) -> str:
    """영문/국문 색상명을 BUYMA 색상계통(일본어)으로 매핑한다."""
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
        return 'ゴールド系'
    return 'その他'


def _select_color_system(driver, color_system: str, row_index: int = 0) -> bool:
    """색상계통 Select에서 키워드에 맞는 옵션을 선택한다."""
    try:
        color_selects = driver.find_elements(By.CSS_SELECTOR, ".sell-color-table .Select")
        if not color_selects:
            return False
        color_select = color_selects[min(row_index, len(color_selects) - 1)]
        control = color_select.find_element(By.CSS_SELECTOR, ".Select-control")
        _scroll_and_click(driver, control)
        time.sleep(0.4)

        # 드롭다운 옵션 중 목표 텍스트 우선 선택
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

        # 옵션을 바로 못 읽는 경우 키보드 fallback
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
            time.sleep(0.05)
        active.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def _split_color_values(color_text: str) -> List[str]:
    """색상 문자열을 구분자 기준으로 분리한다."""
    if not color_text:
        return []
    parts = re.split(r'[,/|]|\s+and\s+|\s*&\s*', color_text)
    out = []
    for p in parts:
        v = p.strip()
        if v:
            out.append(v)
    return out


def _try_add_color_row(driver) -> bool:
    """색상 행 추가 버튼이 있으면 클릭한다."""
    try:
        area = driver.find_element(By.CSS_SELECTOR, ".sell-color-table")
        candidates = area.find_elements(By.CSS_SELECTOR, "button, a, [role='button'], [class*='add']")
        for c in candidates:
            txt = (c.text or '').strip()
            cls = (c.get_attribute('class') or '')
            if ('追加' in txt) or ('add' in cls.lower()) or ('plus' in cls.lower()):
                _scroll_and_click(driver, c)
                time.sleep(0.4)
                return True
    except Exception:
        return False
    return False


def _fill_size_supplement(driver, size_text: str) -> bool:
    """사이즈 선택 옵션이 없을 때 색/사이즈 보충정보 textarea에 사이즈를 기록한다."""
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
        line = f"サイズ: {size_text}"
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
    """색상명 입력칸이 비활성일 때 색/사이즈 보충정보 textarea에 영어 색상명을 기록한다."""
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
    """시트 사이즈 표기를 BUYMA 라벨 비교용 후보들로 확장한다."""
    sz = (size_raw or '').strip()
    if not sz:
        return []

    variants = [sz]
    szu = sz.upper().replace(' ', '')

    # F/FREE/OS 계열
    if szu in {'F', 'FREE', 'FREESIZE', 'OS', 'ONESIZE', 'O/S'}:
        variants.extend([
            'F', 'FREE', 'FREE SIZE', 'ONE SIZE', 'ONESIZE', 'OS', 'O/S',
            'フリー', 'フリーサイズ', 'ワンサイズ', 'サイズ指定なし', '指定なし'
        ])

    # 신발 3자리(예: 240) 변환
    if sz.isdigit() and len(sz) == 3:
        numeric = int(sz)
        if 200 <= numeric <= 350:
            variants.append(f"{numeric / 10:.1f}")
            variants.append(str(numeric // 10))

    # 중복 제거(순서 유지)
    seen = set()
    out = []
    for v in variants:
        k = v.lower()
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _check_no_variation_option(driver) -> bool:
    """사이즈/색상 옵션이 없을 때 '변형없음' 계열 옵션을 체크한다."""
    keywords = [
        '変動なし', '変形なし', 'バリエーションなし', 'サイズなし',
        'サイズ指定なし', '指定なし', '변형없음'
    ]
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        labels = variation.find_elements(By.CSS_SELECTOR, "label")
        for lb in labels:
            txt = (lb.text or '').strip()
            if not txt:
                continue
            if any(k in txt for k in keywords):
                _scroll_and_click(driver, lb)
                return True

        # 텍스트 기반으로 클릭 가능한 요소를 폭넓게 탐색
        nodes = variation.find_elements(By.XPATH, ".//*[normalize-space(text())!='']")
        for node in nodes:
            txt = (node.text or '').strip()
            if not txt:
                continue
            if any(k in txt for k in keywords):
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

        # 라벨 텍스트가 비어있는 경우 input 값/이름으로 fallback
        inputs = variation.find_elements(By.CSS_SELECTOR, "input[type='checkbox'], input[type='radio']")
        for ipt in inputs:
            meta = ' '.join([
                ipt.get_attribute('value') or '',
                ipt.get_attribute('name') or '',
                ipt.get_attribute('id') or ''
            ])
            if any(k in meta for k in ['none', 'unspecified', 'no_variation', 'variation_none']):
                if not ipt.is_selected():
                    driver.execute_script("arguments[0].click();", ipt)
                return True
    except Exception:
        return False
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
                time.sleep(0.6)
                return True
    except Exception:
        return False
    return False


def _fill_size_text_inputs(driver, size_text: str) -> int:
    """체크박스가 없는 경우 사이즈 텍스트 입력칸에 값을 입력한다."""
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
            time.sleep(0.15)
        return count
    except Exception:
        return 0


# ---- 카테고리 추론 매핑 ----
# 상품명(한국어/영어) 키워드 → (大カテゴリ, 中カテゴリ, 小カテゴリ)
# 대/중에 해당하는 조합만 있으면 소카테는 None
CATEGORY_KEYWORDS = [
    # 신발 계열
    (['ballet', 'flat', '플랫', 'バレエ'], 'レディースファッション', '靴', 'フラットシューズ'),
    (['sneaker', 'スニーカー', '스니커즈'], None, '靴', 'スニーカー'),
    (['sandal', 'サンダル', '샌들', '슬라이드', 'slide'], None, '靴', 'サンダル'),
    (['boot', 'ブーツ', '부츠'], None, '靴', 'ブーツ'),
    (['loafer', 'ローファー', '로퍼'], None, '靴', 'ローファー・オペラシューズ'),
    (['pump', 'パンプス', '펌프스'], 'レディースファッション', '靴', 'パンプス'),
    (['mule', 'ミュール', '뮬'], 'レディースファッション', '靴', 'ミュール'),
    (['clog', 'クロッグ', '클로그'], None, '靴', 'サンダル'),
    (['shoe', 'シューズ', '신발', '靴'], None, '靴', None),
    # 가방 계열
    (['tote', 'トート', '토트'], None, 'バッグ', 'トートバッグ'),
    (['backpack', 'リュック', '백팩', '배낭'], None, 'バッグ', 'バックパック・リュック'),
    (['shoulder', 'ショルダー', '숄더'], None, 'バッグ', 'ショルダーバッグ'),
    (['bag', 'バッグ', '가방'], None, 'バッグ', None),
    # 지갑/소품 계열
    (['wallet', '財布', '지갑', 'ウォレット'], None, 'ファッション雑貨・小物', '財布'),
    (['card case', 'カードケース', '카드케이스'], None, 'ファッション雑貨・小物', 'カードケース・名刺入れ'),
    (['keyring', 'キーリング', '키링', 'keychain'], None, 'ファッション雑貨・小物', 'キーケース・キーリング'),
    # 의류 계열 - 상의
    (['t-shirt', 'tee', 'tシャツ', '티셔츠', '긴팔'], None, 'トップス', 'Tシャツ・カットソー'),
    (['hoodie', 'フーディ', '후디', '후드'], None, 'トップス', 'パーカー・フーディ'),
    (['sweater', 'knit', 'ニット', '니트', '스웨터'], None, 'トップス', 'ニット・セーター'),
    (['shirt', 'シャツ', '셔츠', 'blouse', '블라우스'], None, 'トップス', 'シャツ・ブラウス'),
    (['jacket', 'ジャケット', '재킷'], None, 'アウター', 'テーラードジャケット'),
    (['coat', 'コート', '코트'], None, 'アウター', 'コート'),
    (['windbreaker', 'ウィンドブレーカー', '윈드'], None, 'アウター', None),
    # track + pants는 하의로 우선 분류 (사이즈 옵션 노출률이 높음)
    (['track pants', 'trackpant', 'トラックパンツ', '트랙 팬츠', '트랙팬츠'], None, 'ボトムス', 'パンツ'),
    (['track', 'トラック', '트랙', 'jersey', 'ジャージ'], None, 'アウター', 'ジャージ'),
    # 의류 계열 - 하의
    (['pants', 'パンツ', '팬츠', 'trouser', 'スラックス'], None, 'ボトムス', 'パンツ'),
    (['jeans', 'denim', 'デニム', '진', '청바지'], None, 'ボトムス', 'デニム・ジーパン'),
    (['legging', 'レギンス', '레깅스', 'タイツ'], None, 'ボトムス', 'レギンス・スパッツ'),
    (['skirt', 'スカート', '스커트'], 'レディースファッション', 'ボトムス', 'スカート'),
    (['shorts', 'ハーフパンツ', '숏팬츠', '반바지'], None, 'ボトムス', 'ハーフパンツ・ショートパンツ'),
    # 원피스
    (['dress', 'ドレス', '드레스', 'ワンピース', '원피스'], 'レディースファッション', 'ワンピース・オールインワン', 'ワンピース'),
    # 모자
    (['hat', 'ハット', '햇', '모자', 'bucket'], None, '帽子', 'ハット'),
    (['cap', 'キャップ', '캡'], None, '帽子', 'キャップ'),
    (['beanie', 'ビーニー', '비니'], None, '帽子', 'ニットキャップ・ビーニー'),
]


def _infer_buyma_category(product_name_kr: str, product_name_en: str, brand: str = '') -> Tuple[str, str, str]:
    """상품명에서 BUYMA 카테고리 3단계를 추론한다.
    Returns: (大カテゴリ, 中カテゴリ, 小カテゴリ) - 매칭 없으면 빈 문자열"""
    text = f"{product_name_kr} {product_name_en} {brand}".lower()
    for keywords, cat1, cat2, cat3 in CATEGORY_KEYWORDS:
        if any(kw.lower() in text for kw in keywords):
            # 대카테고리가 None이면 기본 메ンズ/레디스 판단
            if cat1 is None:
                # 기본적으로 レディースファッション (필요시 성별 판단 로직 추가)
                cat1 = 'レディースファッション'
            return (cat1, cat2 or '', cat3 or '')
    return ('', '', '')


def _select_category_by_arrow(driver, item_index: int, target_label: str) -> bool:
    """sell-category__item의 Select에서 ArrowDown+Enter로 옵션을 선택한다."""
    if item_index == 0:
        sel_el = driver.find_element(By.CSS_SELECTOR, '.sell-category-select')
    else:
        items = driver.find_elements(By.CSS_SELECTOR, '.sell-category__item')
        if len(items) <= item_index:
            return False
        sel_el = items[item_index].find_element(By.CSS_SELECTOR, '.Select')
    
    ctrl = sel_el.find_element(By.CSS_SELECTOR, '.Select-control')
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", ctrl)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click()", ctrl)
    time.sleep(0.8)
    
    combo = sel_el.find_element(By.CSS_SELECTOR, '.Select-input')
    seen = []
    for _ in range(80):
        combo.send_keys(Keys.ARROW_DOWN)
        time.sleep(0.12)
        focused = driver.execute_script("""
            var items = document.querySelectorAll('.sell-category__item');
            var sel = arguments[0] === 0
                ? document.querySelector('.sell-category-select')
                : items[arguments[0]].querySelector('.Select');
            var f = sel.querySelector('.Select-option.is-focused');
            return f ? (f.getAttribute('aria-label') || '') : '';
        """, item_index)
        if focused == target_label:
            combo.send_keys(Keys.ENTER)
            time.sleep(2)
            return True
        # 순환 감지
        if focused:
            if focused in seen and len(seen) > 2 and focused == seen[0]:
                break
            if focused not in seen:
                seen.append(focused)
    combo.send_keys(Keys.ESCAPE)
    time.sleep(0.3)
    return False


def _find_best_option_by_arrow(driver, item_index: int, target_keyword: str,
                               fallback_other: bool = True) -> bool:
    """sell-category__item의 Select에서 키워드를 포함하는 옵션을 ArrowDown+Enter로 선택한다.
    fallback_other=True이면 매칭 실패 시 'その他' 옵션을 자동 선택한다."""
    if item_index == 0:
        sel_el = driver.find_element(By.CSS_SELECTOR, '.sell-category-select')
    else:
        items = driver.find_elements(By.CSS_SELECTOR, '.sell-category__item')
        if len(items) <= item_index:
            return False
        sel_el = items[item_index].find_element(By.CSS_SELECTOR, '.Select')
    
    ctrl = sel_el.find_element(By.CSS_SELECTOR, '.Select-control')
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", ctrl)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click()", ctrl)
    time.sleep(0.8)
    
    combo = sel_el.find_element(By.CSS_SELECTOR, '.Select-input')
    seen = []
    for _ in range(80):
        combo.send_keys(Keys.ARROW_DOWN)
        time.sleep(0.12)
        focused = driver.execute_script("""
            var items = document.querySelectorAll('.sell-category__item');
            var sel = arguments[0] === 0
                ? document.querySelector('.sell-category-select')
                : items[arguments[0]].querySelector('.Select');
            var f = sel.querySelector('.Select-option.is-focused');
            return f ? (f.getAttribute('aria-label') || '') : '';
        """, item_index)
        if focused and target_keyword in focused:
            combo.send_keys(Keys.ENTER)
            time.sleep(2)
            return True
        if focused:
            if focused in seen and len(seen) > 2 and focused == seen[0]:
                break
            if focused not in seen:
                seen.append(focused)
    combo.send_keys(Keys.ESCAPE)
    time.sleep(0.3)

    # 키워드 매칭 실패 → 'その他' 폴백
    if fallback_other and seen:
        return _find_best_option_by_arrow(driver, item_index, 'その他',
                                          fallback_other=False)
    return False


def _dismiss_overlay(driver):
    """드라이버 팝업/오버레이 제거"""
    driver.execute_script("""
        document.querySelectorAll('#driver-page-overlay, .driver-popover, [id*="driver-"]')
            .forEach(function(el) { el.remove(); });
    """)
    time.sleep(0.3)


def _find_section_field(driver, section_title: str, field_css: str):
    """바이마 출품 페이지에서 섹션 제목(bmm-c-summary__ttl) 아래의 필드를 찾는다"""
    sections = driver.find_elements(By.CSS_SELECTOR, "p.bmm-c-summary__ttl")
    for sec in sections:
        if section_title in sec.text:
            # 섹션의 부모 컨테이너에서 필드 탐색
            parent = sec
            for _ in range(5):
                parent = parent.find_element(By.XPATH, '..')
                fields = parent.find_elements(By.CSS_SELECTOR, field_css)
                if fields:
                    return fields[0]
    return None


def _click_react_select_option(driver, select_container, keyword: str) -> bool:
    """React Select 컴포넌트에서 옵션을 클릭한다"""
    try:
        # Select 컨트롤 클릭하여 드롭다운 열기
        control = select_container.find_element(By.CSS_SELECTOR, ".Select-control, [class*='Select-control']")
        control.click()
        time.sleep(0.5)
        # 옵션 목록에서 키워드 매칭
        options = select_container.find_elements(By.CSS_SELECTOR, ".Select-option, [class*='Select-option']")
        for opt in options:
            if keyword in opt.text:
                opt.click()
                time.sleep(0.5)
                return True
    except Exception:
        pass
    return False


def fill_buyma_form(driver, row_data: Dict[str, str]) -> bool:
    """바이마 출품 폼에 상품 정보를 자동 입력한다.
    바이마는 React 기반 bmm-c-* 컴포넌트를 사용하며 name/id 속성이 없음."""
    try:
        driver.get(BUYMA_SELL_URL)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".bmm-c-heading__ttl"))
        )
        time.sleep(3)

        row_num = row_data['row_num']
        print(f"\n--- [{row_num}행] 바이마 출품 폼 입력 시작 ---")
        print(f"  상품명: {row_data['product_name_kr']}")
        print(f"  브랜드: {row_data['brand']}")
        print(f"  바이마 판매가: {row_data['buyma_price']}")

        # ---- 오버레이 제거 ----
        _dismiss_overlay(driver)

        # ---- カテゴリ 자동 선택 ----
        try:
            cat1, cat2, cat3 = _infer_buyma_category(
                row_data.get('product_name_kr', ''),
                row_data.get('product_name_en', ''),
                row_data.get('brand', '')
            )
            if cat1 and cat2:
                print(f"  카테고리 추론: {cat1} > {cat2} > {cat3}")
                # 대카테고리 선택
                if _select_category_by_arrow(driver, 0, cat1):
                    print(f"  ✓ 대카테: {cat1}")
                    # 중카테고리 선택
                    if cat2 and _find_best_option_by_arrow(driver, 1, cat2):
                        # 실제 선택된 값 확인
                        sel_val = driver.execute_script("""
                            var items = document.querySelectorAll('.sell-category__item');
                            if (items.length < 2) return '';
                            var v = items[1].querySelector('.Select-value-label');
                            return v ? v.textContent.trim() : '';
                        """)
                        if 'その他' in sel_val and sel_val != cat2:
                            print(f"  ✓ 중카테: {cat2} → その他 (기타)")
                        else:
                            print(f"  ✓ 중카테: {sel_val or cat2}")
                        # 소카테고리 선택
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
                                    if 'その他' in (sel_val3 or '') and sel_val3 != cat3:
                                        print(f"  ✓ 소카테: {cat3} → その他 (기타)")
                                    else:
                                        print(f"  ✓ 소카테: {sel_val3 or cat3}")
                                else:
                                    print(f"  △ 소카테 '{cat3}' 미발견, その他도 없음")
                    else:
                        print(f"  △ 중카테 '{cat2}' 미발견, その他도 없음")
                else:
                    print(f"  △ 대카테 '{cat1}' 미발견, 수동 선택 필요")
            else:
                print(f"  △ 카테고리 추론 불가, 수동 선택 필요")
        except Exception as e:
            print(f"  △ 카테고리 선택 실패: {e}")

        # ---- 상품명 입력: "[Brand] ProductNameEN ColorEN" ----
        brand_en = row_data.get('brand_en', '') or row_data.get('brand', '')
        name_en = row_data.get('product_name_en') or row_data['product_name_kr']
        color_en = row_data.get('color_en') or row_data.get('color_kr', '')
        if color_en.lower() == 'none':
            color_en = ''
        title_parts = []
        if brand_en:
            title_parts.append(f"[{brand_en}]")
        title_parts.append(name_en)
        if color_en:
            title_parts.append(color_en)
        product_title = ' '.join(title_parts)
        try:
            # 첫 번째 bmm-c-field 안의 text input이 상품명
            name_fields = driver.find_elements(By.CSS_SELECTOR,
                ".bmm-c-field__input > input.bmm-c-text-field"
            )
            if name_fields:
                name_fields[0].clear()
                name_fields[0].send_keys(product_title)
                print(f"  ✓ 상품명 입력: {product_title}")
            else:
                print(f"  ✗ 상품명 필드를 찾을 수 없습니다")
        except Exception as e:
            print(f"  ✗ 상품명 입력 실패: {e}")

        # ---- 브랜드 입력 (영어) ----
        brand = row_data.get('brand_en', '') or row_data.get('brand', '')
        if brand:
            try:
                brand_input = driver.find_element(By.CSS_SELECTOR,
                    "input[placeholder*='ブランド名を入力']"
                )
                _scroll_and_click(driver, brand_input)
                brand_input.clear()
                brand_input.send_keys(brand)
                time.sleep(1.2)
                # 추천 목록이 전역 ul과 섞이는 경우가 있어 입력창 기준 키보드 선택을 우선 사용
                brand_input.send_keys(Keys.ARROW_DOWN)
                time.sleep(0.2)
                brand_input.send_keys(Keys.ENTER)
                print(f"  ✓ 브랜드 입력/선택: {brand}")
            except Exception as e:
                print(f"  ✗ 브랜드 입력 실패: {e}")

        # ---- 색상: React Select로 색상 선택 + 텍스트 입력 ----
        color = row_data.get('color_en') or row_data.get('color_kr', '')
        color_en_input = (row_data.get('color_en') or '').strip()
        if color and color.lower() != 'none':
            try:
                color_values = _split_color_values(color_en_input or color)
                if not color_values:
                    color_values = [color]
                color_for_system = color_values[0]
                color_system = _infer_color_system(color_for_system)
                picked = _select_color_system(driver, color_system, row_index=0)

                # 다중 색상은 행 추가 후 각 행에 계통 선택 시도
                if len(color_values) > 1:
                    for idx, cval in enumerate(color_values[1:], start=1):
                        if _try_add_color_row(driver):
                            _select_color_system(driver, _infer_color_system(cval), row_index=idx)

                # 색상명 입력칸은 계통 선택 후 활성화될 수 있음
                color_name_inputs = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".sell-color-table tbody tr td:nth-child(2) input.bmm-c-text-field, .sell-color-table input.bmm-c-text-field"
                )
                color_name_input = None
                for ci in color_name_inputs:
                    if ci.is_enabled() and ci.get_attribute('disabled') is None:
                        color_name_input = ci
                        break

                if color_name_input:
                    color_name_value = color_en_input or color
                    _scroll_and_click(driver, color_name_input)
                    color_name_input.clear()
                    color_name_input.send_keys(color_name_value)
                    time.sleep(0.5)
                    if picked:
                        print(f"  ✓ 색상 입력: {color_system} / {color_name_value}")
                    else:
                        print(f"  △ 색상계통 미선택, 색상명만 입력: {color_name_value}")
                else:
                    color_name_value = color_en_input or color
                    forced = False
                    if color_name_inputs and color_name_value:
                        try:
                            forced = driver.execute_script(
                                "var el=arguments[0], val=arguments[1];"
                                "el.removeAttribute('disabled');"
                                "var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                                "setter.call(el, val);"
                                "el.dispatchEvent(new Event('input',{bubbles:true}));"
                                "el.dispatchEvent(new Event('change',{bubbles:true}));"
                                "return (el.value===val);",
                                color_name_inputs[0], color_name_value
                            )
                        except Exception:
                            forced = False

                    if picked and forced:
                        print(f"  ✓ 색상 입력(JS강제): {color_system} / {color_name_value}")
                    elif picked:
                        if _fill_color_supplement(driver, color_name_value):
                            print(f"  ✓ 색상계통 선택 + 보충정보 입력: {color_system} / {color_name_value}")
                        else:
                            print(f"  ✓ 색상계통 선택: {color_system} (색상명 입력칸 비활성)")
                    else:
                        print(f"  △ 색상 입력 실패(계통/색상명), 수동 선택 필요: {color}")
            except Exception as e:
                print(f"  △ 색상 입력 실패: {e}")

        # ---- 사이즈: 컨테이너 탭 클릭 후 체크박스 선택 ----
        # 주의: 카테고리 미선택 시 사이즈 목록이 표시되지 않음
        size_text = row_data.get('size', '')
        try:
            # '사이즈' 탭 클릭
            size_tabs = driver.find_elements(By.CSS_SELECTOR, ".sell-variation__tab-item")
            handled_size = False
            for tab in size_tabs:
                tab_text = (tab.text or '').strip()
                tab_panel_id = (tab.get_attribute('aria-controls') or '').strip()
                if ('サイズ' in tab_text) or tab_panel_id.endswith('-3'):
                    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", tab)
                    driver.execute_script("window.scrollBy(0, -180);")
                    _scroll_and_click(driver, tab)
                    time.sleep(1)

                    panel = None
                    if tab_panel_id:
                        try:
                            panel = driver.find_element(By.ID, tab_panel_id)
                        except Exception:
                            panel = None
                    if panel is None:
                        panel = driver.find_element(By.CSS_SELECTOR, ".sell-variation")

                    panel_html = panel.text.strip()
                    if 'カテゴリーを選択' in panel_html:
                        print(f"  △ 카테고리 미선택으로 사이즈 목록 없음. 카테고리 선택 후 수동 선택 필요: {size_text}")
                    else:
                        items = panel.find_elements(By.CSS_SELECTOR, "label")
                        if not items:
                            items = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                        avail = [it.text.strip() for it in items if it.text.strip()][:10]

                        matched = 0
                        if size_text:
                            sizes = [s.strip() for s in size_text.split(',') if s.strip()]
                            for sz in sizes:
                                sz_variants = _build_size_variants(sz)
                                for item in items:
                                    item_text = item.text.strip()
                                    item_text_norm = item_text.lower().replace(' ', '')
                                    if any(
                                        (v.lower().replace(' ', '') == item_text_norm)
                                        or (v.lower().replace(' ', '') in item_text_norm)
                                        for v in sz_variants
                                    ):
                                        _scroll_and_click(driver, item)
                                        matched += 1
                                        time.sleep(0.3)
                                        break

                        if matched:
                            print(f"  ✓ 사이즈 선택: {matched}개 ({size_text})")
                        else:
                            if not avail:
                                # 먼저 '사이즈 지정' UI 펼치기 시도
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
                                                item_text_norm2 = item_text2.lower().replace(' ', '')
                                                if any(
                                                    (v.lower().replace(' ', '') == item_text_norm2)
                                                    or (v.lower().replace(' ', '') in item_text_norm2)
                                                    for v in sz_variants2
                                                ):
                                                    _scroll_and_click(driver, item2)
                                                    matched2 += 1
                                                    time.sleep(0.2)
                                                    break
                                    if matched2:
                                        print(f"  ✓ 사이즈 선택: {matched2}개 ({size_text})")
                                        handled_size = True
                                        break

                                if _check_no_variation_option(driver):
                                    print(f"  ✓ 사이즈 옵션 없음 → 변형없음 체크")
                                elif size_text and _fill_size_text_inputs(driver, size_text) > 0:
                                    print(f"  ✓ 사이즈 텍스트 입력: {size_text}")
                                elif size_text and _fill_size_supplement(driver, size_text):
                                    print(f"  ✓ 사이즈 옵션 없음 → 보충정보 입력: {size_text}")
                                else:
                                    print(f"  △ 사이즈 옵션 없음(변형없음/보충정보 처리 실패): {size_text}")
                            else:
                                if size_text:
                                    print(f"  △ 사이즈 매칭 실패 (가능 옵션: {avail}), 수동 선택 필요: {size_text}")
                                else:
                                    print(f"  △ 사이즈 값 없음 (가능 옵션: {avail})")
                    handled_size = True
                    break

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
                            item_text_norm = item_text.lower().replace(' ', '')
                            if any(
                                (v.lower().replace(' ', '') == item_text_norm)
                                or (v.lower().replace(' ', '') in item_text_norm)
                                for v in sz_variants
                            ):
                                _scroll_and_click(driver, item)
                                matched += 1
                                time.sleep(0.2)
                                break
                if matched:
                    print(f"  ✓ 사이즈 선택: {matched}개 ({size_text})")
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
                                    item_text_norm2 = item_text2.lower().replace(' ', '')
                                    if any(
                                        (v.lower().replace(' ', '') == item_text_norm2)
                                        or (v.lower().replace(' ', '') in item_text_norm2)
                                        for v in sz_variants2
                                    ):
                                        _scroll_and_click(driver, item2)
                                        matched2 += 1
                                        time.sleep(0.2)
                                        break
                        if matched2:
                            print(f"  ✓ 사이즈 선택: {matched2}개 ({size_text})")
                        elif _check_no_variation_option(driver):
                            print(f"  ✓ 사이즈 옵션 없음 → 변형없음 체크")
                        elif size_text and _fill_size_text_inputs(driver, size_text) > 0:
                            print(f"  ✓ 사이즈 텍스트 입력: {size_text}")
                        elif size_text and _fill_size_supplement(driver, size_text):
                            print(f"  ✓ 사이즈 옵션 없음 → 보충정보 입력: {size_text}")
                        else:
                            print(f"  △ 사이즈 탭/옵션 미탐지: {size_text}")
                    elif _check_no_variation_option(driver):
                        print(f"  ✓ 사이즈 옵션 없음 → 변형없음 체크")
                    elif size_text and _fill_size_text_inputs(driver, size_text) > 0:
                        print(f"  ✓ 사이즈 텍스트 입력: {size_text}")
                    elif size_text and _fill_size_supplement(driver, size_text):
                        print(f"  ✓ 사이즈 옵션 없음 → 보충정보 입력: {size_text}")
                    else:
                        print(f"  △ 사이즈 탭/옵션 미탐지: {size_text}")
                else:
                    if size_text:
                        print(f"  △ 사이즈 매칭 실패 (가능 옵션: {avail}), 수동 선택 필요: {size_text}")
                    else:
                        print(f"  △ 사이즈 값 없음 (가능 옵션: {avail})")
        except Exception as e:
            print(f"  ✗ 사이즈 선택 실패: {e}")

        # ---- 구입기한: react-datepicker (.sell-term) +89일 (최대 설정 가능 기간) ----
        try:
            deadline_date = datetime.now() + timedelta(days=89)
            deadline_str = deadline_date.strftime('%Y/%m/%d')
            deadline_input = driver.find_element(By.CSS_SELECTOR, "input.sell-term")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", deadline_input)
            time.sleep(0.3)
            # react-datepicker는 JS로 값 설정
            driver.execute_script(
                "var el = arguments[0]; "
                "var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; "
                "nativeInputValueSetter.call(el, arguments[1]); "
                "el.dispatchEvent(new Event('input', { bubbles: true })); "
                "el.dispatchEvent(new Event('change', { bubbles: true }));",
                deadline_input, deadline_str
            )
            time.sleep(0.5)
            print(f"  ✓ 구입기한 입력: {deadline_str}")
        except Exception as e:
            print(f"  △ 구입기한 입력 실패, 수동 입력 필요: {e}")

        # ---- 상품 설명(コメント): 첫 번째 textarea.bmm-c-textarea ----
        try:
            textareas = driver.find_elements(By.CSS_SELECTOR, "textarea.bmm-c-textarea")
            if textareas:
                # 상단 sell-variation 내부 textarea는 색/사이즈 보충정보일 수 있어 마지막 textarea를 코멘트로 사용
                target_comment = textareas[-1]
                _scroll_and_click(driver, target_comment)
                target_comment.clear()
                target_comment.send_keys(BUYMA_COMMENT_TEMPLATE)
                print(f"  ✓ 상품 설명 입력 (고정 템플릿)")
            else:
                print(f"  ✗ 코멘트 textarea를 찾을 수 없습니다")
        except Exception as e:
            print(f"  ✗ 상품 설명 입력 실패: {e}")

        # ---- 배송방법: OCS 체크박스 체크 ----
        try:
            ocs_checked = driver.execute_script("""
                // OCS 텍스트를 포함하는 행(tr)의 체크박스를 찾아 체크한다
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
                print(f"  ✓ 배송방법 OCS 체크")
            elif ocs_checked == 'already':
                print(f"  ✓ 배송방법 OCS 이미 체크됨")
            else:
                print(f"  △ OCS 체크박스를 찾지 못했습니다. 수동 선택 필요")
        except Exception as e:
            print(f"  ✗ 배송방법 선택 실패: {e}")

        # ---- 가격 입력: half-size-char 필드 (K열 값) ----
        buyma_price = re.sub(r'[^\d]', '', row_data.get('buyma_price', ''))
        if buyma_price:
            try:
                adjusted_price = max(0, int(buyma_price) - 10)
                price_inputs = driver.find_elements(By.CSS_SELECTOR,
                    "input.bmm-c-text-field.bmm-c-text-field--half-size-char"
                )
                if price_inputs:
                    price_inputs[0].clear()
                    price_inputs[0].send_keys(str(adjusted_price))
                    print(f"  ✓ 판매가 입력: ¥{adjusted_price} (엑셀값-10)")
                else:
                    print(f"  ✗ 가격 입력 필드를 찾을 수 없습니다")
            except Exception as e:
                print(f"  ✗ 판매가 입력 실패: {e}")

        # ---- 구매지/발송지: 이미 아시아-한국으로 기본 설정되어 있음 ----
        # 도시(서울) Select 선택: Select-value-label이 "選択なし"인 항목 → ソウル
        try:
            selects = driver.find_elements(By.CSS_SELECTOR, ".Select")
            city_count = 0
            for sel_container in selects:
                try:
                    val_label = sel_container.find_element(By.CSS_SELECTOR, ".Select-value-label")
                    if '選択なし' in val_label.text:
                        _scroll_and_click(driver, sel_container.find_element(By.CSS_SELECTOR, ".Select-control"))
                        time.sleep(0.5)
                        opts = driver.find_elements(By.CSS_SELECTOR, ".Select-option")
                        for opt in opts:
                            if 'ソウル' in opt.text:
                                opt.click()
                                city_count += 1
                                time.sleep(0.3)
                                break
                except Exception:
                    continue
            if city_count:
                print(f"  ✓ 도시 선택: ソウル ({city_count}개)")
        except Exception as e:
            print(f"  △ 도시 선택 실패, 수동 선택 필요: {e}")

        # ---- 이미지 업로드 ----
        image_files = resolve_image_files(row_data.get('image_paths', ''))
        if image_files:
            try:
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if file_inputs:
                    # 첫 번째 file input에 모든 이미지 경로를 줄바꿈으로 전달
                    file_input = file_inputs[0]
                    file_paths_str = "\n".join(image_files)
                    file_input.send_keys(file_paths_str)
                    print(f"  ✓ 이미지 업로드: {len(image_files)}장")
                    time.sleep(2)  # 업로드 대기
                else:
                    print(f"  ✗ 이미지 업로드 필드를 찾을 수 없습니다")
            except Exception as e:
                print(f"  ✗ 이미지 업로드 실패: {e}")
        else:
            print(f"  △ 업로드할 이미지 없음")

        return True

    except Exception as e:
        print(f"  ✗ 폼 입력 중 오류: {e}")
        return False


def upload_products(specific_row: int = 0):
    """메인 업로드 루프: 시트 읽기 → 로그인 대기 → 행별 입력 → 사용자 확인"""
    print("바이마 출품 자동화를 시작합니다.\n")

    # 1. 시트에서 출품 대상 읽기
    service = get_sheets_service()
    sheet_name = get_sheet_name(service)
    print(f"시트: {sheet_name}")

    rows = read_upload_rows(service, sheet_name, specific_row)
    if not rows:
        print("출품 대상 행이 없습니다. (B열 URL + D열 상품명 + K열 바이마판매가 필요)")
        return

    print(f"출품 대상: {len(rows)}개 상품\n")
    for r in rows:
        print(f"  {r['row_num']}행: {r['brand']} - {r['product_name_kr']} (¥{r['buyma_price']})")
    print()

    # 2. 브라우저 열기 + 로그인 대기
    driver = setup_visible_chrome_driver()
    try:
        if not wait_for_buyma_login(driver):
            print("로그인 실패. 종료합니다.")
            return

        # 3. 행별 처리
        for i, row_data in enumerate(rows):
            row_num = row_data['row_num']
            print(f"\n{'='*60}")
            print(f"  [{i+1}/{len(rows)}] {row_num}행 처리 중")
            print(f"{'='*60}")

            success = fill_buyma_form(driver, row_data)

            if success:
                print(f"\n  폼 입력이 완료되었습니다.")
                print(f"  브라우저에서 내용을 확인하고 수정하세요.")
                print(f"  준비되면 아래에서 선택해주세요:\n")

                while True:
                    choice = input("  [Enter] 다음 상품으로  |  [s] 제출(출품)  |  [q] 종료: ").strip().lower()
                    if choice == '':
                        print(f"  → {row_num}행 건너뜀")
                        break
                    elif choice == 's':
                        # 제출 버튼 클릭 시도 (bmm-c-btn--p: "入力内容を確認する")
                        try:
                            submit_btn = None
                            buttons = driver.find_elements(By.CSS_SELECTOR, "button.bmm-c-btn--p, button[class*='bmm-c-btn']")
                            for btn in buttons:
                                if '確認' in btn.text or '入力内容' in btn.text:
                                    submit_btn = btn
                                    break
                            if not submit_btn:
                                submit_btn = driver.find_element(By.XPATH,
                                    "//button[contains(text(),'入力内容を確認する')]"
                                )
                            submit_btn.click()
                            print(f"  ✓ {row_num}행 출품 확인 버튼 클릭!")
                            time.sleep(3)
                        except Exception as e:
                            print(f"  ✗ 제출 버튼을 찾을 수 없습니다: {e}")
                            print(f"  브라우저에서 직접 제출해주세요.")
                            input("  제출 후 Enter를 눌러주세요...")
                        break
                    elif choice == 'q':
                        print("출품을 종료합니다.")
                        return
                    else:
                        print("  잘못된 입력입니다. Enter/s/q 중 선택해주세요.")
            else:
                print(f"  {row_num}행 폼 입력 실패. 건너뜁니다.")
                input("  Enter를 눌러 다음으로 진행...")

        print(f"\n모든 상품 처리 완료! ({len(rows)}개)")

    finally:
        input("\n브라우저를 닫으려면 Enter를 누르세요...")
        driver.quit()
        print("브라우저를 종료했습니다.")


def main():
    parser = argparse.ArgumentParser(description="바이마 출품 자동화")
    parser.add_argument("--scan", action="store_true", help="출품 페이지 폼 구조 스캔 (개발용)")
    parser.add_argument("--row", type=int, default=0, help="특정 행만 출품 (예: --row 3)")
    args = parser.parse_args()

    if args.scan:
        driver = setup_visible_chrome_driver()
        try:
            if not wait_for_buyma_login(driver):
                return
            scan_form_structure(driver)
        finally:
            input("\nEnter를 눌러 브라우저를 닫습니다...")
            driver.quit()
    else:
        upload_products(specific_row=args.row)


if __name__ == "__main__":
    main()
