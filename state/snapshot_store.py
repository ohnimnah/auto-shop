"""Minimal state snapshot persistence for launcher restarts."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from typing import Any

from state.app_state import AppState, AppStateChange


class StateSnapshotStore:
    """Save and restore the small state subset useful across app restarts."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()

    def load_into(self, state: AppState) -> bool:
        data = self.load()
        if not data:
            return False
        state.apply_snapshot(data)
        return True

    def load(self) -> dict[str, Any]:
        try:
            if not os.path.exists(self.path):
                return {}
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save(self, state: AppState) -> None:
        payload = state.to_snapshot()
        payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
        parent = os.path.dirname(self.path)
        os.makedirs(parent, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp_path = os.path.join(parent, f".launcher_state_snapshot.tmp.{os.getpid()}.{int(time.time()*1000)}")
        with self._lock:
            with open(tmp_path, "w", encoding="utf-8") as file:
                file.write(serialized)
                file.flush()
                os.fsync(file.fileno())
            try:
                os.replace(tmp_path, self.path)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

    def handle_change(self, state: AppState, _change: AppStateChange) -> None:
        try:
            self.save(state)
        except Exception:
            # Snapshot persistence should never crash the launcher.
            return
