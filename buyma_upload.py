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
from datetime import datetime, timedelta
import glob
import json
import os
import re
import sys

# 런처 subprocess 로그가 OS 로케일과 무관하게 UTF-8로 흐르도록 고정한다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import time
from typing import Any, Dict, List, Tuple

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
from config.config_service import load_config as load_profile_config
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
CATEGORY_MAPPING_CANDIDATES_SHEET = "category_mapping_candidates"
CATEGORY_MAPPING_CANDIDATES_COLUMNS = [
    "collected_at",
    "product_name",
    "musinsa_sku",
    "product_url",
    "standard_category",
    "gender",
    "musinsa_category_large",
    "musinsa_category_middle",
    "musinsa_category_small",
    "target_buyma_parent_category",
    "target_buyma_middle_category",
    "target_buyma_child_category",
    "actual_selected_parent_category",
    "actual_selected_middle_category",
    "actual_selected_child_category",
    "failure_stage",
    "fallback_used",
    "final_result",
    "review_status",
    "reviewer_note",
]

DEFAULT_UPLOAD_COLUMNS = {
    "url": "B",
    "brand": "C",
    "brand_en": "D",
    "product_name_kr": "E",
    "product_name_en": "F",
    "musinsa_sku": "G",
    "color_kr": "H",
    "color_en": "I",
    "size": "J",
    "actual_size": "K",
    "price_krw": "L",
    "buyma_price": "M",
    "image_paths": "N",
    "shipping_cost": "O",
    "category_legacy_large": "V",
    "category_legacy_middle": "W",
    "category_legacy_small": "X",
    "musinsa_category_large": "W",
    "musinsa_category_middle": "X",
    "musinsa_category_small": "Y",
}
UPLOAD_COLUMNS = dict(DEFAULT_UPLOAD_COLUMNS)
UPLOAD_MAX_DATA_COLUMN = "Y"


def _get_candidate_sheet_name() -> str:
    profile_name = (os.environ.get("AUTO_SHOP_PROFILE") or "default").strip() or "default"
    try:
        config = load_profile_config(profile_name)
        tabs_cfg = ((config.get("spreadsheet") or {}).get("tabs") or {})
        return str(tabs_cfg.get("category_mapping_candidates") or CATEGORY_MAPPING_CANDIDATES_SHEET).strip() or CATEGORY_MAPPING_CANDIDATES_SHEET
    except Exception:
        return CATEGORY_MAPPING_CANDIDATES_SHEET


def _normalize_upload_columns(raw_columns: Any) -> Dict[str, str]:
    if not isinstance(raw_columns, dict):
        return {}
    normalized: Dict[str, str] = {}
    valid_keys = set(DEFAULT_UPLOAD_COLUMNS)
    for key, value in raw_columns.items():
        field = str(key or "").strip()
        column = str(value or "").strip().upper()
        if field in valid_keys and re.fullmatch(r"[A-Z]+", column):
            normalized[field] = column
    return normalized


def get_runtime_data_dir() -> str:
    """런처/CLI가 지정한 런타임 데이터 폴더를 반환한다."""
    env_data_dir = os.environ.get("AUTO_SHOP_DATA_DIR", "").strip()
    if env_data_dir:
        return os.path.abspath(os.path.expanduser(env_data_dir))
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return os.path.join(local_app_data, "auto_shop")
    return os.path.join(os.path.expanduser("~"), ".auto_shop")


def _load_sheet_runtime_config() -> None:
    """로컬에서 저장한 시트 설정파일을 읽어 기본값을 반영한다."""
    global SPREADSHEET_ID, SHEET_GIDS, SHEET_NAME, ROW_START, UPLOAD_COLUMNS, UPLOAD_MAX_DATA_COLUMN
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

        configured_columns = _normalize_upload_columns(cfg.get("upload_columns"))
        if configured_columns:
            UPLOAD_COLUMNS = {**DEFAULT_UPLOAD_COLUMNS, **configured_columns}
            print(f"업로드 시트 열 설정 적용: {configured_columns}")

        max_column = str(cfg.get("upload_max_data_column") or "").strip().upper()
        if re.fullmatch(r"[A-Z]+", max_column):
            UPLOAD_MAX_DATA_COLUMN = max_column
    except Exception as e:
        print(f"시트 설정 로드 실패: {e}")

    profile_name = (os.environ.get("AUTO_SHOP_PROFILE") or "default").strip() or "default"
    profile_config = load_profile_config(profile_name, create_if_missing=True)
    spreadsheet_cfg = profile_config.get("spreadsheet") or {}
    tabs_cfg = spreadsheet_cfg.get("tabs") or {}

    config_spreadsheet_id = common_sheet_source_mod.extract_spreadsheet_id(spreadsheet_cfg.get("id") or "")
    if config_spreadsheet_id:
        SPREADSHEET_ID = config_spreadsheet_id

    product_input_sheet = str(tabs_cfg.get("product_input") or "").strip()
    if product_input_sheet:
        SHEET_NAME = product_input_sheet


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


