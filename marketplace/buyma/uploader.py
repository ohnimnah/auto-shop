"""BUYMA upload orchestration.

This module keeps browser form-filling callbacks injected from the legacy
entrypoint so behavior stays stable while orchestration moves out of
``buyma_upload.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Dict, List

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


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
    fill_buyma_form: Callable[[object, Dict[str, str]], str],
    handle_success_after_fill: Callable[[object, int, str, bool], tuple[bool, bool]],
    safe_input: Callable[[str], str],
    progress_status_header: str,
    status_uploading: str,
    status_completed: str,
) -> None:
    """Main upload loop for BUYMA."""
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

            fill_result = fill_buyma_form(driver, row_data)

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
            elif fill_result == "manual_review":
                print(f"  {row_num}행은 상품명 등 수동 확인이 필요합니다. 현재 브라우저 화면을 확인해주세요.")
                keep_browser_open = True
                if interactive:
                    safe_input("  수정 또는 확인 후 Enter를 눌러주세요..")
                return
            else:
                print(f"  {row_num}행 상품입력 실패. 건너뜁니다")
                if update_cell_by_header(
                    service,
                    sheet_name,
                    row_num,
                    header_map,
                    progress_status_header,
                    "오류",
                ):
                    print(f"  {row_num}행 상태 업데이트: 오류")
                if interactive:
                    safe_input("  Enter를 눌러 다음으로 진행...")

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
                    return (t || '').replace(/\s+/g, ' ').trim();
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
                print(f"  ✓ 판매가 입력: ¥{adjusted_price} (엑셀값-10)")
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
                var txt = (root.textContent || '').replace(/\s+/g, ' ').trim();
                if (hasQtyHint(txt)) {
                    var ipt = root.querySelector("input.bmm-c-text-field, input[type='text'], input[type='number'], input[type='tel']");
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
                var nt = (allNodes[z].textContent || '').replace(/\s+/g, ' ').trim();
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
