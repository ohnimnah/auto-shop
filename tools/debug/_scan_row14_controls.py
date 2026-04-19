import time
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from buyma_upload import (
    setup_visible_chrome_driver,
    BUYMA_SELL_URL,
    _dismiss_overlay,
    _select_category_by_arrow,
    _find_best_option_by_arrow,
)


OUT = []


def log(msg: str):
    OUT.append(msg)


def dump_elements(title, elements, max_n=30):
    log(f"\n=== {title} ({len(elements)}) ===")
    for i, el in enumerate(elements[:max_n]):
        try:
            txt = (el.text or '').strip().replace('\n', ' / ')
            tag = el.tag_name
            cls = (el.get_attribute('class') or '')[:120]
            rid = (el.get_attribute('id') or '')[:80]
            role = (el.get_attribute('role') or '')[:40]
            log(f"[{i}] tag={tag} id={rid} role={role} class={cls} text={txt[:140]}")
        except Exception as e:
            log(f"[{i}] <error: {e}>")


driver = setup_visible_chrome_driver()
try:
    driver.get(BUYMA_SELL_URL)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".bmm-c-heading__ttl")))
    time.sleep(2)
    _dismiss_overlay(driver)

    # row14 expected category path
    _select_category_by_arrow(driver, 0, "レディースファッション")
    time.sleep(0.6)
    _find_best_option_by_arrow(driver, 1, "ボトムス")
    time.sleep(0.6)
    _find_best_option_by_arrow(driver, 2, "パンツ")
    time.sleep(1.0)

    # color area
    color_root = driver.find_element(By.CSS_SELECTOR, ".sell-color-table")
    log("\n=== COLOR ROOT HTML (head) ===")
    log((color_root.get_attribute("outerHTML") or "")[:8000])

    color_btns = color_root.find_elements(By.CSS_SELECTOR, "button, a, [role='button'], [class*='add'], [class*='plus']")
    dump_elements("COLOR BUTTON CANDIDATES", color_btns)

    # size area
    variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
    log("\n=== VARIATION ROOT HTML (head) ===")
    log((variation.get_attribute("outerHTML") or "")[:12000])

    size_tabs = variation.find_elements(By.CSS_SELECTOR, ".sell-variation__tab-item, [role='tab']")
    dump_elements("SIZE TAB CANDIDATES", size_tabs)

    size_toggle_candidates = variation.find_elements(
        By.XPATH,
        ".//*[contains(normalize-space(.),'サイズ') or contains(normalize-space(.),'バリエーション') or contains(normalize-space(.),'指定')]"
    )
    dump_elements("SIZE TOGGLE TEXT CANDIDATES", size_toggle_candidates, max_n=80)

    labels = variation.find_elements(By.CSS_SELECTOR, "label")
    dump_elements("ALL VARIATION LABELS", labels, max_n=100)

    inputs = variation.find_elements(By.CSS_SELECTOR, "input, select, textarea")
    log(f"\n=== FORM CONTROLS ({len(inputs)}) ===")
    for i, ipt in enumerate(inputs[:200]):
        try:
            tag = ipt.tag_name
            typ = (ipt.get_attribute('type') or '')[:30]
            name = (ipt.get_attribute('name') or '')[:80]
            val = (ipt.get_attribute('value') or '')[:80]
            rid = (ipt.get_attribute('id') or '')[:80]
            cls = (ipt.get_attribute('class') or '')[:120]
            ph = (ipt.get_attribute('placeholder') or '')[:80]
            dis = ipt.get_attribute('disabled')
            chk = ipt.get_attribute('checked')
            log(f"[{i}] tag={tag} type={typ} name={name} id={rid} value={val} placeholder={ph} disabled={dis} checked={chk} class={cls}")
        except Exception as e:
            log(f"[{i}] control error: {e}")

finally:
    driver.quit()

out_file = Path("row14_controls_dump.txt")
out_file.write_text("\n".join(OUT), encoding="utf-8")
print(f"wrote: {out_file.resolve()}")
