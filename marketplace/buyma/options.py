"""BUYMA option-related helpers."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Dict, List

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

from marketplace.buyma.retry_ops import safe_click
from marketplace.buyma.selectors import JP_SHITEI_NASHI, JP_SIZE_SHITEI_NASHI


def infer_color_system(color_text: str) -> str:
    c = (color_text or "").strip().lower()
    if not c or c == "none":
        return "色指定なし"
    if any(k in c for k in ["black", "블랙", "검정"]):
        return "ブラック系"
    if any(k in c for k in ["white", "ivory", "오프화이트", "아이보리", "흰"]):
        return "ホワイト系"
    if any(k in c for k in ["gray", "grey", "그레이", "회색"]):
        return "グレー系"
    if any(k in c for k in ["beige", "camel", "베이지", "카멜"]):
        return "ベージュ系"
    if any(k in c for k in ["brown", "브라운", "갈색"]):
        return "ブラウン系"
    if any(k in c for k in ["pink", "핑크"]):
        return "ピンク系"
    if any(k in c for k in ["red", "레드", "빨강"]):
        return "レッド系"
    if any(k in c for k in ["orange", "오렌지"]):
        return "オレンジ系"
    if any(k in c for k in ["yellow", "옐로우", "노랑"]):
        return "イエロー系"
    if any(k in c for k in ["green", "khaki", "olive", "그린", "카키", "올리브"]):
        return "グリーン系"
    if any(k in c for k in ["blue", "navy", "블루", "네이비"]):
        return "ブルー系"
    if any(k in c for k in ["purple", "violet", "퍼플", "보라"]):
        return "パープル系"
    if any(k in c for k in ["gold", "실버", "silver", "metal", "메탈"]):
        return "シルバー・ゴールド系"
    return "マルチカラー"


def split_color_values(color_text: str) -> List[str]:
    if not color_text:
        return []
    parts = re.split(r"[,/|]|\s+and\s+|\s*&\s*", color_text)
    return [part.strip() for part in parts if part.strip()]


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


def expand_color_abbreviations(color_text: str) -> str:
    normalized_text = (color_text or "").strip()
    dot_parts = [part.strip() for part in normalized_text.split(".") if part.strip()]
    if len(dot_parts) >= 2 and all(re.fullmatch(r"[A-Za-z]{1,3}", part) for part in dot_parts):
        values = dot_parts
    else:
        values = split_color_values(normalized_text)
    if not values:
        return color_text

    expanded: List[str] = []
    for raw in values:
        key = re.sub(r"[^a-z0-9]", "", raw.strip().lower())
        mapped = COLOR_ABBR_MAP.get(key)
        value = mapped if mapped else raw.strip()
        if value and value not in expanded:
            expanded.append(value)
    return ", ".join(expanded)


def build_size_variants(size_raw: str) -> List[str]:
    sz = (size_raw or "").strip()
    if not sz:
        return []

    variants = [sz]
    normalized = sz.upper().replace(" ", "")
    parts = [part.strip() for part in re.split(r"[/|]", sz) if part.strip()]
    for part in parts:
        if part not in variants:
            variants.append(part)

    if normalized in {"F", "FREE", "FREESIZE", "OS", "ONESIZE", "O/S"}:
        variants.extend([
            "F", "FREE", "FREE SIZE", "ONE SIZE", "ONESIZE", "OS", "O/S",
            "フリー", "フリーサイズ", "ワンサイズ", "サイズ指定なし", "指定なし"
        ])

    numeric_seeds = []
    for token in [sz] + parts:
        only_num = re.sub(r"[^0-9.]", "", token)
        if not only_num:
            continue
        try:
            if "." in only_num:
                value = float(only_num)
                if 20 <= value <= 35:
                    numeric_seeds.append(int(round(value * 10)))
                elif 200 <= value <= 350:
                    numeric_seeds.append(int(round(value)))
            else:
                int_value = int(only_num)
                if 200 <= int_value <= 350:
                    numeric_seeds.append(int_value)
                elif 20 <= int_value <= 35:
                    numeric_seeds.append(int_value * 10)
        except Exception:
            continue

    for numeric in numeric_seeds:
        cm = numeric / 10.0
        cm_str = f"{cm:.1f}".rstrip("0").rstrip(".")
        variants.extend([
            str(numeric),
            f"{cm:.1f}",
            cm_str,
            f"{cm_str}cm",
            f"{numeric}mm",
            f"JP{cm_str}",
            f"KR{cm_str}",
        ])

    seen = set()
    out = []
    for value in variants:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def normalize_size_token_for_match(text: str) -> str:
    value = (text or "").lower().strip()
    if not value:
        return ""
    value = value.replace("?", " ")
    value = value.replace("ｃｍ", "cm").replace("㎝", "cm").replace("センチ", "cm")
    value = value.replace("サイズ", "").replace("size", "")
    value = value.replace("cm", "").replace("mm", "")
    value = value.replace("jp", "").replace("kr", "").replace("us", "").replace("uk", "").replace("eu", "").replace("it", "")
    value = re.sub(r"[\s\-_/\(\)\[\]\{\}:;,+]", "", value)
    return value.replace(".", "")


def size_match(a: str, b: str) -> bool:
    normalized_a = normalize_size_token_for_match(a)
    normalized_b = normalize_size_token_for_match(b)
    if not normalized_a or not normalized_b:
        return False
    if normalized_a == normalized_b:
        return True

    fixed_tokens = {"xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl"}
    if normalized_a in fixed_tokens or normalized_b in fixed_tokens:
        return normalized_a == normalized_b
    return (normalized_a in normalized_b) or (normalized_b in normalized_a)


def is_free_size_text(size_text: str) -> bool:
    raw = (size_text or "").strip()
    if not raw:
        return False

    tokens = [token.strip() for token in re.split(r"[,/|]+", raw) if token.strip()]
    if not tokens:
        return False

    normalized_tokens = []
    for token in tokens:
        value = token.lower().strip()
        value = value.replace("?", " ")
        value = re.sub(r"\s+", "", value)
        value = value.replace("-", "").replace("_", "").replace(".", "")
        normalized_tokens.append(value)

    free_aliases = {
        "f", "free", "freesize", "onesize", "os", "o/s".replace("/", ""),
        "none", "n/a", "na", "no", "nosize", "nosizes", "notapplicable",
        "지정없음", "사이즈없음", "없음", "해당없음",
        JP_SIZE_SHITEI_NASHI, JP_SHITEI_NASHI, "サイズなし", "なし",
        "프리", "프리사이즈",
        "フリー", "フリーサイズ", "ワンサイズ",
    }
    return all(token in free_aliases for token in normalized_tokens)


def select_color_system(driver, color_system: str, row_index: int = 0, *, sleep_fn, scroll_and_click) -> bool:
    """Select a BUYMA color-system option."""
    try:
        color_selects = driver.find_elements(By.CSS_SELECTOR, ".sell-color-table .Select")
        if not color_selects:
            return False
        color_select = color_selects[min(row_index, len(color_selects) - 1)]
        control = color_select.find_element(By.CSS_SELECTOR, ".Select-control")
        safe_click(driver, control)
        sleep_fn(0.4)

        options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
        if options:
            target = color_system.replace("系", "")
            for opt in options:
                txt = opt.text.strip()
                if color_system in txt or target in txt:
                    scroll_and_click(driver, opt)
                    return True
            for opt in options:
                txt = opt.text.strip()
                if "その他" in txt:
                    scroll_and_click(driver, opt)
                    return True
            safe_click(driver, options[0])
            return True

        active = driver.switch_to.active_element
        for _ in range(25):
            focused = driver.execute_script(
                "var el=document.querySelector('.Select-menu-outer .Select-option.is-focused');"
                "return el?el.textContent.trim():'';"
            )
            if focused and (color_system in focused or color_system.replace("系", "") in focused):
                active.send_keys(Keys.ENTER)
                return True
            active.send_keys(Keys.ARROW_DOWN)
            sleep_fn(0.05)
        active.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def try_add_color_row(driver, *, sleep_fn, scroll_and_click) -> bool:
    """Click the BUYMA add-color-row action if present."""
    try:
        area = driver.find_element(By.CSS_SELECTOR, ".sell-color-table")
        candidates = area.find_elements(By.CSS_SELECTOR, "button, a, [role='button'], [class*='add']")
        for candidate in candidates:
            txt = (candidate.text or "").strip()
            cls = (candidate.get_attribute("class") or "")
            if ("追加" in txt) or ("add" in cls.lower()) or ("plus" in cls.lower()):
                scroll_and_click(driver, candidate)
                sleep_fn(0.4)
                return True
    except Exception:
        return False
    return False


def fill_size_supplement(driver, size_text: str, *, scroll_and_click) -> bool:
    """Write size text into fallback variation textarea."""
    if not size_text:
        return False
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        areas = variation.find_elements(By.CSS_SELECTOR, "textarea.bmm-c-textarea")
        if not areas:
            return False
        target = areas[0]
        scroll_and_click(driver, target)
        existing = (target.get_attribute("value") or "").strip()
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


def fill_color_supplement(driver, color_text_en: str, *, scroll_and_click) -> bool:
    """Write color text into fallback variation textarea."""
    if not color_text_en:
        return False
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        areas = variation.find_elements(By.CSS_SELECTOR, "textarea.bmm-c-textarea")
        if not areas:
            return False
        target = areas[0]
        scroll_and_click(driver, target)
        existing = (target.get_attribute("value") or "").strip()
        colors = split_color_values(color_text_en)
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


def select_option_in_select_control(driver, select_el, target_text: str, *, sleep_fn, scroll_and_click) -> bool:
    """Select target_text in a React Select control with exact match preference."""
    try:
        control = select_el.find_element(By.CSS_SELECTOR, ".Select-control")
        scroll_and_click(driver, control)
        sleep_fn(0.2)
        options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")

        def _norm(s: str) -> str:
            text = (s or "").strip().replace(" ", "").replace("\u3000", "").lower()
            text = text.replace("サイズ", "").replace("size", "").replace("cm", "").replace("㎝", "")
            return re.sub(r"\s+", "", text)

        def _to_mm(s: str):
            text = (s or "").strip().lower().replace("　", " ").replace("㎝", "cm")
            num = re.sub(r"[^0-9.]", "", text)
            if not num:
                return None
            try:
                if "." in num:
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
        has_range_suffix = ("以上" in (target_text or "")) or ("以下" in (target_text or ""))

        for opt in options:
            txt = (opt.text or "").strip()
            if _norm(txt) == target_norm:
                scroll_and_click(driver, opt)
                sleep_fn(0.3)
                return True

        if target_mm is not None and not has_range_suffix:
            for opt in options:
                txt = (opt.text or "").strip()
                if _to_mm(txt) == target_mm:
                    scroll_and_click(driver, opt)
                    sleep_fn(0.3)
                    return True
            try:
                query_candidates = [str(target_text).strip()]
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
                    sleep_fn(0.35)
                    filtered = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
                    for opt in filtered:
                        txt = (opt.text or "").strip()
                        if _to_mm(txt) == target_mm:
                            scroll_and_click(driver, opt)
                            sleep_fn(0.3)
                            return True
                sel_input.send_keys(Keys.ESCAPE)
            except Exception:
                pass
            return False

        if target_norm in {"s", "m", "l"}:
            return False

        for opt in options:
            txt = (opt.text or "").strip()
            txt_norm = _norm(txt)
            if target_norm and target_norm in txt_norm:
                if target_norm == "s" and "xs" in txt_norm:
                    continue
                scroll_and_click(driver, opt)
                sleep_fn(0.3)
                return True
        return False
    except Exception:
        return False


def infer_reference_jp_size(size_raw: str) -> str:
    """Map a raw size to BUYMA's JP reference size label."""
    if is_free_size_text(size_raw):
        return JP_SHITEI_NASHI

    text = (size_raw or "").strip().upper()
    if not text:
        return ""
    if "/" in text:
        text = text.split("/")[0].strip()

    paren_alpha = re.search(r"\(([A-Z]{1,4})\)", text)
    if paren_alpha:
        text = paren_alpha.group(1)

    alpha_match = re.search(r"(?<![A-Z])(XXXS|XXS|XS|S|M|L|XL|XXL|XXXL)(?![A-Z])", text)
    if alpha_match:
        text = alpha_match.group(1)

    if text in {"XXS", "XS"}:
        return "XS以下"
    if text == "S":
        return "S"
    if text == "M":
        return "M"
    if text == "L":
        return "L"
    if text in {"XL", "XXL", "XXXL"}:
        return "XL以上"

    only_num = re.sub(r"[^0-9.]", "", text)
    if only_num:
        try:
            if "." in only_num:
                fv = float(only_num)
                if 200 <= fv <= 350:
                    cm = fv / 10.0
                elif 20 <= fv <= 35:
                    cm = fv
                else:
                    return text
            else:
                iv = int(only_num)
                if 200 <= iv <= 350:
                    cm = iv / 10.0
                elif 20 <= iv <= 35:
                    cm = float(iv)
                else:
                    return text

            mm_val = int(round(cm * 10))
            if mm_val >= 275:
                return "27cm以上"
            if abs(cm - round(cm)) < 1e-9:
                return str(int(round(cm)))
            return f"{cm:.1f}"
        except Exception:
            return text
    return text


