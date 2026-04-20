import time
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


def count_controls(driver):
    labels = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
    selects = driver.find_elements(By.CSS_SELECTOR, ".sell-variation .Select")
    text_inputs = driver.find_elements(By.CSS_SELECTOR, ".sell-variation input[type='text'], .sell-variation input.bmm-c-text-field")
    visible_inputs = [i for i in text_inputs if i.is_displayed()]
    return len(labels), len(selects), len(visible_inputs)


driver = setup_visible_chrome_driver()
try:
    driver.get(BUYMA_SELL_URL)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".bmm-c-heading__ttl")))
    time.sleep(2)
    _dismiss_overlay(driver)

    # row14 expected path
    _select_category_by_arrow(driver, 0, "レディースファッション")
    time.sleep(0.6)
    _find_best_option_by_arrow(driver, 1, "ボトムス")
    time.sleep(0.6)
    _find_best_option_by_arrow(driver, 2, "パンツ")
    time.sleep(1)

    print("브라우저에서 사이즈/변형 관련 토글을 직접 클릭해보세요. 60초 동안 감시합니다.")
    print("time,label_count,select_count,visible_text_inputs")

    for sec in range(61):
        l, s, t = count_controls(driver)
        print(f"{sec:02d},{l},{s},{t}")
        time.sleep(1)

finally:
    driver.quit()
