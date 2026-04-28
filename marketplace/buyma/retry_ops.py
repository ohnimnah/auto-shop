from __future__ import annotations

from typing import Any

from tenacity import retry, stop_after_attempt, wait_fixed


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def safe_click(driver: Any, target: Any) -> None:
    try:
        target.click()
    except Exception:
        driver.execute_script("arguments[0].click();", target)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def safe_send_keys(target: Any, value: str) -> None:
    target.send_keys(value)

