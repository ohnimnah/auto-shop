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


driver = setup_visible_chrome_driver()
try:
    driver.get(BUYMA_SELL_URL)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".bmm-c-heading__ttl")))
    time.sleep(2)
    _dismiss_overlay(driver)
    _select_category_by_arrow(driver, 0, "レディースファッション")
    time.sleep(0.6)
    _find_best_option_by_arrow(driver, 1, "ボトムス")
    time.sleep(0.6)
    _find_best_option_by_arrow(driver, 2, "パンツ")
    time.sleep(1)

    rows = driver.execute_script("""
        var out = [];
        var fields = document.querySelectorAll('.bmm-c-field, .sell-variation, form div');
        for (var i = 0; i < fields.length; i++) {
            var el = fields[i];
            var ta = el.querySelector('textarea.bmm-c-textarea, textarea');
            if (!ta) continue;
            var label = el.querySelector('.bmm-c-field__label, label, h2, h3, p');
            out.push({
                idx: i,
                label: label ? (label.textContent || '').trim() : '',
                className: (el.className || '').toString(),
                textareaClass: (ta.className || '').toString(),
                placeholder: ta.getAttribute('placeholder') || '',
                parentText: (el.textContent || '').trim().slice(0, 180)
            });
        }
        return out;
    """)

    print('FOUND:', len(rows))
    for r in rows[:60]:
        print('---')
        print('idx=', r['idx'])
        print('label=', r['label'])
        print('class=', r['className'][:140])
        print('taClass=', r['textareaClass'])
        print('placeholder=', r['placeholder'])
        print('text=', r['parentText'])
finally:
    driver.quit()