def normalize_jp_match_text(text: str) -> str:
    return (text or "").strip().replace(" ", "").replace("\u3000", "")


def is_shitei_nashi_text(text: str) -> bool:
    normalized = normalize_jp_match_text(text)
    return JP_SHITEI_NASHI in normalized or JP_SIZE_SHITEI_NASHI in normalized


def try_add_size_row(driver, scope=None, *, sleep_fn, scroll_and_click) -> bool:
    """Click the BUYMA add-size-row action if present."""
    try:
        root = scope or driver
        before = len(root.find_elements(By.CSS_SELECTOR, ".Select"))
        candidates = root.find_elements(
            By.CSS_SELECTOR,
            "button, a, [role='button'], [class*='add'], [class*='plus'], "
            "[aria-label*='追加'], [title*='追加'], [data-testid*='add']"
        )
        for candidate in candidates:
            txt = (candidate.text or "").strip()
            cls = (candidate.get_attribute("class") or "")
            aria = (candidate.get_attribute("aria-label") or "")
            title = (candidate.get_attribute("title") or "")
            if (
                ("追加" in txt) or ("add" in cls.lower()) or ("plus" in cls.lower())
                or ("追加" in aria) or ("追加" in title)
            ):
                scroll_and_click(driver, candidate)
                sleep_fn(0.4)

        icon_buttons = root.find_elements(By.CSS_SELECTOR, "button, [role='button']")
        for button in icon_buttons:
            txt = (button.text or "").strip()
            if txt:
                continue
            cls = (button.get_attribute("class") or "").lower()
            if any(keyword in cls for keyword in ["plus", "add", "icon"]):
                scroll_and_click(driver, button)
                sleep_fn(0.4)
                after = len(root.find_elements(By.CSS_SELECTOR, ".Select"))
                if after > before:
                    return True
    except Exception:
        return False
    return False


