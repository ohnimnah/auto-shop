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


def _open_select(driver: WebDriver, level_index: int, timeout: float = 5.0) -> bool:
    js = """
    const idx = arguments[0];
    let el = null;
    if (idx === 0) {
      el = document.querySelector('.sell-category-select .Select-control')
        || document.querySelector('.sell-category-select');
    } else {
      const items = document.querySelectorAll('.sell-category__item');
      if (items.length > idx) {
        el = items[idx].querySelector('.Select-control') || items[idx].querySelector('.Select');
      }
    }
    if (!el) return false;
    el.click();
    return true;
    """
    ok = bool(driver.execute_script(js, level_index))
    if not ok:
        return False
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".Select-menu-outer .Select-option"))
        )
        return True
    except Exception:
        return False


def _read_open_options(driver: WebDriver) -> List[Dict[str, str]]:
    js = """
    const options = Array.from(document.querySelectorAll('.Select-menu-outer .Select-option'));
    return options.map((el, i) => {
      const text = (el.textContent || '').trim();
      const href = el.getAttribute('href') || '';
      return { index: String(i), text, href };
    }).filter(o => o.text);
    """
    rows = driver.execute_script(js) or []
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
    js = """
    const target = (arguments[0] || '').trim().toLowerCase();
    const options = Array.from(document.querySelectorAll('.Select-menu-outer .Select-option'));
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
    return bool(driver.execute_script(js, label))


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


def _append_warning(warnings: List[str], message: str, *, limit: int = 12) -> None:
    msg = (message or "").strip()
    if not msg:
        return
    if msg in warnings:
        return
    if len(warnings) >= limit:
        return
    warnings.append(msg)


def collect_buyma_category_hierarchy(
    driver: WebDriver,
    *,
    page_url: str = "",
    max_parent: int = 120,
    max_middle: int = 300,
    max_child: int = 300,
) -> List[BuymaCategoryRow]:
    """Collect BUYMA category hierarchy from category selects on page.

    This collector expects BUYMA category React-Select UI to be present.
    """
    if page_url:
        driver.get(page_url)

    collected_at = _now_iso()
    rows: List[BuymaCategoryRow] = []
    current_url = driver.current_url

    # Parent
    if not _open_select(driver, 0):
        return []
    parents = _read_open_options(driver)[: max_parent if max_parent > 0 else None]

    for parent in parents:
        p = parent["text"]
        if not p:
            continue
        if not _open_select(driver, 0):
            continue
        if not _choose_open_option_by_text(driver, p):
            continue

        parent_url = parent.get("href", "") or current_url
        parent_id = _extract_category_id(parent_url)

        rows.append(
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

        # Middle
        if not _open_select(driver, 1):
            continue
        middles = _read_open_options(driver)[: max_middle if max_middle > 0 else None]
        for middle in middles:
            m = middle["text"]
            if not m:
                continue

            if not _open_select(driver, 1):
                continue
            if not _choose_open_option_by_text(driver, m):
                continue

            middle_url = middle.get("href", "") or parent_url or current_url
            middle_id = _extract_category_id(middle_url)
            rows.append(
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

            # Child
            if not _open_select(driver, 2):
                continue
            children = _read_open_options(driver)[: max_child if max_child > 0 else None]
            for child in children:
                c = child["text"]
                if not c:
                    continue
                child_url = child.get("href", "") or middle_url or parent_url or current_url
                child_id = _extract_category_id(child_url)
                rows.append(
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

    return _iter_unique(rows)


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

    if not _open_select(driver, 0):
        return [], {
            "raw_count": 0,
            "deduped_count": 0,
            "duplicate_skipped_count": 0,
            "blank_category_id_count": 0,
            "selector_failure_count": 1,
            "warnings": ["parent selector open failed; React-Select DOM may have changed or login may be required"],
        }

    parents = _read_open_options(driver)[: max_parent if max_parent > 0 else None]
    if not parents:
        _append_warning(warnings, "no parent category options were detected; check login/account visibility")
    elif len(parents) < 3:
        _append_warning(
            warnings,
            f"parent category options look incomplete (detected={len(parents)}); account/category visibility may be limited",
        )
    for parent in parents:
        p = parent["text"]
        if not p:
            continue
        if not _open_select(driver, 0):
            selector_failure_count += 1
            _append_warning(warnings, f"failed to reopen parent selector while processing '{p}'")
            continue
        if not _choose_open_option_by_text(driver, p):
            selector_failure_count += 1
            _append_warning(warnings, f"failed to select parent option '{p}'")
            continue

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
            _append_warning(warnings, f"no middle options detected under parent '{p}'")
        for middle in middles:
            m = middle["text"]
            if not m:
                continue
            if not _open_select(driver, 1):
                selector_failure_count += 1
                _append_warning(warnings, f"failed to reopen middle selector under '{p}'")
                continue
            if not _choose_open_option_by_text(driver, m):
                selector_failure_count += 1
                _append_warning(warnings, f"failed to select middle option '{m}' under '{p}'")
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
                selector_failure_count += 1
                _append_warning(warnings, f"child selector is not available for '{p} > {m}'")
                continue
            children = _read_open_options(driver)[: max_child if max_child > 0 else None]
            if not children:
                _append_warning(warnings, f"no child options detected for '{p} > {m}'")
            for child in children:
                c = child["text"]
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
