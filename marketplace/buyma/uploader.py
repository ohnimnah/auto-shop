"""BUYMA upload orchestration.

This module keeps browser form-filling callbacks injected from the legacy
entrypoint so behavior stays stable while orchestration moves out of
``buyma_upload.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import re
from typing import Any, Callable, Dict, List

from marketplace.buyma.failure_tracking import capture_failure_artifacts
from marketplace.buyma.mapper import buyma_title_units
from marketplace.buyma.retry_ops import safe_click
from marketplace.common.interfaces import MarketplaceRow, MarketplaceUploader
try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except Exception:  # pragma: no cover
    By = None  # type: ignore[assignment]
    Keys = None  # type: ignore[assignment]
    EC = None  # type: ignore[assignment]
    WebDriverWait = None  # type: ignore[assignment]
try:
    from tenacity import RetryError, Retrying, stop_after_attempt, wait_fixed
except Exception:  # pragma: no cover
    class RetryError(Exception):
        def __init__(self, exc: Exception | None = None):
            self._exc = exc
            self.last_attempt = type("_Attempt", (), {"exception": lambda self: exc})()

    def stop_after_attempt(_n):
        return None

    def wait_fixed(_n):
        return None

    class _AttemptCtx:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, _tb):
            if exc is not None:
                raise exc
            return False

    class Retrying:
        def __init__(self, *args, **kwargs):
            self._done = False

        def __iter__(self):
            return self

        def __next__(self):
            if self._done:
                raise StopIteration
            self._done = True
            return _AttemptCtx()
from utils.structured_logger import get_logger, log_event


def upload_products(
    *,
    specific_row: int = 0,
    upload_mode: str = "auto",
    max_items: int = 0,
    interactive: bool = True,
    get_sheets_service: Callable[[], object],
    get_sheet_name: Callable[[object], str],
    get_sheet_header_map: Callable[[object, str], Dict[str, int]],
    read_upload_rows: Callable[[object, str, int], List[Dict[str, str]]],
    setup_visible_chrome_driver: Callable[[], object],
    wait_for_buyma_login: Callable[[object], bool],
    update_cell_by_header: Callable[[object, str, int, Dict[str, int], str, str], bool],
    fill_buyma_form: Callable[[object, Dict[str, str]], object],
    handle_success_after_fill: Callable[[object, int, str, bool], tuple[bool, bool]],
    append_category_candidate: Callable[[object, Dict[str, str], Dict[str, Any]], None] | None = None,
    safe_input: Callable[[str], str],
    progress_status_header: str,
    status_uploading: str,
    status_completed: str,
) -> None:
    """Main upload loop for BUYMA."""
    logger = get_logger("auto_shop.upload")
    print("바이마 출품 자동화 시작합니다\n")
    print(f"업로드 모드: {upload_mode}\n")

    service = get_sheets_service()
    sheet_name = get_sheet_name(service)
    header_map = get_sheet_header_map(service, sheet_name)
    print(f"시트: {sheet_name}")

    rows = read_upload_rows(service, sheet_name, specific_row)
    if not rows:
        print("출품 대상이 없습니다. (BUYMA URL + DB상품 + KEY 바이마판매가 필요)")
        return

    print(f"출품 행수: {len(rows)}개품\n")
    for row in rows:
        print(f"  {row['row_num']}행 {row['brand']} - {row['product_name_kr']} (JPY {row['buyma_price']})")
    print()

    driver = setup_visible_chrome_driver()
    keep_browser_open = False
    try:
        if not wait_for_buyma_login(driver):
            print("로그인 실패. 종료합니다.")
            return

        processed = 0
        for index, row_data in enumerate(rows):
            if max_items > 0 and processed >= max_items:
                break

            row_num = row_data["row_num"]
            print(f"\n{'=' * 60}")
            print(f"  [{index + 1}/{len(rows)}] {row_num}행 처리 중")
            print(f"{'=' * 60}")

            if update_cell_by_header(
                service,
                sheet_name,
                row_num,
                header_map,
                progress_status_header,
                status_uploading,
            ):
                print(f"  {row_num}행 상태 업데이트: {status_uploading}")
            processed += 1
            log_event(logger, logging.INFO, "upload_started", row=row_num, brand=row_data.get("brand", ""))
            try:
                fill_output = None
                for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True):
                    with attempt:
                        fill_output = fill_buyma_form(driver, row_data)
            except RetryError as retry_exc:
                last = retry_exc.last_attempt.exception()
                error_text = str(last or retry_exc)
                capture_failure_artifacts(driver, int(row_num), "fill_buyma_form", error_text, retry_count=3)
                log_event(
                    logger,
                    logging.ERROR,
                    "upload_fill_failed",
                    row=row_num,
                    step="fill_buyma_form",
                    error=error_text,
                    retry_count=3,
                )
                if update_cell_by_header(service, sheet_name, row_num, header_map, progress_status_header, "오류"):
                    print(f"  {row_num}행 상태 업데이트: 오류")
                continue
            except Exception as exc:
                capture_failure_artifacts(driver, int(row_num), "fill_buyma_form", str(exc), retry_count=0)
                log_event(
                    logger,
                    logging.ERROR,
                    "upload_fill_failed",
                    row=row_num,
                    step="fill_buyma_form",
                    error=str(exc),
                    retry_count=0,
                )
                if update_cell_by_header(service, sheet_name, row_num, header_map, progress_status_header, "오류"):
                    print(f"  {row_num}행 상태 업데이트: 오류")
                continue
            if isinstance(fill_output, dict):
                fill_result = str(fill_output.get("result", "error"))
                category_diag = dict(fill_output.get("category_diag") or {})
            else:
                fill_result = str(fill_output)
                category_diag = {}

            if fill_result == "success":
                should_continue, fully_submitted = handle_success_after_fill(
                    driver,
                    row_num,
                    upload_mode,
                    interactive,
                )
                if not should_continue:
                    return
                if fully_submitted:
                    if update_cell_by_header(
                        service,
                        sheet_name,
                        row_num,
                        header_map,
                        progress_status_header,
                        status_completed,
                    ):
                        print(f"  {row_num}행 상태 업데이트: {status_completed}")
                    category_diag["final_result"] = "success"
                elif upload_mode == "auto":
                    if update_cell_by_header(
                        service,
                        sheet_name,
                        row_num,
                        header_map,
                        progress_status_header,
                        "오류",
                    ):
                        print(f"  {row_num}행 상태 업데이트: 오류")
                    if not category_diag.get("final_result"):
                        category_diag["final_result"] = "failed"
            elif fill_result == "manual_review":
                print(f"  {row_num}행은 상품명 등 수동 확인이 필요합니다. 현재 브라우저 화면을 확인해주세요.")
                category_diag["final_result"] = "manual_review"
                keep_browser_open = True
                if append_category_candidate:
                    try:
                        append_category_candidate(service, row_data, category_diag)
                    except Exception as exc:
                        print(f"  △ category_mapping_candidates 기록 실패: {exc}")
                if interactive:
                    safe_input("  수정 또는 확인 후 Enter를 눌러주세요..")
                return
            else:
                print(f"  {row_num}행 상품입력 실패. 건너뜁니다")
                capture_failure_artifacts(driver, int(row_num), "fill_result_error", fill_result, retry_count=0)
                log_event(
                    logger,
                    logging.ERROR,
                    "upload_row_failed",
                    row=row_num,
                    step="fill_result_error",
                    error=fill_result,
                    retry_count=0,
                )
                if update_cell_by_header(
                    service,
                    sheet_name,
                    row_num,
                    header_map,
                    progress_status_header,
                    "오류",
                ):
                    print(f"  {row_num}행 상태 업데이트: 오류")
                if not category_diag.get("final_result"):
                    category_diag["final_result"] = "error"
                if interactive:
                    safe_input("  Enter를 눌러 다음으로 진행...")

            # 후보 기록: 기타/실패/manual_review 중심
            if append_category_candidate:
                final_result = str(category_diag.get("final_result", "") or "").lower()
                failure_stage = str(category_diag.get("failure_stage", "") or "")
                if final_result in {"other", "failed", "error", "manual_review"} or failure_stage:
                    try:
                        append_category_candidate(service, row_data, category_diag)
                    except Exception as exc:
                        print(f"  △ category_mapping_candidates 기록 실패: {exc}")

        print(f"\n모든 상품 처리 완료! ({len(rows)}건)")

    finally:
        if keep_browser_open:
            print("\n브라우저를 열어둔 상태로 유지합니다. 확인 후 직접 닫아주세요.")
        else:
            if interactive:
                safe_input("\n브라우저를 모두 닫으면 Enter를 눌러주세요...")
            driver.quit()
            print("브라우저가 종료되었습니다.")


def apply_buyma_core_fields(
    driver,
    *,
    payload: Dict[str, object],
    comment_template: str,
    sleep_fn,
    scroll_and_click,
    set_text_input_value,
    detect_title_input_issue,
    build_buyma_title_retry_candidates,
) -> str:
    """Fill core BUYMA fields except category/options/images."""
    brand_en = payload["brand"]
    name_en = payload["name_en"]
    color_en = payload["color_en"]

    try:
        name_fields = driver.find_elements(By.CSS_SELECTOR, ".bmm-c-field__input > input.bmm-c-text-field")
        if name_fields:
            maxlength_raw = (name_fields[0].get_attribute("maxlength") or "").strip()
            title_limit = int(maxlength_raw) if maxlength_raw.isdigit() else 60
            title_candidates = build_buyma_title_retry_candidates(brand_en, name_en, color_en, title_limit)
            title_ok = False
            last_issue = ""
            final_title = ""
            for idx, candidate in enumerate(title_candidates, start=1):
                set_text_input_value(driver, name_fields[0], candidate)
                sleep_fn(0.1)
                issue = detect_title_input_issue(name_fields[0], candidate)
                if not issue:
                    title_ok = True
                    final_title = candidate
                    break
                last_issue = issue
                print(f"  △ 상품명 재시도 {idx}/{len(title_candidates)} 실패: {issue} -> '{candidate}'")

            if title_ok:
                print(f"  ✓ 상품명 입력: {final_title}")
            else:
                print(f"  ! 상품명 수동 확인 필요: {last_issue or '알 수 없는 제목 입력 오류'}")
                return "manual_review"
        else:
            print("  △ 상품명 입력란을 찾을 수 없습니다")
    except Exception as exc:
        print(f"  ✗ 상품명 입력 실패: {exc}")
        return "manual_review"

    brand = payload["brand"]
    if brand:
        try:
            brand_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='ブランド名を入力']")
            scroll_and_click(driver, brand_input)
            brand_input.clear()
            brand_input.send_keys(brand)
            sleep_fn(1.2)
            brand_input.send_keys(Keys.ARROW_DOWN)
            sleep_fn(0.2)
            brand_input.send_keys(Keys.ENTER)
            print(f"  ✓ 브랜드 입력/선택: {brand}")
        except Exception as exc:
            print(f"  ✗ 브랜드 입력 실패: {exc}")

    return "success"


def detect_title_input_issue(name_input, intended_title: str) -> str:
    """Check whether BUYMA title input applied the intended value cleanly."""
    try:
        actual_value = (name_input.get_attribute("value") or "").strip()
        maxlength_raw = (name_input.get_attribute("maxlength") or "").strip()
        validation_message = (name_input.get_attribute("validationMessage") or "").strip()

        maxlength = int(maxlength_raw) if maxlength_raw.isdigit() else 0
        effective_limit = maxlength if maxlength > 0 else 60
        intended_units = buyma_title_units(intended_title)
        actual_units = buyma_title_units(actual_value)
        if intended_units > effective_limit:
            return f"상품명 길이 초과: {intended_units}유닛 / 제한 {effective_limit}유닛"

        try:
            note_text = ""
            container = name_input.find_element(By.XPATH, "./ancestor::div[contains(@class,'bmm-c-field')][1]")
            note_nodes = container.find_elements(By.CSS_SELECTOR, ".bmm-c-field__note")
            for node in note_nodes:
                text = (node.text or "").strip()
                if "あと" in text and "文字" in text:
                    note_text = text
                    break
            if note_text:
                match = re.search(r"あと\s*([+-]?\d+)\s*文字", note_text)
                if match:
                    remaining = int(match.group(1))
                    if remaining < 0:
                        return f"상품명 길이 초과(UI): 남은 글자 {remaining}"
        except Exception:
            pass

        if actual_value != intended_title:
            if validation_message:
                return f"상품명 입력 제한: {validation_message}"
            if actual_units < intended_units:
                return f"상품명 입력값이 잘렸습니다: 입력 {intended_units}유닛 / 반영 {actual_units}유닛"
            return "상품명 입력값이 요청값과 다릅니다"

        if validation_message:
            return f"상품명 검증 메시지: {validation_message}"
    except Exception:
        return ""
    return ""


def set_text_input_value(driver, input_el, text: str, *, scroll_and_click) -> None:
    """Overwrite a text input as robustly as possible."""
    target = text or ""
    scroll_and_click(driver, input_el)
    try:
        input_el.clear()
    except Exception:
        pass
    try:
        input_el.send_keys(Keys.CONTROL, "a")
        input_el.send_keys(Keys.BACKSPACE)
    except Exception:
        pass
    input_el.send_keys(target)


def apply_buyma_post_option_fields(
    driver,
    *,
    payload: Dict[str, object],
    comment_template: str,
    sleep_fn,
    scroll_and_click,
) -> None:
    """Fill BUYMA fields that come after category/options selection."""
    try:
        deadline_date = datetime.now() + timedelta(days=89)
        deadline_str = deadline_date.strftime("%Y/%m/%d")
        deadline_input = driver.find_element(By.CSS_SELECTOR, "input.sell-term")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", deadline_input)
        sleep_fn(0.3)
        driver.execute_script(
            "var el = arguments[0]; "
            "var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; "
            "nativeInputValueSetter.call(el, arguments[1]); "
            "el.dispatchEvent(new Event('input', { bubbles: true })); "
            "el.dispatchEvent(new Event('change', { bubbles: true }));",
            deadline_input,
            deadline_str,
        )
        sleep_fn(0.5)
        print(f"  ✓ 구입기한 입력: {deadline_str}")
    except Exception as exc:
        print(f"  ✗ 구입기한 입력 실패, 수동 입력 필요: {exc}")

    try:
        target_comment = driver.execute_script("""
            function isProductCommentField(field) {
                if (!field) return false;
                var label = field.querySelector('.bmm-c-field__label, label, p');
                var txt = label ? (label.textContent || '').replace(/\\s+/g, ' ').trim() : '';
                return txt.indexOf('?品?メ?ト') >= 0;
            }

            var fields = document.querySelectorAll('.bmm-c-field');
            for (var i = 0; i < fields.length; i++) {
                if (isProductCommentField(fields[i])) {
                    var ta = fields[i].querySelector('textarea.bmm-c-textarea');
                    if (ta && !ta.closest('.sell-variation')) return ta;
                }
            }

            var allFields = document.querySelectorAll('.bmm-c-field');
            for (var j = 0; j < allFields.length; j++) {
                if (allFields[j].closest('.sell-variation')) continue;
                var label2 = allFields[j].querySelector('.bmm-c-field__label, label, p');
                var txt2 = label2 ? (label2.textContent || '').trim() : '';
                if (txt2.indexOf('?品?メ?ト') >= 0) {
                    var ta2 = allFields[j].querySelector('textarea.bmm-c-textarea, textarea');
                    if (ta2) return ta2;
                }
            }

            var labels = document.querySelectorAll('label[for], .bmm-c-field__label[for]');
            for (var k = 0; k < labels.length; k++) {
                var lt = (labels[k].textContent || '').trim();
                if (lt.indexOf('商品コメント') < 0) continue;
                var forId = labels[k].getAttribute('for') || '';
                if (!forId) continue;
                var ta3 = document.getElementById(forId);
                if (ta3 && ta3.tagName === 'TEXTAREA') return ta3;
            }

            var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            var node;
            while ((node = walker.nextNode())) {
                var t = (node.nodeValue || '').replace(/\\s+/g, ' ').trim();
                if (!t || t.indexOf('商品コメント') < 0) continue;
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
            scroll_and_click(driver, target_comment)
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
                target_comment,
                comment_template,
            )
            if wrote:
                print("  ✓ 상품코멘트(必須) 입력 (고정 템플릿)")
            else:
                print("  ✗ 상품코멘트 입력 시도했으나 확인 실패")
        else:
            print("  △ 商品コメント 필드를 찾지 못했습니다. 수동 입력 필요")
    except Exception as exc:
        print(f"  ✗ 상품 설명 입력 실패: {exc}")

    try:
        ocs_checked = driver.execute_script("""
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
        if ocs_checked == "clicked":
            print("  ✓ 배송방법 OCS 체크")
        elif ocs_checked == "already":
            print("  ✓ 배송방법 OCS 이미 체크됨")
        else:
            print("  △ OCS 체크박스를 찾지 못했습니다. 수동 선택 필요")
    except Exception as exc:
        print(f"  ✗ 배송방법 선택 실패: {exc}")

    # 관세 관련 체크박스 자동 선택
    try:
        customs_checked = driver.execute_script("""
            function norm(t) {
                return (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            }
            var keywords = ['関税', '관세', 'duty', 'customs'];
            var rows = document.querySelectorAll('.bmm-c-form-table__table tbody tr, .bmm-c-field, .bmm-c-form-table tr');
            for (var i = 0; i < rows.length; i++) {
                var text = norm(rows[i].textContent || '');
                var matched = false;
                for (var k = 0; k < keywords.length; k++) {
                    if (text.indexOf(keywords[k]) >= 0) {
                        matched = true;
                        break;
                    }
                }
                if (!matched) continue;

                var cb = rows[i].querySelector('input[type="checkbox"]');
                if (!cb) {
                    var labels = rows[i].querySelectorAll('label');
                    for (var j = 0; j < labels.length; j++) {
                        var forId = labels[j].getAttribute('for') || '';
                        if (!forId) continue;
                        var linked = document.getElementById(forId);
                        if (linked && linked.type === 'checkbox') {
                            cb = linked;
                            break;
                        }
                    }
                }

                if (cb && !cb.checked) {
                    cb.click();
                    return 'clicked';
                } else if (cb && cb.checked) {
                    return 'already';
                }
            }
            return 'not_found';
        """)
        if customs_checked == "clicked":
            print("  ✓ 관세 관련 체크박스 선택 완료")
        elif customs_checked == "already":
            print("  ✓ 관세 관련 체크박스 이미 선택됨")
        else:
            print("  △ 관세 관련 체크박스를 찾지 못했습니다.")
    except Exception as exc:
        print(f"  ⚠ 관세 관련 체크 실패: {exc}")

    buyma_price = payload["buyma_price_digits"]
    if buyma_price:
        try:
            adjusted_price = payload["adjusted_price"]
            filled_count = 0
            product_price_input = driver.execute_script("""
                function findInputFromField(field) {
                    if (!field) return null;
                    var candidates = field.querySelectorAll('input.bmm-c-text-field, input[type="text"], input[type="number"]');
                    for (var k = 0; k < candidates.length; k++) {
                        var c = candidates[k];
                        var meta = ((c.getAttribute('name') || '') + ' ' + (c.getAttribute('id') || '') + ' ' + (c.getAttribute('placeholder') || '') + ' ' + (c.getAttribute('class') || '')).toLowerCase();
                        if (meta.indexOf('数量') >= 0 || meta.indexOf('qty') >= 0 || meta.indexOf('stock') >= 0 || meta.indexOf('在庫') >= 0) {
                            continue;
                        }
                        return c;
                    }
                    return null;
                }

                function normText(t) {
                    return (t || '').replace(/\\\\s+/g, ' ').trim();
                }

                var fields = document.querySelectorAll('.bmm-c-field, .bmm-c-form-table__body tr, .bmm-c-form-table tr');
                for (var i = 0; i < fields.length; i++) {
                    var root = fields[i];
                    var txt = normText(root.textContent || '');
                    var hasPriceKeyword = (txt.indexOf('商品価格') >= 0 || txt.indexOf('販売価格') >= 0 || txt.indexOf('価格') >= 0);
                    var hasQtyKeyword = (txt.indexOf('買付できる合計数量') >= 0 || txt.indexOf('合計数量') >= 0 || txt.indexOf('数量') >= 0 || txt.indexOf('在庫') >= 0);
                    if (hasPriceKeyword && !hasQtyKeyword) {
                        var ipt = findInputFromField(fields[i]);
                        if (ipt) return ipt;
                    }
                }

                var labels = document.querySelectorAll('label[for], .bmm-c-field__label[for]');
                for (var j = 0; j < labels.length; j++) {
                    var lt = normText(labels[j].textContent || '');
                    var isPrice = (lt.indexOf('商品価格') >= 0 || lt.indexOf('販売価格') >= 0 || lt.indexOf('価格') >= 0);
                    var isQty = (lt.indexOf('買付できる合計数量') >= 0 || lt.indexOf('合計数量') >= 0 || lt.indexOf('数量') >= 0 || lt.indexOf('在庫') >= 0);
                    if (!isPrice || isQty) continue;
                    var idv = labels[j].getAttribute('for') || '';
                    if (!idv) continue;
                    var ipt2 = document.getElementById(idv);
                    if (ipt2 && ipt2.tagName === 'INPUT') return ipt2;
                }

                var allInputs = document.querySelectorAll('input.bmm-c-text-field, input[type="text"], input[type="number"]');
                for (var m = 0; m < allInputs.length; m++) {
                    var ii = allInputs[m];
                    var mm = ((ii.getAttribute('name') || '') + ' ' + (ii.getAttribute('id') || '') + ' ' + (ii.getAttribute('placeholder') || '') + ' ' + (ii.getAttribute('class') || '')).toLowerCase();
                    var mmPrice = (mm.indexOf('商品価格') >= 0 || mm.indexOf('販売価格') >= 0 || mm.indexOf('price') >= 0 || mm.indexOf('価格') >= 0);
                    var mmQty = (mm.indexOf('qty') >= 0 || mm.indexOf('quantity') >= 0 || mm.indexOf('数量') >= 0 || mm.indexOf('stock') >= 0 || mm.indexOf('在庫') >= 0);
                    if (mmPrice && !mmQty) return ii;
                }
                return null;
            """)

            if product_price_input is not None:
                try:
                    scroll_and_click(driver, product_price_input)
                    product_price_input.clear()
                    product_price_input.send_keys(str(adjusted_price))
                    filled_count += 1
                except Exception:
                    pass

            if filled_count == 0:
                try:
                    price_by_placeholder = driver.find_element(
                        By.CSS_SELECTOR,
                        "input[placeholder*='商品価格'], input[placeholder*='販売価格'], input[placeholder*='価格']",
                    )
                    if price_by_placeholder.is_displayed() and price_by_placeholder.is_enabled():
                        scroll_and_click(driver, price_by_placeholder)
                        price_by_placeholder.clear()
                        price_by_placeholder.send_keys(str(adjusted_price))
                        filled_count += 1
                except Exception:
                    pass

            if filled_count:
                print(f"  ✓ 판매가 입력: ¥{adjusted_price} (엑셀값-1)")
            else:
                print("  ✗ 가격 입력 필드를 찾을 수 없습니다")
        except Exception as exc:
            print(f"  ✗ 판매가 입력 실패: {exc}")

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
                    var txt = (cur.textContent || '').replace(/\\\\s+/g, ' ').trim();
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
                return text.indexOf('買付できる合計数量') >= 0 ||
                       text.indexOf('合計数量') >= 0 ||
                       text.indexOf('買付可能数量') >= 0 ||
                       text.indexOf('購入可能数量') >= 0 ||
                       text.indexOf('数量') >= 0 ||
                       text.indexOf('quantity') >= 0 ||
                       text.indexOf('qty') >= 0;
            }

            var byPlaceholder = document.querySelector("input[placeholder*='買付できる合計数量'], input[placeholder*='合計数量'], input[placeholder*='買付可能数量'], input[placeholder*='購入可能数量'], input[aria-label*='買付できる合計数量'], input[aria-label*='合計数量'], input[aria-label*='買付可能数量'], input[aria-label*='購入可能数量'], input[type='tel'][placeholder*='合計数量'], input[type='tel'][aria-label*='合計数量']");
            if (byPlaceholder && isVisible(byPlaceholder)) return byPlaceholder;

            var fields = document.querySelectorAll('.bmm-c-field, .bmm-c-form-table__body tr, .bmm-c-form-table tr');
            for (var i = 0; i < fields.length; i++) {
                var root = fields[i];
                var txt = (root.textContent || '').replace(/\\\\s+/g, ' ').trim();
                if (hasQtyHint(txt)) {
                    var ipt = root.querySelector("input.bmm-c-text-field, input[type='text'], input[type='number'], input[type='tel']");
                    if (ipt && isVisible(ipt)) return ipt;
                }
            }

            var labels = document.querySelectorAll('label, .bmm-c-field__label, .bmm-c-form-table__header, .bmm-c-form-table__label');
            for (var i2 = 0; i2 < labels.length; i2++) {
                var label = labels[i2];
                var labelText = (label.textContent || '').replace(/\\\\s+/g, ' ').trim();
                if (!hasQtyHint(labelText)) continue;
                var forId = label.getAttribute('for') || '';
                if (forId) {
                    var direct = document.getElementById(forId);
                    if (direct && direct.tagName === 'INPUT' && isVisible(direct)) return direct;
                }
                var labelInput = label.querySelector("input.bmm-c-text-field, input[type='text'], input[type='number'], input[type='tel']");
                if (labelInput && isVisible(labelInput)) return labelInput;
                var parent = label.parentElement;
                for (var up0 = 0; parent && up0 < 4; up0++) {
                    var parentInput = parent.querySelector("input.bmm-c-text-field, input[type='text'], input[type='number'], input[type='tel']");
                    if (parentInput && isVisible(parentInput)) return parentInput;
                    parent = parent.parentElement;
                }
            }

            var allNodes = document.querySelectorAll("p, span, div, th, td, label");
            for (var z = 0; z < allNodes.length; z++) {
                var nt = (allNodes[z].textContent || '').replace(/\\\\s+/g, ' ').trim();
                if (!hasQtyHint(nt)) continue;
                var c = allNodes[z];
                for (var upz = 0; c && upz < 6; upz++) {
                    var near = c.querySelector("input.bmm-c-text-field, input[type='text'], input[type='number'], input[type='tel']");
                    if (near && isVisible(near)) return near;
                    c = c.parentElement;
                }
            }

            var allInputs = document.querySelectorAll("input.bmm-c-text-field, input[type='text'], input[type='number'], input[type='tel']");
            for (var j = 0; j < allInputs.length; j++) {
                var ip = allInputs[j];
                if (!isVisible(ip)) continue;
                var meta = metaText(ip).toLowerCase();
                if (meta.indexOf('price') >= 0 || meta.indexOf('商品価格') >= 0 || meta.indexOf('販売価格') >= 0) continue;
                var around = nearestText(ip);
                if (around.indexOf('あと') >= 0 && around.indexOf('文字') >= 0) continue;
                if (hasQtyHint(around.toLowerCase())) {
                    return ip;
                }
                if (hasQtyHint(meta)) {
                    return ip;
                }
            }

            for (var k = 0; k < allInputs.length; k++) {
                var ip2 = allInputs[k];
                if (!isVisible(ip2)) continue;
                var meta2 = metaText(ip2).toLowerCase();
                if (meta2.indexOf('price') >= 0 || meta2.indexOf('商品価格') >= 0 || meta2.indexOf('販売価格') >= 0) continue;
                if (meta2.indexOf('stock') >= 0 || meta2.indexOf('在庫') >= 0) continue;
                var around2 = nearestText(ip2);
                if (around2.indexOf('あと') >= 0 && around2.indexOf('文字') >= 0) continue;
                if ((ip2.type || '').toLowerCase() === 'number' || (ip2.getAttribute('inputmode') || '').toLowerCase() === 'numeric' || hasQtyHint(meta2)) {
                    return ip2;
                }
            }

            var priceInput = null;
            for (var p = 0; p < allInputs.length; p++) {
                var cand = allInputs[p];
                var metaP = metaText(cand);
                var aroundP = nearestText(cand);
                if (metaP.indexOf('商品価格') >= 0 || metaP.indexOf('販売価格') >= 0 || aroundP.indexOf('商品価格') >= 0 || aroundP.indexOf('販売価格') >= 0) {
                    priceInput = cand;
                    break;
                }
            }
            if (priceInput) {
                var container = priceInput.parentElement;
                for (var up = 0; container && up < 5; up++) {
                    var nearby = container.querySelectorAll("input.bmm-c-text-field, input[type='text'], input[type='number'], input[type='tel']");
                    for (var q = 0; q < nearby.length; q++) {
                        var n = nearby[q];
                        if (n === priceInput || !isVisible(n)) continue;
                        var metaN = metaText(n).toLowerCase();
                        if (metaN.indexOf('stock') >= 0 || metaN.indexOf('在庫') >= 0) continue;
                        return n;
                    }
                    container = container.parentElement;
                }
            }

            return null;
        """)

        if qty_input is not None:
            try:
                scroll_and_click(driver, qty_input)
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
                        var txt = (cur.textContent || '').replace(/\\\\s+/g, ' ').trim();
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
            print("  ✓ 買付できる合計数量 입력: 100")
        else:
            print("  △ 買付できる合計数量 입력칸을 찾지 못했습니다. 수동 입력 필요")
            if qty_candidates:
                for idx, cand in enumerate(qty_candidates[:8], 1):
                    around = (cand.get("around") or "")[:120]
                    print(
                        f"    후보 {idx}: type={cand.get('type','')} name={cand.get('name','')} id={cand.get('id','')} "
                        f"placeholder={cand.get('placeholder','')} aria={cand.get('aria','')} inputmode={cand.get('inputmode','')} around={around}"
                    )
    except Exception as exc:
        print(f"  △ 合計数量 입력 실패: {exc}")

    try:
        selects = driver.find_elements(By.CSS_SELECTOR, ".Select")
        city_count = 0
        for sel_container in selects:
            try:
                val_label = sel_container.find_element(By.CSS_SELECTOR, ".Select-value-label")
                if "選択なし" in val_label.text:
                    scroll_and_click(driver, sel_container.find_element(By.CSS_SELECTOR, ".Select-control"))
                    sleep_fn(0.5)
                    opts = driver.find_elements(By.CSS_SELECTOR, ".Select-option")
                    for opt in opts:
                        if "ソウル" in opt.text:
                            opt.click()
                            city_count += 1
                            sleep_fn(0.3)
                            break
            except Exception:
                continue
        if city_count:
            print(f"  ✓ 도시 선택: ソウル({city_count}개)")
    except Exception as exc:
        print(f"  ✗ 도시 선택 실패, 자동 선택 필요: {exc}")


def fill_buyma_form(
    driver,
    row_data: MarketplaceRow,
    *,
    build_buyma_form_payload,
    build_buyma_category_plan,
    apply_buyma_category_selection,
    apply_buyma_option_selection,
    apply_buyma_post_option_fields,
    upload_product_images,
    normalize_actual_size_for_upload,
    expand_color_abbreviations,
    split_color_values,
    resolve_image_files,
    category_corrector,
    select_category_by_arrow,
    find_best_option_by_arrow,
    buyma_sell_url: str,
    dismiss_overlay,
    sleep_fn,
    comment_template: str,
    scroll_and_click,
    set_text_input_value,
    detect_title_input_issue,
    build_buyma_title_retry_candidates,
    select_color_system,
    try_add_color_row,
    fill_color_supplement,
    select_size_by_select_controls,
    fill_size_table_rows,
    force_select_variation_none_sequence,
    force_select_shitei_nashi_global,
    check_no_variation_option,
    force_reference_size_shitei_nashi,
    fill_size_edit_details,
    enable_size_selection_ui,
    fill_size_text_inputs,
    fill_size_supplement,
) -> Dict[str, Any]:
    """Marketplace BUYMA form fill orchestration."""

    def _is_apparel_category(diag: Dict[str, Any]) -> bool:
        standard = str(diag.get("standard_category", "") or "").upper()
        if standard.startswith("TOP_") or standard in {"OUTER", "PANTS", "HOME_PAJAMA"}:
            return True
        middle = str(diag.get("target_buyma_middle_category", "") or "")
        for token in ("トップス", "ボトムス", "パンツ", "アウター", "ジャケット", "ワンピース", "インナー"):
            if token in middle:
                return True
        return False

    category_diag: Dict[str, Any] = {}
    try:
        try:
            payload = build_buyma_form_payload(
                row_data,
                normalize_actual_size_for_upload=normalize_actual_size_for_upload,
                expand_color_abbreviations=expand_color_abbreviations,
                split_color_values=split_color_values,
                resolve_image_files=resolve_image_files,
            )
        except TypeError as exc:
            # Compatibility: mapper method style (map_row(row_data)) does not accept
            # keyword helper injections.
            if "unexpected keyword argument" not in str(exc):
                raise
            payload = build_buyma_form_payload(row_data)
        driver.get(buyma_sell_url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".bmm-c-heading__ttl"))
        )
        sleep_fn(3)

        row_num = row_data["row_num"]
        print(f"\n--- [{row_num}번째 바이마 출품 자동입력 시작 ---")
        print(f"  상품명: {payload['product_name_kr']}")
        print(f"  브랜드: {payload['brand']}")
        print(f"  바이마 판매가: {row_data['buyma_price']}")

        dismiss_overlay(driver)

        try:
            category_plan = build_buyma_category_plan(
                row_data,
                category_corrector=category_corrector,
            )
            category_diag = apply_buyma_category_selection(
                driver,
                category_plan,
                select_category_by_arrow=select_category_by_arrow,
                find_best_option_by_arrow=find_best_option_by_arrow,
            )
            actual_mid = str(category_diag.get("actual_selected_middle_category", "") or "")
            actual_child = str(category_diag.get("actual_selected_child_category", "") or "")
            if "その他" in actual_mid or "その他" in actual_child:
                # 의류 카테고리의 '기타' 선택은 실패로 격상한다.
                if _is_apparel_category(category_diag):
                    category_diag["final_result"] = "failed"
                    if not category_diag.get("failure_stage"):
                        category_diag["failure_stage"] = "middle_other" if "その他" in actual_mid else "child_other"
                    category_diag["category_selection_success"] = False
                else:
                    category_diag["final_result"] = category_diag.get("final_result") or "other"
                    category_diag["category_selection_success"] = False
        except Exception as exc:
            print(f"  ✗ 카테고리 선택 실패: {exc}")
            category_diag = {
                "category_selection_success": False,
                "failure_stage": "category_exception",
                "final_result": "failed",
                "fallback_used": False,
                "standard_category": (category_plan.get("standard_category", "") if "category_plan" in locals() else ""),
                "cat_source": (category_plan.get("cat_source", "") if "category_plan" in locals() else ""),
                "semantic_fallback_used": bool(category_plan.get("semantic_fallback_used", False)) if "category_plan" in locals() else False,
                "target_buyma_parent_category": (category_plan.get("cat1", "") if "category_plan" in locals() else ""),
                "target_buyma_middle_category": (category_plan.get("cat2", "") if "category_plan" in locals() else ""),
                "target_buyma_child_category": (category_plan.get("cat3", "") if "category_plan" in locals() else ""),
                "actual_selected_parent_category": "",
                "actual_selected_middle_category": "",
                "actual_selected_child_category": "",
                "mapping_table_used": bool(category_plan.get("mapping_table_used", False)) if "category_plan" in locals() else False,
                "legacy_used": bool(category_plan.get("legacy_used", False)) if "category_plan" in locals() else False,
            }

        if str(category_diag.get("final_result", "")).lower() in {"other", "failed"}:
            print("  △ 카테고리 선택 결과가 기타/실패로 판단되어 자동 진행을 중단합니다.")
            return {"result": "error", "category_diag": category_diag}

        core_fill_result = apply_buyma_core_fields(
            driver,
            payload=payload,
            comment_template=comment_template,
            sleep_fn=sleep_fn,
            scroll_and_click=scroll_and_click,
            set_text_input_value=set_text_input_value,
            detect_title_input_issue=detect_title_input_issue,
            build_buyma_title_retry_candidates=build_buyma_title_retry_candidates,
        )
        if core_fill_result != "success":
            return {"result": core_fill_result, "category_diag": category_diag}

        apply_buyma_option_selection(
            driver,
            buyma_sell_url=buyma_sell_url,
            color=payload["color"],
            color_values=payload["color_values"],
            size_text=payload["size_text"],
            actual_size_text=payload["actual_size_text"],
            sleep_fn=sleep_fn,
            scroll_and_click=scroll_and_click,
            select_color_system=select_color_system,
            try_add_color_row=try_add_color_row,
            fill_color_supplement=fill_color_supplement,
            select_size_by_select_controls=select_size_by_select_controls,
            fill_size_table_rows=fill_size_table_rows,
            force_select_variation_none_sequence=force_select_variation_none_sequence,
            force_select_shitei_nashi_global=force_select_shitei_nashi_global,
            check_no_variation_option=check_no_variation_option,
            force_reference_size_shitei_nashi=force_reference_size_shitei_nashi,
            fill_size_edit_details=fill_size_edit_details,
            enable_size_selection_ui=enable_size_selection_ui,
            fill_size_text_inputs=fill_size_text_inputs,
            fill_size_supplement=fill_size_supplement,
        )
        apply_buyma_post_option_fields(
            driver,
            payload=payload,
            comment_template=comment_template,
            sleep_fn=sleep_fn,
            scroll_and_click=scroll_and_click,
        )

        upload_product_images(driver, payload["image_files"], sleep_fn=sleep_fn)
        return {"result": "success", "category_diag": category_diag}
    except Exception as exc:
        print(f"  ✗ 이미지 업로드 오류: {exc}")
        if not category_diag:
            category_diag = {
                "category_selection_success": False,
                "failure_stage": "upload_exception",
                "final_result": "error",
                "fallback_used": False,
                "standard_category": "",
                "cat_source": "",
                "semantic_fallback_used": False,
                "target_buyma_parent_category": "",
                "target_buyma_middle_category": "",
                "target_buyma_child_category": "",
                "actual_selected_parent_category": "",
                "actual_selected_middle_category": "",
                "actual_selected_child_category": "",
                "mapping_table_used": False,
                "legacy_used": False,
            }
        return {"result": "error", "category_diag": category_diag}


class BuymaUploaderAdapter(MarketplaceUploader):
    """Marketplace uploader adapter over existing BUYMA orchestration."""

    def __init__(self, *, fill_form_fn, upload_rows_fn) -> None:
        self._fill_form_fn = fill_form_fn
        self._upload_rows_fn = upload_rows_fn

    def fill_form(self, driver, row_data: MarketplaceRow) -> str:
        return self._fill_form_fn(driver, row_data)

    def upload_rows(
        self,
        *,
        specific_row: int = 0,
        upload_mode: str = "auto",
        max_items: int = 0,
        interactive: bool = True,
    ) -> None:
        self._upload_rows_fn(
            specific_row=specific_row,
            upload_mode=upload_mode,
            max_items=max_items,
            interactive=interactive,
        )