def select_size_by_select_controls(
    driver,
    scope,
    size_text: str,
    *,
    sleep_fn,
    scroll_and_click,
    try_add_size_row_fn,
) -> int:
    """Select size values through React Select controls."""
    if not size_text:
        return 0
    try:
        t0 = datetime.now().timestamp()
        sizes = [s.strip() for s in size_text.split(",") if s.strip()]
        if not sizes:
            return 0

        for _ in range(10):
            if datetime.now().timestamp() - t0 > 8:
                break
            current_selects = scope.find_elements(By.CSS_SELECTOR, ".Select")
            if len(current_selects) >= len(sizes):
                break
            if not try_add_size_row_fn(driver, scope=scope):
                break

        selected = 0
        for idx, sz in enumerate(sizes):
            if datetime.now().timestamp() - t0 > 12:
                break
            selects = scope.find_elements(By.CSS_SELECTOR, ".Select")
            if not selects:
                break

            if idx >= len(selects):
                if not try_add_size_row_fn(driver, scope=scope):
                    break
                selects = scope.find_elements(By.CSS_SELECTOR, ".Select")
                if idx >= len(selects):
                    break

            sel = selects[idx]
            try:
                control = sel.find_element(By.CSS_SELECTOR, ".Select-control")
            except Exception:
                continue

            scroll_and_click(driver, control)
            sleep_fn(0.25)

            variants = [v.lower().replace(" ", "") for v in build_size_variants(sz)]
            options = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
            picked = False

            if options:
                for opt in options:
                    txt = (opt.text or "").strip()
                    if any(size_match(v, txt) for v in variants):
                        scroll_and_click(driver, opt)
                        selected += 1
                        picked = True
                        sleep_fn(0.2)
                        break

            if not picked:
                try:
                    sel_input = sel.find_element(By.CSS_SELECTOR, "input")
                    sel_input.clear()
                    only_num = re.sub(r"[^0-9]", "", sz)
                    type_candidates = [sz]
                    if only_num and 200 <= int(only_num) <= 350:
                        cm_val = int(only_num) / 10.0
                        type_candidates.append(f"{cm_val:.1f}")
                        type_candidates.append(str(int(cm_val)) if cm_val == int(cm_val) else f"{cm_val}")
                    for query in type_candidates:
                        sel_input.clear()
                        sel_input.send_keys(query)
                        sleep_fn(0.4)
                        filtered = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
                        for opt in filtered:
                            txt = (opt.text or "").strip()
                            if any(size_match(v, txt) for v in variants):
                                scroll_and_click(driver, opt)
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
                try:
                    driver.execute_script("arguments[0].click()", control)
                    sleep_fn(0.3)
                    active = driver.switch_to.active_element
                    for _ in range(50):
                        if datetime.now().timestamp() - t0 > 15:
                            break
                        focused = driver.execute_script(
                            "var el=document.querySelector('.Select-menu-outer .Select-option.is-focused');"
                            "return el?el.textContent.trim():'';"
                        )
                        fnorm = (focused or "").lower().replace(" ", "")
                        if focused and any(size_match(v, fnorm) for v in variants):
                            active.send_keys(Keys.ENTER)
                            selected += 1
                            picked = True
                            break
                        active.send_keys(Keys.ARROW_DOWN)
                        sleep_fn(0.05)
                    if not picked:
                        active.send_keys(Keys.ESCAPE)
                except Exception:
                    pass
        return selected
    except Exception:
        return 0


