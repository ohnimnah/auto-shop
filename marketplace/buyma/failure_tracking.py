from __future__ import annotations

import json
import os
from datetime import datetime


def _runtime_logs_dir() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = os.path.join(root, "logs")
    os.makedirs(path, exist_ok=True)
    return path


def capture_failure_artifacts(driver, row: int, step: str, error: str, retry_count: int = 0) -> None:
    logs_dir = _runtime_logs_dir()
    shots_dir = os.path.join(logs_dir, "screenshots")
    os.makedirs(shots_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    screenshot_path = os.path.join(shots_dir, f"{ts}_row{row}_{step}.png")
    try:
        driver.save_screenshot(screenshot_path)
    except Exception:
        screenshot_path = ""

    payload = {
        "timestamp": ts,
        "row": row,
        "step": step,
        "error": error,
        "retry_count": retry_count,
        "screenshot": screenshot_path,
    }
    failure_log = os.path.join(logs_dir, "upload_failures.jsonl")
    with open(failure_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