def _select_color_system(driver, color_system: str, row_index: int = 0) -> bool:
    return buyma_options_mod.select_color_system(
        driver,
        color_system,
        row_index=row_index,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


def _try_add_color_row(driver) -> bool:
    return buyma_options_mod.try_add_color_row(
        driver,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


def _try_add_size_row(driver, scope=None) -> bool:
    return buyma_options_mod.try_add_size_row(
        driver,
        scope=scope,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


def _select_size_by_select_controls(driver, scope, size_text: str) -> int:
    return buyma_options_mod.select_size_by_select_controls(
        driver,
        scope,
        size_text,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
        try_add_size_row_fn=_try_add_size_row,
    )


def _fill_size_supplement(driver, size_text: str) -> bool:
    return buyma_options_mod.fill_size_supplement(
        driver,
        size_text,
        scroll_and_click=_scroll_and_click,
    )


def _fill_color_supplement(driver, color_text_en: str) -> bool:
    return buyma_options_mod.fill_color_supplement(
        driver,
        color_text_en,
        scroll_and_click=_scroll_and_click,
    )


def _check_no_variation_option(driver, prefer_shitei_nashi: bool = False) -> bool:
    return buyma_options_mod.check_no_variation_option(
        driver,
        prefer_shitei_nashi=prefer_shitei_nashi,
        scroll_and_click=_scroll_and_click,
        select_option_in_select_control_fn=_select_option_in_select_control,
    )


def _force_select_shitei_nashi(driver) -> bool:
    return buyma_options_mod.force_select_shitei_nashi(
        driver,
        scroll_and_click=_scroll_and_click,
        select_option_in_select_control_fn=_select_option_in_select_control,
    )


def _force_select_shitei_nashi_global(driver) -> bool:
    return buyma_options_mod.force_select_shitei_nashi_global(
        driver,
        force_select_shitei_nashi_fn=_force_select_shitei_nashi,
        select_option_in_select_control_fn=_select_option_in_select_control,
    )


def _force_reference_size_shitei_nashi(driver, panel=None) -> bool:
    return buyma_options_mod.force_reference_size_shitei_nashi(
        driver,
        panel=panel,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
        select_option_in_select_control_fn=_select_option_in_select_control,
    )


def _force_select_variation_none_sequence(driver, panel=None) -> bool:
    return buyma_options_mod.force_select_variation_none_sequence(
        driver,
        panel=panel,
        select_option_in_select_control_fn=_select_option_in_select_control,
    )


def _enable_size_selection_ui(driver) -> bool:
    return buyma_options_mod.enable_size_selection_ui(
        driver,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


def _fill_size_text_inputs(driver, size_text: str) -> int:
    return buyma_options_mod.fill_size_text_inputs(
        driver,
        size_text,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


def _select_option_in_select_control(driver, select_el, target_text: str) -> bool:
    return buyma_options_mod.select_option_in_select_control(
        driver,
        select_el,
        target_text,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


def _fill_size_table_rows(driver, panel, size_text: str) -> int:
    return buyma_options_mod.fill_size_table_rows(
        driver,
        panel,
        size_text,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
        select_option_in_select_control_fn=_select_option_in_select_control,
        infer_reference_jp_size_fn=buyma_options_mod.infer_reference_jp_size,
    )


def _fill_size_edit_details(driver, actual_size_text: str) -> int:
    return buyma_options_mod.fill_size_edit_details(
        driver,
        actual_size_text,
        scroll_and_click=_scroll_and_click,
        extract_actual_size_rows_fn=buyma_validate_mod.extract_actual_size_rows,
        extract_actual_measure_map_fn=buyma_validate_mod.extract_actual_measure_map,
        pick_measure_value_by_label_fn=buyma_validate_mod.pick_measure_value_by_label,
    )


# ---- 카테고리 추론 매핑 ----
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


def _set_text_input_value(driver, input_el, text: str) -> None:
    return buyma_uploader_mod.set_text_input_value(
        driver,
        input_el,
        text,
        scroll_and_click=_scroll_and_click,
    )


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


def _quote_sheet_name(sheet_name: str) -> str:
    return sheet_name.replace("'", "''")


def _ensure_category_mapping_candidates_sheet(service) -> None:
    candidate_sheet_name = _get_candidate_sheet_name()
    metadata = service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        fields="sheets(properties(sheetId,title))",
    ).execute()
    sheets = metadata.get("sheets", [])
    title_to_id = {
        (s.get("properties", {}) or {}).get("title", ""): (s.get("properties", {}) or {}).get("sheetId")
        for s in sheets
    }

    if candidate_sheet_name not in title_to_id:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": candidate_sheet_name,
                            }
                        }
                    }
                ]
            },
        ).execute()

    last_col = column_index_to_letter(len(CATEGORY_MAPPING_CANDIDATES_COLUMNS) - 1)
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{_quote_sheet_name(candidate_sheet_name)}'!A1:{last_col}1",
        valueInputOption="RAW",
        body={"values": [CATEGORY_MAPPING_CANDIDATES_COLUMNS]},
    ).execute()


