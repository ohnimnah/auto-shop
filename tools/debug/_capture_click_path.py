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

    driver.execute_script("""
window.__last_click_info = null;
(function(){
  const cssPath = (el) => {
    if (!el) return '';
    const parts = [];
    while (el && el.nodeType === 1 && parts.length < 8) {
      let part = el.tagName.toLowerCase();
      if (el.id) part += '#' + el.id;
      else {
        if (el.className && typeof el.className === 'string') {
          const c = el.className.trim().split(/\\s+/).slice(0,2).join('.');
          if (c) part += '.' + c;
        }
        let i = 1, sib = el;
        while ((sib = sib.previousElementSibling) != null) i++;
        part += `:nth-child(${i})`;
      }
      parts.unshift(part);
      el = el.parentElement;
    }
    return parts.join(' > ');
  };
  document.addEventListener('click', function(e){
    const t = e.target;
    window.__last_click_info = {
      text: (t && t.textContent ? t.textContent.trim().slice(0,120) : ''),
      tag: t ? t.tagName : '',
      id: t ? t.id : '',
      cls: t ? t.className : '',
      path: cssPath(t),
      time: Date.now()
    };
  }, true);
})();
""")

    print('이제 브라우저에서 사이즈/변형 토글을 1번 클릭하세요. 20초 대기 후 마지막 클릭 경로를 출력합니다.')
    time.sleep(20)
    info = driver.execute_script("return window.__last_click_info")
    print(info)
finally:
    driver.quit()
