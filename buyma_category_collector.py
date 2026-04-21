"""Standalone BUYMA category hierarchy collector.

This module is intentionally decoupled from current upload flow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Dict, Iterable, List, Set, Tuple
from urllib.parse import parse_qs, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchWindowException, WebDriverException
import time


@dataclass(frozen=True)
class BuymaCategoryRow:
    parent_category: str
    middle_category: str
    child_category: str
    category_url: str
    category_id: str
    raw_text: str
    collected_at: str

    def dedupe_key(self) -> Tuple[str, str, str, str, str]:
        return (
            (self.parent_category or "").strip(),
            (self.middle_category or "").strip(),
            (self.child_category or "").strip(),
            (self.category_url or "").strip(),
            (self.category_id or "").strip(),
        )


BUYMA_PARENT_CATEGORY_SEEDS = [
    "レディースファッション",
    "メンズファッション",
    "ベビー・キッズ",
    "ビューティー",
    "ライフスタイル",
    "スポーツ",
]

PLACEHOLDER_LABELS = {
    "第一カテゴリから選択",
    "第二カテゴリから選択",
    "第三カテゴリから選択",
    "選択してください",
    "선택하세요",
    "선택해주세요",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _extract_category_id(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for key in ("cid", "category_id", "categoryId", "cat", "id"):
        values = qs.get(key) or []
        if values and str(values[0]).strip():
            return str(values[0]).strip()
    m = re.search(r"/category/(\d+)", parsed.path)
    if m:
        return m.group(1)
    return ""


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _safe_execute_script(driver: WebDriver, script: str, *args, default=None):
    try:
        return driver.execute_script(script, *args)
    except (NoSuchWindowException, WebDriverException):
        return default


def _is_window_alive(driver: WebDriver) -> bool:
    try:
        return bool(driver.window_handles)
    except Exception:
        return False


def _scroll_category_section_into_view(driver: WebDriver) -> None:
    js = """
    const titleNodes = Array.from(document.querySelectorAll('.bmm-c-summary__ttl, h1, h2, h3'));
    const titleHit = titleNodes.find(n => (n.textContent || '').includes('カテゴリ'));
    const categoryRoot = document.querySelector('.sell-category')
      || document.querySelector('.sell-category-select')
      || document.querySelector('.sell-category__item');
    const target = categoryRoot || titleHit;
    if (!target) return false;
    target.scrollIntoView({ behavior: 'instant', block: 'center' });
    return true;
    """
    try:
        _safe_execute_script(driver, js, default=None)
    except Exception:
        pass


def _native_select_control_click(driver: WebDriver, level_index: int) -> bool:
    selectors = []
    if level_index == 0:
        selectors = [
            ".sell-category-select .Select-control",
            ".sell-category-select [class*='-control']",
            ".sell-category-select [role='combobox']",
            ".sell-category-select",
        ]
    else:
        selectors = [
            f".sell-category__item:nth-of-type({level_index + 1}) .Select-control",
            f".sell-category__item:nth-of-type({level_index + 1}) [class*='-control']",
            f".sell-category__item:nth-of-type({level_index + 1}) [role='combobox']",
            f".sell-category__item:nth-of-type({level_index + 1}) .Select",
        ]
    for selector in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, selector)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.08)
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(0.12)
            return True
        except Exception:
            continue
    return False


def _open_select(driver: WebDriver, level_index: int, timeout: float = 5.0) -> bool:
    _scroll_category_section_into_view(driver)
    js_click = """
    const idx = arguments[0];
    let el = null;
    const fireMouseSequence = (node) => {
      if (!node) return false;
      const rect = node.getBoundingClientRect();
      const init = { bubbles: true, cancelable: true, view: window, clientX: rect.left + 8, clientY: rect.top + 8 };
      node.dispatchEvent(new MouseEvent('mousedown', init));
      node.dispatchEvent(new MouseEvent('mouseup', init));
      node.dispatchEvent(new MouseEvent('click', init));
      return true;
    };
    const clickControl = (node) => {
      if (!node) return false;
      const control = node.closest('.Select-control')
        || node.closest('[class*="-control"]')
        || node.closest('[role="combobox"]')
        || node;
      const arrow = control.querySelector('.Select-arrow-zone, [class*="indicator"], [class*="arrow"]');
      control.focus?.();
      fireMouseSequence(control);
      if (arrow) fireMouseSequence(arrow);
      return true;
    };
    if (idx === 0) {
      el = document.querySelector('.sell-category-select .Select-control')
        || document.querySelector('.sell-category-select [class*="-control"]')
        || document.querySelector('.sell-category-select [role="combobox"]')
        || document.querySelector('.sell-category-select input')
        || document.querySelector('.sell-category-select');
    } else {
      const items = document.querySelectorAll('.sell-category__item');
      if (items.length > idx) {
        el = items[idx].querySelector('.Select-control')
          || items[idx].querySelector('[class*="-control"]')
          || items[idx].querySelector('[role="combobox"]')
          || items[idx].querySelector('input')
          || items[idx].querySelector('.Select');
      }
    }
    if (!el) {
      const allCombos = Array.from(document.querySelectorAll('[role="combobox"], [class*="-control"]'));
      if (allCombos.length > idx) el = allCombos[idx];
    }
    return clickControl(el);
    """
    js_key_open = """
    const idx = arguments[0];
    let target = null;
    const items = document.querySelectorAll('.sell-category__item');
    if (idx === 0) {
      target = document.querySelector('.sell-category-select .Select-input[role="combobox"]')
        || document.querySelector('.sell-category-select [role="combobox"]')
        || document.querySelector('.sell-category-select input');
    } else if (items.length > idx) {
      target = items[idx].querySelector('.Select-input[role="combobox"]')
        || items[idx].querySelector('[role="combobox"]')
        || items[idx].querySelector('input');
    }
    if (!target) {
      const combos = document.querySelectorAll('[role="combobox"], .Select-input');
      if (combos.length > idx) target = combos[idx];
    }
    if (!target) return false;
    target.focus();
    const ev = new KeyboardEvent('keydown', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true });
    target.dispatchEvent(ev);
    target.dispatchEvent(new KeyboardEvent('keyup', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true }));
    return true;
    """
    menu_selector = (
        ".Select-menu-outer .Select-option, .Select-menu .Select-option, "
        "[role='listbox'] [role='option'], [class*='menu'] [class*='option'], "
        ".Select-menu-outer [id*='react-select'][role='option']"
    )
    for _ in range(3):
        # BUYMA UI often needs a real click before options render.
        _native_select_control_click(driver, level_index)
        if not _is_window_alive(driver):
            return False
        opened = bool(_safe_execute_script(driver, js_click, level_index, default=False))
        if not opened:
            opened = bool(_safe_execute_script(driver, js_key_open, level_index, default=False))
        if not opened:
            opened = _native_select_control_click(driver, level_index)
        if not opened:
            continue
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, menu_selector))
            )
            return True
        except Exception:
            # Retry with keyboard-open fallback.
            bool(_safe_execute_script(driver, js_key_open, level_index, default=False))
            try:
                WebDriverWait(driver, 1.5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, menu_selector))
                )
                return True
            except Exception:
                continue
    return False


def _read_open_options(driver: WebDriver) -> List[Dict[str, str]]:
    js = """
    const options = Array.from(document.querySelectorAll(
      '.Select-menu-outer .Select-option, .Select-menu .Select-option, '
      + '[role="listbox"] [role="option"], [class*="menu"] [class*="option"], '
      + '[id*="react-select"][id*="-option-"]'
    ));
    return options.map((el, i) => {
      const text = (el.textContent || '').trim();
      const href = el.getAttribute('href')
        || el.dataset?.href
        || (el.querySelector('a[href]') ? el.querySelector('a[href]').getAttribute('href') : '')
        || '';
      return { index: String(i), text, href };
    }).filter(o => o.text);
    """
    rows = []
    for _ in range(8):
        if not _is_window_alive(driver):
            break
        rows = _safe_execute_script(driver, js, default=[]) or []
        if rows:
            break
        time.sleep(0.25)
    out: List[Dict[str, str]] = []
    for row in rows:
        out.append(
            {
                "index": str(row.get("index", "")),
                "text": _normalize_space(str(row.get("text", ""))),
                "href": str(row.get("href", "")).strip(),
            }
        )
    return out


def _choose_open_option_by_text(driver: WebDriver, label: str) -> bool:
    target_raw = _normalize_space(label)
    target = target_raw.lower()
    if not target:
        return False
    selectors = [
        ".Select-menu-outer .Select-option",
        ".Select-menu .Select-option",
        "[role='listbox'] [role='option']",
        "[class*='menu'] [class*='option']",
        "[id*='react-select'][id*='-option-']",
    ]
    # Native click first (BUYMA often requires real click event sequence).
    for _ in range(4):
        for selector in selectors:
            try:
                options = driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                options = []
            for option in options:
                try:
                    text = _normalize_space(option.text).lower()
                    if not text:
                        text = _normalize_space(option.get_attribute("aria-label") or "").lower()
                    if text == target or target in text or text in target:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", option)
                        try:
                            option.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", option)
                        time.sleep(0.12)
                        return True
                except Exception:
                    continue
        time.sleep(0.12)

    # JS fallback click.
    js = """
    const target = (arguments[0] || '').trim().toLowerCase();
    const options = Array.from(document.querySelectorAll(
      '.Select-menu-outer .Select-option, .Select-menu .Select-option, '
      + '[role="listbox"] [role="option"], [class*="menu"] [class*="option"], '
      + '[id*="react-select"][id*="-option-"]'
    ));
    for (const el of options) {
      const text = (el.textContent || '').trim().toLowerCase();
      if (text === target) {
        el.click();
        return true;
      }
    }
    for (const el of options) {
      const text = (el.textContent || '').trim().toLowerCase();
      if (text.includes(target) || target.includes(text)) {
        el.click();
        return true;
      }
    }
    return false;
    """
    return bool(_safe_execute_script(driver, js, target_raw, default=False))


def _dispatch_key_to_combo(driver: WebDriver, level_index: int, key: str) -> bool:
    js = """
    const idx = arguments[0];
    const key = arguments[1];
    let target = null;
    const items = document.querySelectorAll('.sell-category__item');
    if (idx === 0) {
      target = document.querySelector('.sell-category-select .Select-input[role="combobox"]')
        || document.querySelector('.sell-category-select [role="combobox"]')
        || document.querySelector('.sell-category-select input');
    } else if (items.length > idx) {
      target = items[idx].querySelector('.Select-input[role="combobox"]')
        || items[idx].querySelector('[role="combobox"]')
        || items[idx].querySelector('input');
    }
    if (!target) {
      const combos = document.querySelectorAll('[role="combobox"], .Select-input, .Select input');
      if (combos.length > idx) target = combos[idx];
    }
    if (!target) return false;
    target.focus();
    target.dispatchEvent(new KeyboardEvent('keydown', { key, code: key, bubbles: true }));
    target.dispatchEvent(new KeyboardEvent('keyup', { key, code: key, bubbles: true }));
    return true;
    """
    try:
        return bool(_safe_execute_script(driver, js, level_index, key, default=False))
    except Exception:
        return False


def _read_focused_option_text(driver: WebDriver) -> str:
    js = """
    const focused = document.querySelector('.Select-option.is-focused')
      || document.querySelector('[role="option"][aria-selected="true"]')
      || document.querySelector('[class*="option"][class*="focused"]');
    if (!focused) return '';
    return (focused.getAttribute('aria-label') || focused.textContent || '').trim();
    """
    try:
        return _normalize_space(str(_safe_execute_script(driver, js, default="") or ""))
    except Exception:
        return ""


def _collect_options_by_arrow(driver: WebDriver, level_index: int, max_steps: int = 140) -> List[Dict[str, str]]:
    if not _open_select(driver, level_index):
        return []
    out: List[Dict[str, str]] = []
    seen: Set[str] = set()
    repeated = 0
    first = ""
    for i in range(max_steps):
        if not _dispatch_key_to_combo(driver, level_index, "ArrowDown"):
            break
        time.sleep(0.08)
        txt = _read_focused_option_text(driver)
        if not txt:
            continue
        if not first:
            first = txt
        if txt in seen:
            repeated += 1
            if txt == first and len(seen) >= 2:
                break
            if repeated > 10:
                break
            continue
        seen.add(txt)
        out.append({"index": str(i), "text": txt, "href": ""})
    _dispatch_key_to_combo(driver, level_index, "Escape")
    return out


def _choose_option_by_arrow(driver: WebDriver, level_index: int, label: str) -> bool:
    target = _normalize_space(label).lower()
    if not target:
        return False
    if not _open_select(driver, level_index):
        return False
    seen: Set[str] = set()
    for _ in range(180):
        if not _dispatch_key_to_combo(driver, level_index, "ArrowDown"):
            break
        time.sleep(0.08)
        txt = _read_focused_option_text(driver)
        norm = _normalize_space(txt).lower()
        if not norm:
            continue
        if norm in seen and len(seen) > 2:
            break
        seen.add(norm)
        if norm == target or target in norm or norm in target:
            return _dispatch_key_to_combo(driver, level_index, "Enter")
    _dispatch_key_to_combo(driver, level_index, "Escape")
    return False


def _iter_unique(rows: Iterable[BuymaCategoryRow]) -> List[BuymaCategoryRow]:
    out: List[BuymaCategoryRow] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()
    for row in rows:
        key = row.dedupe_key()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _build_parent_candidates(parents: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for row in parents:
        label = _normalize_space(row.get("text", ""))
        if _is_placeholder_option(label):
            continue
        if not label or label in seen:
            continue
        seen.add(label)
        out.append({"index": row.get("index", ""), "text": label, "href": row.get("href", "")})
    for label in BUYMA_PARENT_CATEGORY_SEEDS:
        norm = _normalize_space(label)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append({"index": "", "text": norm, "href": ""})
    return out


def _get_selected_category_label(driver: WebDriver, level_index: int) -> str:
    js = """
    const idx = arguments[0];
    const labels = Array.from(document.querySelectorAll('.sell-category__item .Select-value-label'));
    if (labels.length > idx) return (labels[idx].textContent || '').trim();
    const legacy = document.querySelector('.sell-category-select .Select-value-label');
    if (idx === 0 && legacy) return (legacy.textContent || '').trim();
    return '';
    """
    return _normalize_space(str(_safe_execute_script(driver, js, level_index, default="") or ""))


def _looks_like_parent_option(text: str) -> bool:
    t = _normalize_space(text)
    if not t:
        return False
    return t in BUYMA_PARENT_CATEGORY_SEEDS


def _is_compatible_middle_selection(requested: str, actual: str) -> bool:
    req = _normalize_space(requested)
    act = _normalize_space(actual)
    if not req or not act:
        return False
    if req == act:
        return True
    if req in act or act in req:
        return True
    alias_pairs = {
        ("スマホケース・テックアクセサリー", "アクセサリー"),
    }
    return (req, act) in alias_pairs


def _is_placeholder_option(text: str) -> bool:
    t = _normalize_space(text)
    if not t:
        return True
    if t in PLACEHOLDER_LABELS:
        return True
    lower_t = t.lower()
    return "カテゴリから選択" in t or "select" == lower_t or "placeholder" in lower_t


def _append_warning(warnings: List[str], message: str, *, limit: int = 12) -> None:
    msg = (message or "").strip()
    if not msg:
        return
    if msg in warnings:
        return
    if len(warnings) >= limit:
        return
    warnings.append(msg)


def _has_category_controls(driver: WebDriver) -> bool:
    js = """
    const hasLegacy = !!document.querySelector('.sell-category-select, .sell-category__item');
    const hasReact = !!document.querySelector('[role="combobox"], [class*="-control"]');
    return hasLegacy || hasReact;
    """
    try:
        return bool(_safe_execute_script(driver, js, default=False))
    except Exception:
        return False


def _try_switch_to_frame_with_category_controls(driver: WebDriver) -> bool:
    driver.switch_to.default_content()
    if _has_category_controls(driver):
        return True
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for idx, frame in enumerate(frames):
        try:
            driver.switch_to.default_content()
            driver.switch_to.frame(frame)
            if _has_category_controls(driver):
                return True
        except Exception:
            continue
    driver.switch_to.default_content()
    return False


def _click_entry_candidates(driver: WebDriver) -> bool:
    js = """
    const keywords = ['出品', 'カテゴリ', 'カタログ', '판매', '출품', '카테고리'];
    const nodes = Array.from(document.querySelectorAll('a[href], button, input[type="button"], input[type="submit"]'));
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    for (const el of nodes) {
      if (!visible(el)) continue;
      const text = ((el.textContent || el.value || '') + ' ' + (el.getAttribute('aria-label') || '')).trim();
      const href = (el.getAttribute('href') || '').trim();
      const hitText = keywords.some(k => text.includes(k));
      const hitHref = href.includes('/my/sell/');
      if (hitText || hitHref) {
        el.click();
        return true;
      }
    }
    return false;
    """
    try:
        return bool(driver.execute_script(js))
    except Exception:
        return False


def _collect_selector_diagnostics(driver: WebDriver) -> Dict[str, object]:
    js = """
    return {
      url: window.location.href || '',
      title: document.title || '',
      iframes: document.querySelectorAll('iframe').length,
      legacyRootCount: document.querySelectorAll('.sell-category-select, .sell-category__item').length,
      reactControlCount: document.querySelectorAll('[role="combobox"], [class*="-control"]').length,
      optionCount: document.querySelectorAll('.Select-option, [role="option"], [class*="option"], [id*="react-select"][id*="-option-"]').length
    };
    """
    try:
        result = _safe_execute_script(driver, js, default={}) or {}
        return dict(result) if isinstance(result, dict) else {}
    except Exception:
        return {}


def _ensure_category_ui_ready(driver: WebDriver, warnings: List[str], timeout_sec: float = 15.0) -> bool:
    deadline = time.time() + max(1.0, timeout_sec)
    clicked = False
    while time.time() < deadline:
        if not _is_window_alive(driver):
            _append_warning(warnings, "browser window was closed during collection")
            return False
        _scroll_category_section_into_view(driver)
        if _try_switch_to_frame_with_category_controls(driver):
            return True
        if not clicked:
            clicked = _click_entry_candidates(driver)
        time.sleep(0.3)
    diag = _collect_selector_diagnostics(driver)
    _append_warning(
        warnings,
        "category UI not detected. "
        f"url={diag.get('url','')} iframes={diag.get('iframes',0)} "
        f"legacy={diag.get('legacyRootCount',0)} react={diag.get('reactControlCount',0)} options={diag.get('optionCount',0)}",
    )
    return False


def collect_buyma_category_hierarchy_with_stats(
    driver: WebDriver,
    *,
    page_url: str = "",
    max_parent: int = 120,
    max_middle: int = 300,
    max_child: int = 300,
) -> Tuple[List[BuymaCategoryRow], Dict[str, object]]:
    """Collect category hierarchy and include dedupe stats."""
    if page_url:
        driver.get(page_url)

    collected_at = _now_iso()
    raw_rows: List[BuymaCategoryRow] = []
    current_url = driver.current_url

    warnings: List[str] = []
    selector_failure_count = 0

    if not _is_window_alive(driver):
        return [], {
            "raw_count": 0,
            "deduped_count": 0,
            "duplicate_skipped_count": 0,
            "blank_category_id_count": 0,
            "selector_failure_count": 1,
            "warnings": ["browser window is not available before collection started"],
        }

    if not _ensure_category_ui_ready(driver, warnings):
        return [], {
            "raw_count": 0,
            "deduped_count": 0,
            "duplicate_skipped_count": 0,
            "blank_category_id_count": 0,
            "selector_failure_count": 1,
            "warnings": warnings,
        }

    if not _open_select(driver, 0):
        diag = _collect_selector_diagnostics(driver)
        return [], {
            "raw_count": 0,
            "deduped_count": 0,
            "duplicate_skipped_count": 0,
            "blank_category_id_count": 0,
            "selector_failure_count": 1,
            "warnings": [
                "parent selector open failed; React-Select DOM may have changed or login may be required",
                "diagnostic: "
                f"url={diag.get('url','')} legacy={diag.get('legacyRootCount',0)} "
                f"react={diag.get('reactControlCount',0)} options={diag.get('optionCount',0)}",
            ],
        }

    parents = _read_open_options(driver)[: max_parent if max_parent > 0 else None]
    if not parents:
        parents = _collect_options_by_arrow(driver, 0, max_parent if max_parent > 0 else 120)
    parent_candidates = _build_parent_candidates(parents)
    if not parents:
        _append_warning(warnings, "no parent category options were detected; check login/account visibility")
    elif len(parents) < 3:
        _append_warning(
            warnings,
            f"parent category options look incomplete (detected={len(parents)}); account/category visibility may be limited",
        )
    available_parent_count = 0
    for parent in parent_candidates:
        if not _is_window_alive(driver):
            _append_warning(warnings, "browser window was closed while reading parent categories")
            break
        p = parent["text"]
        if _is_placeholder_option(p):
            continue
        if not p:
            continue
        if not _open_select(driver, 0):
            selector_failure_count += 1
            _append_warning(warnings, f"failed to reopen parent selector while processing '{p}'")
            continue
        if not _choose_open_option_by_text(driver, p):
            if not _choose_option_by_arrow(driver, 0, p):
                selector_failure_count += 1
                if p in BUYMA_PARENT_CATEGORY_SEEDS:
                    _append_warning(warnings, f"parent category not selectable in current account/view: '{p}'")
                else:
                    _append_warning(warnings, f"failed to select parent option '{p}'")
                continue
        selected_parent = _get_selected_category_label(driver, 0)
        if selected_parent and selected_parent != p:
            selector_failure_count += 1
            _append_warning(
                warnings,
                f"parent selection mismatch requested='{p}' actual='{selected_parent}' (skipping this parent)",
            )
            continue
        # BUYMA creates middle-category options after parent click; give it a brief render window.
        try:
            WebDriverWait(driver, 2.5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".sell-category__item:nth-of-type(2), .sell-category__item .Select-control")
                )
            )
        except Exception:
            pass
        time.sleep(0.15)
        available_parent_count += 1

        parent_url = parent.get("href", "") or current_url
        parent_id = _extract_category_id(parent_url)
        raw_rows.append(
            BuymaCategoryRow(
                parent_category=p,
                middle_category="",
                child_category="",
                category_url=parent_url,
                category_id=parent_id,
                raw_text=p,
                collected_at=collected_at,
            )
        )

        if not _open_select(driver, 1):
            selector_failure_count += 1
            _append_warning(warnings, f"middle selector is not available under parent '{p}'")
            continue
        middles = _read_open_options(driver)[: max_middle if max_middle > 0 else None]
        if not middles:
            middles = _collect_options_by_arrow(driver, 1, max_middle if max_middle > 0 else 180)
        middles = [row for row in middles if not _looks_like_parent_option(row.get("text", ""))]
        if not middles:
            _append_warning(warnings, f"no middle options detected under parent '{p}'")
        for middle in middles:
            m = middle["text"]
            if _is_placeholder_option(m):
                continue
            if not m:
                continue
            if _looks_like_parent_option(m):
                _append_warning(
                    warnings,
                    f"wrong dropdown context under '{p}' (middle option looks like parent: '{m}')",
                )
                continue
            if not _open_select(driver, 1):
                selector_failure_count += 1
                _append_warning(warnings, f"failed to reopen middle selector under '{p}'")
                continue
            if not _choose_open_option_by_text(driver, m):
                if not _choose_option_by_arrow(driver, 1, m):
                    selector_failure_count += 1
                    _append_warning(warnings, f"failed to select middle option '{m}' under '{p}'")
                    continue
            selected_middle = _get_selected_category_label(driver, 1)
            if selected_middle and selected_middle != m:
                if _is_compatible_middle_selection(m, selected_middle):
                    m = selected_middle
                else:
                    _append_warning(
                        warnings,
                        f"middle selection mismatch under '{p}' requested='{m}' actual='{selected_middle}'",
                    )
                    continue

            middle_url = middle.get("href", "") or parent_url or current_url
            middle_id = _extract_category_id(middle_url)
            raw_rows.append(
                BuymaCategoryRow(
                    parent_category=p,
                    middle_category=m,
                    child_category="",
                    category_url=middle_url,
                    category_id=middle_id,
                    raw_text=f"{p} > {m}",
                    collected_at=collected_at,
                )
            )

            if not _open_select(driver, 2):
                # Some middle categories are legitimate leaves with no child selector.
                continue
            children = _read_open_options(driver)[: max_child if max_child > 0 else None]
            if not children:
                children = _collect_options_by_arrow(driver, 2, max_child if max_child > 0 else 220)
            for child in children:
                c = child["text"]
                if _is_placeholder_option(c):
                    continue
                if not c:
                    continue
                child_url = child.get("href", "") or middle_url or parent_url or current_url
                child_id = _extract_category_id(child_url)
                raw_rows.append(
                    BuymaCategoryRow(
                        parent_category=p,
                        middle_category=m,
                        child_category=c,
                        category_url=child_url,
                        category_id=child_id,
                        raw_text=f"{p} > {m} > {c}",
                        collected_at=collected_at,
                    )
                )

    if available_parent_count < 2:
        _append_warning(
            warnings,
            f"only {available_parent_count} parent categories were selectable; collect again with broader account permissions",
        )

    deduped = _iter_unique(raw_rows)
    blank_category_id_count = sum(1 for row in deduped if not (row.category_id or "").strip())
    stats = {
        "raw_count": len(raw_rows),
        "deduped_count": len(deduped),
        "duplicate_skipped_count": max(0, len(raw_rows) - len(deduped)),
        "blank_category_id_count": blank_category_id_count,
        "selector_failure_count": selector_failure_count,
        "warnings": warnings,
    }
    return deduped, stats


def rows_to_dicts(rows: Iterable[BuymaCategoryRow]) -> List[Dict[str, str]]:
    return [asdict(row) for row in rows]