def _normalize_candidate_gender(row_data: Dict[str, str], product_name: str) -> str:
    raw = (row_data.get("musinsa_category_large") or "").strip()
    raw_lower = raw.lower()
    if raw in {"여성", "남성"}:
        return raw
    if "여성" in raw or "woman" in raw_lower or "women" in raw_lower:
        return "여성"
    if "남성" in raw or "man" in raw_lower or "men" in raw_lower:
        return "남성"

    detected = buyma_category_mod.detect_gender_raw(product_name or "")
    if detected == "F":
        return "여성"
    if detected == "M":
        return "남성"
    return ""


def _parse_candidate_collected_at(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _build_candidate_dedupe_keys(candidate: Dict[str, str]) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    primary = (
        (candidate.get("musinsa_sku") or "").strip(),
        (candidate.get("failure_stage") or "").strip(),
        (candidate.get("target_buyma_parent_category") or "").strip(),
        (candidate.get("target_buyma_middle_category") or "").strip(),
        (candidate.get("target_buyma_child_category") or "").strip(),
        (candidate.get("final_result") or "").strip(),
    )
    fallback = (
        (candidate.get("product_url") or "").strip(),
        (candidate.get("product_name") or "").strip(),
        (candidate.get("failure_stage") or "").strip(),
        (candidate.get("target_buyma_parent_category") or "").strip(),
        (candidate.get("target_buyma_middle_category") or "").strip(),
        (candidate.get("target_buyma_child_category") or "").strip(),
    )
    return primary, fallback


def _is_duplicate_candidate_within_24h(
    service,
    candidate: Dict[str, str],
    *,
    recent_limit: int = 1000,
) -> bool:
    candidate_sheet_name = _get_candidate_sheet_name()
    last_col = column_index_to_letter(len(CATEGORY_MAPPING_CANDIDATES_COLUMNS) - 1)
    response = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{_quote_sheet_name(candidate_sheet_name)}'!A2:{last_col}",
    ).execute()
    rows = response.get("values", [])
    if not rows:
        return False

    recent_rows = rows[-max(1, recent_limit):]
    now = datetime.now()
    threshold = now - timedelta(hours=24)
    primary_key, fallback_key = _build_candidate_dedupe_keys(candidate)
    use_primary = bool(primary_key[0])

    idx = {name: i for i, name in enumerate(CATEGORY_MAPPING_CANDIDATES_COLUMNS)}
    for row in reversed(recent_rows):
        collected = _parse_candidate_collected_at(row[idx["collected_at"]] if idx["collected_at"] < len(row) else "")
        if not collected or collected < threshold:
            continue

        row_candidate = {name: (row[i] if i < len(row) else "") for name, i in idx.items()}
        row_primary, row_fallback = _build_candidate_dedupe_keys(row_candidate)
        if use_primary:
            if row_primary == primary_key:
                return True
        elif row_fallback == fallback_key:
            return True
    return False