def check_no_variation_option(
    driver,
    prefer_shitei_nashi: bool = False,
    *,
    scroll_and_click,
    select_option_in_select_control_fn,
) -> bool:
    """Select variation-none / shitei-nashi style options when no variation exists."""
    if prefer_shitei_nashi:
        keywords = [
            "指定なし", "サイズ指定なし", "サイズなし",
            "変動なし", "変形なし", "バリエーションなし", "バリエーション無し", "변형없음"
        ]
    else:
        keywords = [
            "変動なし", "変形なし", "バリエーションなし", "バリエーション無し", "サイズなし",
            "サイズ指定なし", "指定なし", "변형없음"
        ]
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        labels = variation.find_elements(By.CSS_SELECTOR, "label")
        for keyword in keywords:
            for label in labels:
                txt = (label.text or "").strip()
                if txt and keyword in txt:
                    scroll_and_click(driver, label)
                    return True

        nodes = variation.find_elements(By.XPATH, ".//*[normalize-space(text())!='']")
        for keyword in keywords:
            for node in nodes:
                txt = (node.text or "").strip()
                if not txt or keyword not in txt:
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

        inputs = variation.find_elements(By.CSS_SELECTOR, "input[type='checkbox'], input[type='radio']")
        for ipt in inputs:
            meta = " ".join([
                ipt.get_attribute("value") or "",
                ipt.get_attribute("name") or "",
                ipt.get_attribute("id") or "",
            ])
            if any(keyword in meta for keyword in ["none", "unspecified", "no_variation", "variation_none"]):
                return True

        selects = variation.find_elements(By.CSS_SELECTOR, ".Select")
        targets = (
            ["指定なし", "サイズ指定なし", "バリエーションなし", "在庫変動なし"]
            if prefer_shitei_nashi
            else ["バリエーションなし", "在庫変動なし", "サイズ指定なし", "指定なし"]
        )
        for sel in selects:
            for target in targets:
                if select_option_in_select_control_fn(driver, sel, target):
                    return True
    except Exception:
        return False
    return False


def force_select_shitei_nashi(driver, *, scroll_and_click, select_option_in_select_control_fn) -> bool:
    """Force select 指定なし / サイズ指定なし."""
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")

        labels = variation.find_elements(By.CSS_SELECTOR, "label")
        for label in labels:
            if is_shitei_nashi_text(label.text or ""):
                scroll_and_click(driver, label)
                return True

        nodes = variation.find_elements(By.XPATH, ".//*[normalize-space(text())!='']")
        for node in nodes:
            if not is_shitei_nashi_text(node.text or ""):
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

        selects = variation.find_elements(By.CSS_SELECTOR, ".Select")
        for sel in selects:
            if select_option_in_select_control_fn(driver, sel, JP_SHITEI_NASHI):
                return True
            if select_option_in_select_control_fn(driver, sel, JP_SIZE_SHITEI_NASHI):
                return True
    except Exception:
        return False
    return False


def force_select_shitei_nashi_global(driver, *, force_select_shitei_nashi_fn, select_option_in_select_control_fn) -> bool:
    if force_select_shitei_nashi_fn(driver):
        return True

    try:
        selects = driver.find_elements(By.CSS_SELECTOR, ".sell-size-table .Select, .sell-variation .Select")
        for sel in selects:
            if select_option_in_select_control_fn(driver, sel, JP_SHITEI_NASHI):
                return True
            if select_option_in_select_control_fn(driver, sel, JP_SIZE_SHITEI_NASHI):
                return True
    except Exception:
        pass

    try:
        nodes = driver.find_elements(By.XPATH, "//*[normalize-space(text())!='']")
        for node in nodes:
            if not is_shitei_nashi_text(node.text or ""):
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


