"""Minimal state snapshot persistence for launcher restarts."""

from __future__ import annotations

import json
import os
import threading
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
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self._lock:
            with open(self.path, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)

    def handle_change(self, state: AppState, _change: AppStateChange) -> None:
        self.save(state)