def _append_category_candidate_row(service, row_data: Dict[str, str], category_diag: Dict[str, Any]) -> None:
    _ensure_category_mapping_candidates_sheet(service)
    candidate_sheet_name = _get_candidate_sheet_name()

    product_name = (row_data.get("product_name_kr") or "").strip()
    candidate: Dict[str, str] = {
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "product_name": product_name,
        "musinsa_sku": str(row_data.get("musinsa_sku", "") or ""),
        "product_url": str(row_data.get("url", "") or ""),
        "standard_category": str(category_diag.get("standard_category", "") or ""),
        "gender": _normalize_candidate_gender(row_data, product_name),
        "musinsa_category_large": str(row_data.get("musinsa_category_large", "") or ""),
        "musinsa_category_middle": str(row_data.get("musinsa_category_middle", "") or ""),
        "musinsa_category_small": str(row_data.get("musinsa_category_small", "") or ""),
        "target_buyma_parent_category": str(category_diag.get("target_buyma_parent_category", "") or ""),
        "target_buyma_middle_category": str(category_diag.get("target_buyma_middle_category", "") or ""),
        "target_buyma_child_category": str(category_diag.get("target_buyma_child_category", "") or ""),
        "actual_selected_parent_category": str(category_diag.get("actual_selected_parent_category", "") or ""),
        "actual_selected_middle_category": str(category_diag.get("actual_selected_middle_category", "") or ""),
        "actual_selected_child_category": str(category_diag.get("actual_selected_child_category", "") or ""),
        "failure_stage": str(category_diag.get("failure_stage", "") or ""),
        "fallback_used": "TRUE" if bool(category_diag.get("fallback_used", False)) else "FALSE",
        "final_result": str(category_diag.get("final_result", "") or ""),
        "review_status": "NEW",
        "reviewer_note": "",
    }

    if _is_duplicate_candidate_within_24h(service, candidate):
        print("  ℹ category_mapping_candidates 중복(24h)으로 기록 생략")
        return

    row_values = [candidate.get(col, "") for col in CATEGORY_MAPPING_CANDIDATES_COLUMNS]
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{_quote_sheet_name(candidate_sheet_name)}'!A:A",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row_values]},
    ).execute()
    print("  ✓ category_mapping_candidates 후보 기록 완료")


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
        max_data_column=UPLOAD_MAX_DATA_COLUMN,
        upload_columns=UPLOAD_COLUMNS,
        progress_status_header=PROGRESS_STATUS_HEADER,
        status_completed=STATUS_COMPLETED,
        status_upload_ready=STATUS_UPLOAD_READY,
        status_thumbnails_done=STATUS_THUMBNAILS_DONE,
        specific_row=specific_row,
    )

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
    normalize_actual_size_for_upload=buyma_validate_mod.normalize_actual_size_for_upload,
    expand_color_abbreviations=buyma_options_mod.expand_color_abbreviations,
    split_color_values=buyma_options_mod.split_color_values,
    resolve_image_files=resolve_image_files,
)


def setup_visible_chrome_driver():
    return buyma_login_mod.setup_visible_chrome_driver()


def wait_for_buyma_login(driver) -> bool:
    return buyma_login_mod.wait_for_buyma_login(
        driver,
        safe_input_fn=_safe_input,
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


def _fill_buyma_form_via_modules(driver, row_data: Dict[str, str]) -> Dict[str, Any]:
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
        normalize_actual_size_for_upload=buyma_validate_mod.normalize_actual_size_for_upload,
        expand_color_abbreviations=buyma_options_mod.expand_color_abbreviations,
        split_color_values=buyma_options_mod.split_color_values,
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
        append_category_candidate=_append_category_candidate_row,
        safe_input=_safe_input,
        progress_status_header=PROGRESS_STATUS_HEADER,
        status_uploading=STATUS_UPLOADING,
        status_completed=STATUS_COMPLETED,
    )


BUYMA_UPLOADER = buyma_uploader_mod.BuymaUploaderAdapter(
    fill_form_fn=_fill_buyma_form_via_modules,
    upload_rows_fn=_upload_buyma_rows_via_modules,
)


def fill_buyma_form(driver, row_data: Dict[str, str]) -> Dict[str, Any]:
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