def force_reference_size_shitei_nashi(driver, panel=None, *, sleep_fn, scroll_and_click, select_option_in_select_control_fn) -> bool:
    """Force JP reference size selects to 指定なし."""
    try:
        root = panel if panel is not None else driver
        selects = root.find_elements(By.CSS_SELECTOR, ".sell-size-table .Select")
        if not selects:
            selects = root.find_elements(By.CSS_SELECTOR, ".sell-variation .sell-size-table .Select")
        if not selects:
            return False

        changed = 0
        for sel in selects:
            try:
                current = sel.find_elements(By.CSS_SELECTOR, ".Select-value-label")
                if current and is_shitei_nashi_text(current[0].text or ""):
                    changed += 1
                    continue

                if select_option_in_select_control_fn(driver, sel, JP_SHITEI_NASHI):
                    changed += 1
                    continue
                if select_option_in_select_control_fn(driver, sel, JP_SIZE_SHITEI_NASHI):
                    changed += 1
                    continue

                try:
                    control = sel.find_element(By.CSS_SELECTOR, ".Select-control")
                    scroll_and_click(driver, control)
                    sleep_fn(0.2)
                    inp = sel.find_element(By.CSS_SELECTOR, ".Select-input input")
                    inp.clear()
                    inp.send_keys(JP_SHITEI_NASHI)
                    sleep_fn(0.35)
                    opts = driver.find_elements(By.CSS_SELECTOR, ".Select-menu-outer .Select-option")
                    exact = None
                    for opt in opts:
                        if is_shitei_nashi_text(opt.text or ""):
                            exact = opt
                            break
                    if exact is not None:
                        scroll_and_click(driver, exact)
                        changed += 1
                        continue
                    inp.send_keys(Keys.ENTER)
                    sleep_fn(0.2)
                    current2 = sel.find_elements(By.CSS_SELECTOR, ".Select-value-label")
                    if current2 and is_shitei_nashi_text(current2[0].text or ""):
                        changed += 1
                        continue
                except Exception:
                    pass
            except Exception:
                continue
        return changed > 0
    except Exception:
        return False


def force_select_variation_none_sequence(driver, panel=None, *, select_option_in_select_control_fn) -> bool:
    """Select バリエーションなし / 指定なし in size selects."""
    try:
        root = panel if panel is not None else driver
        selects = root.find_elements(By.CSS_SELECTOR, ".sell-variation .Select, .sell-size-table .Select")
        if not selects:
            selects = driver.find_elements(By.CSS_SELECTOR, ".sell-variation .Select, .sell-size-table .Select")
        if not selects:
            return False

        targets = ["バリエーションなし", "バリエーション無し", "指定なし", "サイズ指定なし"]
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
            for target in targets:
                if select_option_in_select_control_fn(driver, sel, target):
                    return True
        return False
    except Exception:
        return False


def enable_size_selection_ui(driver, *, sleep_fn, scroll_and_click) -> bool:
    """Expand hidden size selection UI."""
    keywords = ["サイズを指定", "サイズあり", "サイズを選択", "サイズを入力", "バリエーションあり"]
    try:
        variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
        nodes = variation.find_elements(By.XPATH, ".//*[normalize-space(text())!='']")
        for node in nodes:
            txt = (node.text or "").strip()
            if txt and any(keyword in txt for keyword in keywords):
                try:
                    scroll_and_click(driver, node)
                except Exception:
                    driver.execute_script("arguments[0].click();", node)
                sleep_fn(0.6)
                return True
    except Exception:
        return False
    return False


def fill_size_text_inputs(driver, size_text: str, *, sleep_fn, scroll_and_click) -> int:
    """Fill visible size text inputs directly."""
    if not size_text:
        return 0
    sizes = [s.strip() for s in size_text.split(",") if s.strip()]
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
            scroll_and_click(driver, target)
            target.clear()
            target.send_keys(sz)
            count += 1
            sleep_fn(0.15)
        return count
    except Exception:
        return 0


def fill_size_table_rows(
    driver,
    panel,
    size_text: str,
    *,
    sleep_fn,
    scroll_and_click,
    select_option_in_select_control_fn,
    infer_reference_jp_size_fn,
) -> int:
    """Fill BUYMA sell-size-table rows with size names and JP reference sizes."""
    if not size_text:
        return 0
    try:
        sizes = [s.strip() for s in size_text.split(",") if s.strip()]
        if not sizes:
            return 0

        mode_selects = panel.find_elements(By.CSS_SELECTOR, ".bmm-l-grid-no-bottom .Select")
        if mode_selects:
            select_option_in_select_control_fn(driver, mode_selects[0], "バリエーションあり")
            sleep_fn(0.4)

        table = panel.find_elements(By.CSS_SELECTOR, ".sell-size-table")
        if not table:
            return 0

        max_add_attempts = max(len(sizes) * 2, 24)
        for _ in range(max_add_attempts):
            rows = panel.find_elements(By.CSS_SELECTOR, ".sell-size-table tbody tr")
            if len(rows) >= len(sizes):
                break
            add_links = panel.find_elements(By.XPATH, ".//div[contains(@class,'bmm-c-form-table__foot')]//a")
            clicked = False
            for link in add_links:
                txt = (link.text or "").strip()
                if "新しいサイズを追加" in txt or "サイズ" in txt:
                    scroll_and_click(driver, link)
                    sleep_fn(0.35)
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
                scroll_and_click(driver, name_input)
                name_input.clear()
                name_input.send_keys(sz)

                try:
                    ref_select = rows[idx].find_element(By.CSS_SELECTOR, "td:nth-child(3) .Select")
                    ref_target = infer_reference_jp_size_fn(sz)
                    if ref_target:
                        select_option_in_select_control_fn(driver, ref_select, ref_target)
                except Exception:
                    pass

                filled += 1
                sleep_fn(0.15)
            except Exception:
                continue
        return filled
    except Exception:
        return 0


