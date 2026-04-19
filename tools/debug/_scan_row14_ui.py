import time
from buyma_upload import setup_visible_chrome_driver, BUYMA_SELL_URL, _dismiss_overlay, _select_category_by_arrow, _find_best_option_by_arrow
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


driver = setup_visible_chrome_driver()
driver.get(BUYMA_SELL_URL)
WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".bmm-c-heading__ttl")))
time.sleep(2)
_dismiss_overlay(driver)

# row14 의도 카테고리: レディースファッション > ボトムス > パンツ
_select_category_by_arrow(driver, 0, "レディースファッション")
time.sleep(0.6)
_find_best_option_by_arrow(driver, 1, "ボトムス")
time.sleep(0.6)
_find_best_option_by_arrow(driver, 2, "パンツ")
time.sleep(1.0)

print("=== COLOR TABLE ===")
try:
    color_table = driver.find_element(By.CSS_SELECTOR, ".sell-color-table")
    html = color_table.get_attribute("outerHTML")
    print(html[:7000])
except Exception as e:
    print("color table error:", e)

print("=== COLOR ADD BUTTON CANDIDATES ===")
for sel in [
    ".sell-color-table button",
    ".sell-color-table [class*='add']",
    ".sell-color-table .bmm-c-ico-plus",
    ".sell-color-table a",
]:
    try:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        print(sel, len(els))
        for e in els[:5]:
            print("  -", (e.text or '').strip(), "| class=", e.get_attribute("class"))
    except Exception:
        pass

print("=== SIZE TAB/PANEL ===")
try:
    tabs = driver.find_elements(By.CSS_SELECTOR, ".sell-variation__tab-item")
    for t in tabs:
        if "サイズ" in t.text:
            driver.execute_script("arguments[0].scrollIntoView({block:'start'}); window.scrollBy(0,-180);", t)
            t.click()
            time.sleep(1)
            panel_id = t.get_attribute("aria-controls")
            panel = driver.find_element(By.ID, panel_id)
            labels = panel.find_elements(By.CSS_SELECTOR, "label")
            print("size labels:", len(labels))
            for lb in labels[:40]:
                txt = (lb.text or '').strip()
                if txt:
                    print(" -", txt)
            print("panel html:")
            print(panel.get_attribute("outerHTML")[:7000])
            break
except Exception as e:
    print("size panel error:", e)

input("done")
driver.quit()
