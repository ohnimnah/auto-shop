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


def metrics(driver):
    labels = driver.find_elements(By.CSS_SELECTOR, ".sell-variation label")
    selects = driver.find_elements(By.CSS_SELECTOR, ".sell-variation .Select")
    visible_inputs = [
        i for i in driver.find_elements(
            By.CSS_SELECTOR,
            ".sell-variation input[type='text'], .sell-variation input.bmm-c-text-field"
        ) if i.is_displayed()
    ]
    return len(labels), len(selects), len(visible_inputs)


def dump_snapshot(driver, tag):
    out = []
    out.append(f"SNAPSHOT: {tag}")
    out.append(f"TIME: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    variation = driver.find_element(By.CSS_SELECTOR, ".sell-variation")
    out.append("\n=== VARIATION HTML (head) ===")
    out.append((variation.get_attribute("outerHTML") or "")[:25000])

    selects = driver.find_elements(By.CSS_SELECTOR, ".sell-variation .Select")
    out.append(f"\n=== SELECT COUNT: {len(selects)} ===")
    for idx, sel in enumerate(selects):
        try:
            ph = sel.find_elements(By.CSS_SELECTOR, ".Select-placeholder, .Select-value-label")
            ph_text = " | ".join([(p.text or '').strip() for p in ph if (p.text or '').strip()])
            out.append(f"[{idx}] class={(sel.get_attribute('class') or '')[:120]} placeholder={ph_text}")
        except Exception as e:
            out.append(f"[{idx}] error: {e}")

    file_path = Path(f"row14_snapshot_{tag}.txt")
    file_path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote snapshot: {file_path.resolve()}")


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

    l0, s0, t0 = metrics(driver)
    print(f"baseline: labels={l0}, selects={s0}, text_inputs={t0}")
    dump_snapshot(driver, "baseline")

    print("지금 브라우저에서 토글을 클릭하세요. 90초 감시합니다.")
    for sec in range(90):
        l, s, t = metrics(driver)
        print(f"{sec:02d}: labels={l}, selects={s}, text_inputs={t}")

        if s > s0 or l > l0 or t > t0:
            tag = f"changed_{sec:02d}_l{l}_s{s}_t{t}"
            dump_snapshot(driver, tag)
            print("변화 감지됨: 스냅샷 저장 완료")
            break
        time.sleep(1)
    else:
        print("변화 없음")
finally:
    driver.quit()
