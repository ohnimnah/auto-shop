"""Persistent launcher log storage."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime

from state.app_state import LogEvent


class FileLogWriter:
    """Append structured launcher logs as JSON lines."""

    def __init__(self, log_dir: str) -> None:
        self.log_dir = log_dir
        self._lock = threading.RLock()

    def handle(self, event: LogEvent) -> None:
        os.makedirs(self.log_dir, exist_ok=True)
        path = self._path_for(event.timestamp)
        payload = {
            "timestamp": event.timestamp.isoformat(timespec="seconds"),
            "level": event.level,
            "category": event.category,
            "message": event.message.rstrip("\n"),
        }
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with open(path, "a", encoding="utf-8") as file:
                file.write(line + "\n")

    def _path_for(self, timestamp: datetime) -> str:
        return os.path.join(self.log_dir, f"launcher-{timestamp:%Y-%m-%d}.log")
