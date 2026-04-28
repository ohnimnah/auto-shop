from __future__ import annotations

from typing import Any

try:
    from tenacity import retry, stop_after_attempt, wait_fixed
except Exception:  # pragma: no cover
    def retry(*_args, **_kwargs):
        def _decorator(fn):
            return fn

        return _decorator

    def stop_after_attempt(_n):
        return None

    def wait_fixed(_n):
        return None


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def safe_click(driver: Any, target: Any) -> None:
    try:
        target.click()
    except Exception:
        driver.execute_script("arguments[0].click();", target)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def safe_send_keys(target: Any, value: str) -> None:
    target.send_keys(value)
