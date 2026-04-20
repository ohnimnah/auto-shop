"""BUYMA submit/finalization helpers."""

import time
from typing import Callable, List, Tuple

from selenium.webdriver.common.by import By

from marketplace.buyma.selectors import BUYMA_BUTTON_SELECTOR


def find_buyma_button_by_keywords(driver, keywords: List[str], timeout: float = 0.0, sleep_fn: Callable[[float], None] = time.sleep):
    end_time = time.time() + max(0.0, timeout)
    while True:
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, BUYMA_BUTTON_SELECTOR)
            for candidate in candidates:
                text = (candidate.text or "").strip()
                value = (candidate.get_attribute("value") or "").strip()
                label = f"{text} {value}".strip()
                if any(keyword in label for keyword in keywords):
                    return candidate
        except Exception:
            pass

        if time.time() >= end_time:
            return None
        sleep_fn(0.5)


def click_buyma_button(driver, button, success_message: str, click_fallback: Callable | None = None) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", button)
        print(success_message)
        return True
    except Exception:
        if click_fallback is None:
            return False
        try:
            click_fallback(driver, button)
            print(success_message)
            return True
        except Exception:
            return False


def submit_buyma_listing(driver, row_num: int, click_fallback: Callable | None = None, sleep_fn: Callable[[float], None] = time.sleep) -> bool:
    try:
        submit_btn = find_buyma_button_by_keywords(
            driver,
            ["入力内容を確認する", "入力内容", "確認"],
            sleep_fn=sleep_fn,
        )
        if not submit_btn:
            raise RuntimeError("입력 내용 확인 버튼을 찾지 못했습니다.")
        if not click_buyma_button(driver, submit_btn, f"  ✓ {row_num}행 출품 확인 버튼 자동 클릭!", click_fallback=click_fallback):
            raise RuntimeError("입력 내용 확인 버튼 클릭에 실패했습니다.")
        sleep_fn(3)
        return True
    except Exception as exc:
        print(f"  ✗ 출품 버튼 자동 클릭 실패: {exc}")
        return False


def finalize_buyma_listing(driver, row_num: int, click_fallback: Callable | None = None, sleep_fn: Callable[[float], None] = time.sleep) -> bool:
    try:
        final_btn = find_buyma_button_by_keywords(
            driver,
            ["この内容で出品する", "出品する", "公開する", "登録する", "完了する"],
            timeout=10.0,
            sleep_fn=sleep_fn,
        )
        if not final_btn:
            raise RuntimeError("최종 출품 버튼을 찾지 못했습니다.")
        if not click_buyma_button(driver, final_btn, f"  ✓ {row_num}행 최종 출품 버튼 자동 클릭!", click_fallback=click_fallback):
            raise RuntimeError("최종 출품 버튼 클릭에 실패했습니다.")
        sleep_fn(3)
        return True
    except Exception as exc:
        print(f"  ✗ 최종 출품 자동 클릭 실패: {exc}")
        return False


def handle_success_after_fill(
    driver,
    row_num: int,
    upload_mode: str,
    interactive: bool = True,
    *,
    safe_input_fn: Callable[[str], str] = input,
    sleep_fn: Callable[[float], None] = time.sleep,
    click_fallback: Callable | None = None,
) -> Tuple[bool, bool]:
    print("\n  폼 입력이 완료되었습니다.")

    if upload_mode == "auto":
        print("  오류가 없어 자동 제출을 진행합니다.")
        if not submit_buyma_listing(driver, row_num, click_fallback=click_fallback, sleep_fn=sleep_fn):
            print("  브라우저에서 직접 출품해주세요.")
            if interactive:
                safe_input_fn("  출품 후 Enter를 눌러주세요..")
            return True, False
        if not finalize_buyma_listing(driver, row_num, click_fallback=click_fallback, sleep_fn=sleep_fn):
            print("  확인 페이지에서 직접 최종 출품해주세요.")
            if interactive:
                safe_input_fn("  최종 출품 후 Enter를 눌러주세요..")
            return True, False
        return True, True

    if not interactive:
        print("  감시 모드(review)에서는 제출 대기 없이 다음 점검으로 진행합니다.")
        return True, False

    print("  확인용 모드입니다. 브라우저에서 내용을 검토한 뒤 선택해주세요.\n")
    while True:
        answer = safe_input_fn("  [e] 출품 완료 / [s] 건너뛰기 / [q] 종료: ").strip().lower()
        if answer in {"e", "enter", ""}:
            return True, False
        if answer == "s":
            return True, False
        if answer == "q":
            return False, False