def fill_size_edit_details(
    driver,
    actual_size_text: str,
    *,
    scroll_and_click,
    extract_actual_size_rows_fn,
    extract_actual_measure_map_fn,
    pick_measure_value_by_label_fn,
) -> int:
    """Fill BUYMA size edit dialogs with parsed actual-size measurements."""
    all_rows = extract_actual_size_rows_fn(actual_size_text)
    fallback_pairs = extract_actual_measure_map_fn(actual_size_text)
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
            for dialog in dialogs:
                try:
                    txt = (dialog.text or "").strip()
                    score = 0
                    if any(k in txt for k in ["着丈", "ウエスト", "股上", "ヒップ", "サイズ", "cm"]):
                        score += 5
                    inputs = dialog.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[type='tel'], textarea")
                    editable = [i for i in inputs if i.get_attribute("disabled") is None]
                    score += len(editable)
                    if score > best_score:
                        best = dialog
                        best_score = score
                except Exception:
                    continue
            return best or dialogs[-1]

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
                scroll_and_click(driver, btn)

                dialog = driver
                popup_handle = None
                for _ in range(10):
                    now_handles = set(driver.window_handles)
                    new_handles = [h for h in now_handles if h not in before_handles]
                    if new_handles:
                        popup_handle = new_handles[0]
                        break
                if popup_handle:
                    driver.switch_to.window(popup_handle)
                    print("  [actual-size] popup window detected")
                    dialog = driver
                else:
                    dialogs = driver.find_elements(By.CSS_SELECTOR, "[role='dialog'], .ReactModal__Content, .bmm-c-modal")
                    dialog = _pick_best_dialog(dialogs) if dialogs else driver
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

                active_frame = None
                if not visible_inputs:
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
                        picked_value = pick_measure_value_by_label_fn(label, selected_pairs)
                        inputs = row.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], textarea")
                        if not inputs:
                            continue
                        target = next((i for i in inputs if i.get_attribute("disabled") is None), None)
                        if not target or not picked_value:
                            continue
                        target_id = target.get_attribute("id") or target.get_attribute("name") or str(id(target))
                        if target_id in used_inputs:
                            continue
                        scroll_and_click(driver, target)
                        target.send_keys(Keys.CONTROL, "a")
                        target.send_keys(Keys.BACKSPACE)
                        target.send_keys(picked_value)
                        used_inputs.add(target_id)
                        local_filled += 1
                    except Exception:
                        continue

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
                            scroll_and_click(driver, inp)
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
                        scroll_and_click(driver, save_buttons[0])
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


