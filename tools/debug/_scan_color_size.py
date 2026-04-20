"""색상/사이즈/브랜드 영역의 HTML 구조를 스캔하는 스크립트"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from marketplace.buyma.selectors import BUYMA_SELL_URL
from marketplace.buyma.login import setup_visible_chrome_driver
from marketplace.buyma import category as buyma_category_mod
from marketplace.buyma import ui as buyma_ui_mod


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _scroll_and_click(driver, element):
    return buyma_ui_mod.scroll_and_click(driver, element, sleep_fn=_sleep)


def _dismiss_overlay(driver):
    return buyma_ui_mod.dismiss_overlay(driver, sleep_fn=_sleep)


def _select_category_by_arrow(driver, item_index: int, target_label: str) -> bool:
    return buyma_category_mod.select_category_by_typing(
        driver,
        item_index,
        target_label,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )


def _find_best_option_by_arrow(driver, item_index: int, target_keyword: str, fallback_other: bool = True) -> bool:
    return buyma_category_mod.find_best_option_by_arrow(
        driver,
        item_index,
        target_keyword,
        fallback_other=fallback_other,
        sleep_fn=_sleep,
        scroll_and_click=_scroll_and_click,
    )

driver = setup_visible_chrome_driver()
driver.get(BUYMA_SELL_URL)
WebDriverWait(driver, 15).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, ".bmm-c-heading__ttl"))
)
time.sleep(3)

# 먼저 카테고리를 선택해야 사이즈가 나옴
# 대카테: レディースファッション 선택 (index 0)
_dismiss_overlay(driver)
_select_category_by_arrow(driver, 0, "レディースファッション")
time.sleep(1)
_find_best_option_by_arrow(driver, 1, "ファッション雑貨・小物")
time.sleep(1)
# 소카테
items_count = len(driver.find_elements(By.CSS_SELECTOR, '.sell-category__item'))
if items_count >= 3:
    _find_best_option_by_arrow(driver, 2, "財布")
    time.sleep(1)

print("\n=== 브랜드 영역 ===")
try:
    brand_input = driver.find_element(By.CSS_SELECTOR, "input[placeholder*='ブランド名を入力']")
    print(f"  Found: tag={brand_input.tag_name}, type={brand_input.get_attribute('type')}")
    print(f"  placeholder={brand_input.get_attribute('placeholder')}")
    parent = brand_input.find_element(By.XPATH, "./..")
    print(f"  Parent: tag={parent.tag_name}, class={parent.get_attribute('class')}")
    gp = parent.find_element(By.XPATH, "./..")
    print(f"  Grandparent: tag={gp.tag_name}, class={gp.get_attribute('class')}")
    # 자동완성 목록 구조 확인
    brand_input.clear()
    brand_input.send_keys("SCULPTOR")
    time.sleep(3)
    suggests = driver.find_elements(By.CSS_SELECTOR, "[class*='suggest'] li, .bmm-c-suggest__list li, [class*='autocomplete'] li, [role='option'], [role='listbox'] li")
    print(f"  Suggestions found: {len(suggests)}")
    for s in suggests[:5]:
        print(f"    - {s.text[:80]}")
    # 더 넓은 범위 검색
    all_lists = driver.find_elements(By.CSS_SELECTOR, "ul, [role='listbox']")
    for lst in all_lists:
        if lst.is_displayed() and lst.text.strip():
            print(f"  Visible list: tag={lst.tag_name} class={lst.get_attribute('class')[:80]} text={lst.text[:100]}")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== 색상 영역 ===")
try:
    # 색상은 sell-variation 영역에 있음
    variation = driver.find_elements(By.CSS_SELECTOR, ".sell-variation, [class*='variation']")
    print(f"  Variation containers: {len(variation)}")
    for v in variation[:3]:
        print(f"    class={v.get_attribute('class')[:80]}")

    # 색상 탭 찾기
    tabs = driver.find_elements(By.CSS_SELECTOR, ".sell-variation__tab-item, [class*='tab-item']")
    print(f"  Tabs: {len(tabs)}")
    for t in tabs:
        print(f"    text='{t.text}' aria-selected={t.get_attribute('aria-selected')} aria-controls={t.get_attribute('aria-controls')}")

    # 색상 탭 클릭
    for t in tabs:
        if 'カラー' in t.text or '色' in t.text:
            t.click()
            time.sleep(1)
            panel_id = t.get_attribute('aria-controls')
            if panel_id:
                panel = driver.find_element(By.ID, panel_id)
                html = panel.get_attribute('innerHTML')
                print(f"  Color panel HTML (first 2000 chars):")
                print(html[:2000])
            break
    else:
        # 탭이 없으면 다른 방식으로 색상 찾기
        color_selects = driver.find_elements(By.CSS_SELECTOR, ".Select")
        print(f"  Select containers: {len(color_selects)}")
        for i, sel in enumerate(color_selects):
            try:
                placeholder = sel.find_element(By.CSS_SELECTOR, ".Select-placeholder, .Select-value-label")
                print(f"    Select[{i}]: {placeholder.text}")
            except:
                print(f"    Select[{i}]: (no placeholder)")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== 사이즈 영역 ===")
try:
    for t in tabs:
        if 'サイズ' in t.text:
            t.click()
            time.sleep(1)
            panel_id = t.get_attribute('aria-controls')
            if panel_id:
                panel = driver.find_element(By.ID, panel_id)
                html = panel.get_attribute('innerHTML')
                print(f"  Size panel HTML (first 2000 chars):")
                print(html[:2000])
                labels = panel.find_elements(By.CSS_SELECTOR, "label")
                print(f"  Labels: {len(labels)}")
                for l in labels[:20]:
                    print(f"    '{l.text.strip()}'")
            break
except Exception as e:
    print(f"  Error: {e}")

print("\n=== 전체 variation 영역 outer HTML ===")
try:
    var_section = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
    outer = var_section.get_attribute('outerHTML')
    print(outer[:5000])
except Exception as e:
    print(f"  Error: {e}")

input("\n완료. Enter로 종료...")
driver.quit()
