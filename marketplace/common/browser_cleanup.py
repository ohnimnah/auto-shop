"""Browser cleanup helpers shared by crawler and uploader scripts."""

from __future__ import annotations

import threading
from typing import Callable


def quit_driver_safely(driver, *, timeout: float = 8.0, log: Callable[[str], None] | None = None) -> bool:
    """Quit Selenium driver with a timeout so launcher one-shot jobs can finish."""
    if driver is None:
        return True

    done = threading.Event()

    def _quit() -> None:
        try:
            driver.quit()
        finally:
            done.set()

    thread = threading.Thread(target=_quit, daemon=True)
    thread.start()
    thread.join(timeout)
    if done.is_set():
        return True

    if log:
        try:
            log("브라우저 종료가 지연되어 드라이버 프로세스를 정리합니다.")
        except Exception:
            pass
    try:
        proc = getattr(getattr(driver, "service", None), "process", None)
        if proc and proc.poll() is None:
            proc.kill()
    except Exception:
        pass
    return False