def apply_buyma_option_selection(
    driver,
    *,
    buyma_sell_url: str,
    color: str,
    color_values: List[str],
    size_text: str,
    actual_size_text: str,
    sleep_fn,
    scroll_and_click,
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
) -> None:
    """Apply BUYMA color/size selection UI using injected browser helpers."""
    if color and color.lower() != "none":
        try:
            if not color_values:
                color_values = [color]
            color_for_system = color_values[0]
            color_system = infer_color_system(color_for_system)
            picked = select_color_system(driver, color_system, row_index=0)

            if len(color_values) > 1:
                for idx, color_value in enumerate(color_values[1:], start=1):
                    if try_add_color_row(driver):
                        select_color_system(driver, infer_color_system(color_value), row_index=idx)

            color_name_inputs = driver.find_elements(
                By.CSS_SELECTOR,
                ".sell-color-table tbody tr td:nth-child(2) input.bmm-c-text-field, .sell-color-table input.bmm-c-text-field",
            )
            enabled_inputs = [
                color_input for color_input in color_name_inputs
                if color_input.is_enabled() and color_input.get_attribute("disabled") is None
            ]

            if enabled_inputs:
                for idx, color_value in enumerate(color_values):
                    if idx >= len(enabled_inputs):
                        if try_add_color_row(driver):
                            color_name_inputs = driver.find_elements(
                                By.CSS_SELECTOR,
                                ".sell-color-table tbody tr td:nth-child(2) input.bmm-c-text-field, .sell-color-table input.bmm-c-text-field",
                            )
                            enabled_inputs = [
                                color_input for color_input in color_name_inputs
                                if color_input.is_enabled() and color_input.get_attribute("disabled") is None
                            ]
                        else:
                            break
                    if idx >= len(enabled_inputs):
                        break

                    target_input = enabled_inputs[idx]
                    scroll_and_click(driver, target_input)
                    target_input.clear()
                    target_input.send_keys(color_value)
                    sleep_fn(0.2)

                if picked:
                    print(f"  ✓ 색상 입력(개별): {', '.join(color_values)}")
                else:
                    print(f"  △ 색상계통 미선택, 색상만 개별 입력: {', '.join(color_values)}")
            else:
                forced = False
                if color_name_inputs and color_values:
                    try:
                        forced_count = 0
                        for idx, color_value in enumerate(color_values):
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
                                color_name_inputs[idx],
                                color_value,
                            )
                            if ok:
                                forced_count += 1
                        forced = forced_count > 0
                    except Exception:
                        forced = False

                if picked and forced:
                    print(f"  ✓ 색상 입력(JS강제/개별): {', '.join(color_values)}")
                elif picked:
                    if fill_color_supplement(driver, ", ".join(color_values)):
                        print(f"  ✓ 색상계통 선택 + 보충정보 입력: {color_system} / {', '.join(color_values)}")
                    else:
                        print(f"  ✓ 색상계통 선택: {color_system} (색상입력란 비활성)")
                else:
                    print(f"  ✗ 색상 입력 실패(계통/색상), 수동 선택 필요: {color}")
        except Exception as exc:
            print(f"  ✗ 색상 입력 실패: {exc}")

    try:
        free_size = is_free_size_text(size_text)
        size_tabs = driver.find_elements(By.CSS_SELECTOR, ".sell-variation__tab-item")
        handled_size = False

        all_tab_texts = [(tab.text or "").strip() for tab in size_tabs]
        all_tab_ids = [(tab.get_attribute("aria-controls") or "").strip() for tab in size_tabs]
        print(f"  [탭별 사이즈목록: {list(zip(all_tab_texts, all_tab_ids))}")

        for tab_idx, tab in enumerate(size_tabs):
            tab_text = (tab.text or "").strip()
            tab_panel_id = (tab.get_attribute("aria-controls") or "").strip()
            is_color_tab = ("カラー" in tab_text or "COLOR" in tab_text.upper() or "color" in tab_panel_id.lower())
            is_size_tab = (
                "サイズ" in tab_text
                or "SIZE" in tab_text.upper()
                or tab_panel_id.endswith("-3")
                or tab_panel_id.endswith("-size")
                or (not is_color_tab and tab_idx > 0)
            )
            if not is_size_tab:
                continue

            print(f"  [탭] 사이즈탭 클릭: '{tab_text}' (aria-controls={tab_panel_id})")
            driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", tab)
            driver.execute_script("window.scrollBy(0, -180);")
            scroll_and_click(driver, tab)

            for _ in range(16):
                visible_labels = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                visible_selects = driver.find_elements(By.CSS_SELECTOR, ".sell-variation .Select")
                visible_inputs = [
                    input_el
                    for input_el in driver.find_elements(
                        By.CSS_SELECTOR,
                        ".sell-variation input[type='text'], .sell-variation input.bmm-c-text-field",
                    )
                    if input_el.is_displayed()
                ]
                size_table = driver.find_elements(By.CSS_SELECTOR, ".sell-size-table")
                if len(visible_labels) > 0 or len(visible_selects) > 1 or len(visible_inputs) > 1 or size_table:
                    break
                sleep_fn(0.5)

            panel = None
            if tab_panel_id:
                try:
                    panel = driver.find_element(By.ID, tab_panel_id)
                except Exception:
                    panel = None
            if panel is None:
                panel = driver.find_element(By.CSS_SELECTOR, ".sell-variation")

            panel_html = panel.text.strip()
            if "カテゴリを選択" in panel_html:
                print(f"  ✗ 카테고리 미선택으로 사이즈목록 없음. 카테고리 선택 후 자동 선택 필요: {size_text}")
            else:
                for _ in range(10):
                    if panel.find_elements(By.CSS_SELECTOR, "label, input[type='checkbox']"):
                        break
                    sleep_fn(0.5)

                if free_size:
                    no_var_ok = (
                        force_select_variation_none_sequence(driver, panel=panel)
                        or force_select_shitei_nashi_global(driver)
                        or check_no_variation_option(driver, prefer_shitei_nashi=True)
                    )
                    ref_ok = force_reference_size_shitei_nashi(driver, panel=panel)
                    if no_var_ok or ref_ok:
                        if actual_size_text:
                            filled_detail = fill_size_edit_details(driver, actual_size_text)
                            if filled_detail:
                                print(f"  actual size detail filled: {filled_detail}")
                            else:
                                print("  actual size detail not filled")
                        print(f"  ✓ 프리사이즈 감지, 指定なし 선택 ({size_text})")
                    else:
                        print(f"  ✗ 프리사이즈 감지, 指定なし 선택 실패. 자동 선택 필요: {size_text}")
                    handled_size = True
                    break

                table_filled = fill_size_table_rows(driver, panel, size_text)
                if table_filled:
                    if actual_size_text:
                        filled_detail = fill_size_edit_details(driver, actual_size_text)
                        if filled_detail:
                            print(f"  actual size detail filled: {filled_detail}")
                        else:
                            print("  actual size detail not filled")
                    print(f"  ✓ 사이즈입력(테이블): {table_filled}개({size_text})")
                    handled_size = True
                    break

                select_matched = select_size_by_select_controls(driver, panel, size_text)
                if select_matched:
                    print(f"  ✓ 사이즈선택(Select): {select_matched}개({size_text})")
                    handled_size = True
                    break

                items = panel.find_elements(By.CSS_SELECTOR, "label")
                if not items:
                    items = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                available = [item.text.strip() for item in items if item.text.strip()]

                matched = 0
                if size_text:
                    sizes = [size.strip() for size in size_text.split(",") if size.strip()]
                    for size in sizes:
                        size_variants = build_size_variants(size)
                        for item in items:
                            item_text = item.text.strip()
                            if any(size_match(variant, item_text) for variant in size_variants):
                                scroll_and_click(driver, item)
                                matched += 1
                                driver.get(buyma_sell_url)
                                break

                    if matched:
                        print(f"  ✓ 사이즈선택: {matched}개({size_text})")
                    else:
                        if not available:
                            expanded = enable_size_selection_ui(driver)
                            if expanded:
                                items2 = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                                matched2 = 0
                                if size_text and items2:
                                    sizes2 = [size.strip() for size in size_text.split(",") if size.strip()]
                                    for size2 in sizes2:
                                        size_variants2 = build_size_variants(size2)
                                        for item2 in items2:
                                            item_text2 = item2.text.strip()
                                            if any(size_match(variant, item_text2) for variant in size_variants2):
                                                scroll_and_click(driver, item2)
                                                matched2 += 1
                                                sleep_fn(0.2)
                                                break
                                if matched2:
                                    print(f"  ✓ 사이즈선택: {matched2}개({size_text})")
                                    handled_size = True
                                    break

                            if free_size:
                                if (
                                    force_select_variation_none_sequence(driver)
                                    or force_select_shitei_nashi_global(driver)
                                    or force_reference_size_shitei_nashi(driver)
                                ):
                                    print(f"  ✓ 프리사이즈 감지, 指定なし 선택 ({size_text})")
                                else:
                                    print(f"  ✗ 프리사이즈 감지, 선택없음/실패: {size_text}")
                            else:
                                if check_no_variation_option(driver):
                                    print("  ✗ 사이즈옵션 없음, 체크박스만 체크")
                                elif size_text and fill_size_text_inputs(driver, size_text) > 0:
                                    print(f"  ✓ 사이즈텍스트입력: {size_text}")
                                elif size_text and fill_size_supplement(driver, size_text):
                                    print(f"  ✓ 사이즈옵션 없음, 보충정보 입력: {size_text}")
                                else:
                                    print(f"  ✗ 사이즈옵션 없음(보충정보 처리 실패): {size_text}")
                        else:
                            print(f"  ✗ 사이즈매칭 실패 (옵션 전체: {available}), 자동 선택 필요: {size_text}")
                else:
                    print(f"  ✗ 사이즈옵션없음 (옵션: {available})")

                handled_size = True
                break

        if not handled_size:
            if free_size:
                no_var_ok = (
                    force_select_variation_none_sequence(driver)
                    or force_select_shitei_nashi_global(driver)
                    or check_no_variation_option(driver, prefer_shitei_nashi=True)
                )
                ref_ok = force_reference_size_shitei_nashi(driver)
                if no_var_ok or ref_ok:
                    if actual_size_text:
                        filled_detail = fill_size_edit_details(driver, actual_size_text)
                        if filled_detail:
                            print(f"  actual size detail filled: {filled_detail}")
                        else:
                            print("  actual size detail not filled")
                    print(f"  ✓ 프리사이즈 감지, 指定なし 선택 ({size_text})")
                else:
                    print(f"  ✗ 프리사이즈 감지, 指定なし 선택 실패. 자동 선택 필요: {size_text}")
                handled_size = True

        if not handled_size:
            select_matched = select_size_by_select_controls(
                driver,
                driver.find_element(By.CSS_SELECTOR, ".sell-variation"),
                size_text,
            )
            if select_matched:
                print(f"  ✓ 사이즈선택(Select): {select_matched}개({size_text})")
                handled_size = True

        if not handled_size:
            items = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
            available = [item.text.strip() for item in items if item.text.strip()][:10]
            matched = 0
            if size_text:
                sizes = [size.strip() for size in size_text.split(",") if size.strip()]
                for size in sizes:
                    size_variants = build_size_variants(size)
                    for item in items:
                        item_text = item.text.strip()
                        if any(size_match(variant, item_text) for variant in size_variants):
                            scroll_and_click(driver, item)
                            matched += 1
                            sleep_fn(0.2)
                            break
            if matched:
                print(f"  ✓ 사이즈선택: {matched}개({size_text})")
            elif not available:
                if enable_size_selection_ui(driver):
                    items2 = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
                    matched2 = 0
                    if size_text and items2:
                        sizes2 = [size.strip() for size in size_text.split(",") if size.strip()]
                        for size2 in sizes2:
                            size_variants2 = build_size_variants(size2)
                            for item2 in items2:
                                item_text2 = item2.text.strip()
                                if any(size_match(variant, item_text2) for variant in size_variants2):
                                    scroll_and_click(driver, item2)
                                    matched2 += 1
                                    sleep_fn(0.2)
                                    break
                    if matched2:
                        print(f"  ✓ 사이즈선택: {matched2}개({size_text})")
                    elif free_size and (
                        force_select_variation_none_sequence(driver)
                        or force_select_shitei_nashi_global(driver)
                        or force_reference_size_shitei_nashi(driver)
                    ):
                        print(f"  ✓ 프리사이즈 감지, 指定なし 선택 ({size_text})")
                    elif check_no_variation_option(driver):
                        print("  ✗ 사이즈옵션 없음, 체크박스만 체크")
                    elif (not free_size) and size_text and fill_size_text_inputs(driver, size_text) > 0:
                        print(f"  ✓ 사이즈텍스트입력: {size_text}")
                    elif (not free_size) and size_text and fill_size_supplement(driver, size_text):
                        print(f"  ✓ 사이즈옵션 없음, 보충정보 입력: {size_text}")
                    else:
                        print(f"  ✗ 사이즈옵션/선택 미탐: {size_text}")
                elif free_size and (
                    force_select_variation_none_sequence(driver)
                    or force_select_shitei_nashi_global(driver)
                    or force_reference_size_shitei_nashi(driver)
                ):
                    print(f"  ✓ 프리사이즈 감지, 指定なし 선택 ({size_text})")
                elif check_no_variation_option(driver):
                    print("  ✗ 사이즈옵션 없음, 체크박스만 체크")
                elif (not free_size) and size_text and fill_size_text_inputs(driver, size_text) > 0:
                    print(f"  ✓ 사이즈텍스트입력: {size_text}")
                elif (not free_size) and size_text and fill_size_supplement(driver, size_text):
                    print(f"  ✓ 사이즈옵션 없음, 보충정보 입력: {size_text}")
                else:
                    print(f"  ✗ 사이즈옵션/선택 미탐: {size_text}")
            else:
                if size_text:
                    print(f"  ✗ 사이즈매칭 실패 (옵션: {available}), 자동 선택 필요: {size_text}")
                else:
                    print(f"  ✗ 사이즈옵션없음 (옵션: {available})")
    except Exception as exc:
        print(f"  ✗ 사이즈선택 실패: {exc}")
