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
