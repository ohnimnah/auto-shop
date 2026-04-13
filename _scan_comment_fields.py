import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from buyma_upload import setup_visible_chrome_driver, BUYMA_SELL_URL, _dismiss_overlay, _select_category_by_arrow, _find_best_option_by_arrow


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
