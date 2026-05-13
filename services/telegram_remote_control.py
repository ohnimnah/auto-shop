"""Telegram long-polling remote control for the launcher."""

from __future__ import annotations

import threading
import time
from typing import Callable

from services.telegram_service import (
    answer_callback_query,
    get_updates,
    is_authorized_chat,
    send_control_panel,
    send_message,
)


REMOTE_ACTIONS = {
    "auto_shop:run:scout": ("run", "정찰"),
    "auto_shop:run:image": ("save-images", "이미지 저장"),
    "auto_shop:run:thumbnail": ("thumbnail-create", "썸네일 생성"),
    "auto_shop:run:upload": ("upload-auto", "BUYMA 업로드"),
    "auto_shop:stop": ("stop", "현재 작업 중지"),
    "auto_shop:status": ("status", "상태 확인"),
}


class TelegramRemoteController:
    """Poll Telegram button callbacks and forward safe commands to the UI."""

    def __init__(
        self,
        *,
        command_callback: Callable[[str], str],
        log_callback: Callable[[str], None] | None = None,
        poll_timeout: int = 20,
    ) -> None:
        self.command_callback = command_callback
        self.log_callback = log_callback
        self.poll_timeout = max(5, int(poll_timeout))
        self._offset = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, *, send_panel: bool = False) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(send_panel,),
            name="telegram-remote-control",
            daemon=True,
        )
        self._thread.start()
        self._log("Telegram 원격제어 감시 시작")

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        self._log("Telegram 원격제어 감시 중지")

    def _prime_offset(self) -> None:
        """Skip callbacks that arrived before this launcher session started."""
        updates = get_updates(offset=0, timeout=1)
        for update in updates:
            try:
                update_id = int(update.get("update_id", 0))
            except Exception:
                continue
            if update_id >= self._offset:
                self._offset = update_id + 1

    def _run(self, send_panel: bool) -> None:
        self._prime_offset()
        if send_panel:
            send_control_panel()
        while not self._stop_event.is_set():
            updates = get_updates(offset=self._offset, timeout=self.poll_timeout)
            if not updates:
                continue
            for update in updates:
                try:
                    update_id = int(update.get("update_id", 0))
                    if update_id >= self._offset:
                        self._offset = update_id + 1
                    self._handle_update(update)
                except Exception as exc:
                    self._log(f"Telegram 원격제어 처리 오류: {exc}")
            time.sleep(0.1)

    def _handle_update(self, update: dict) -> None:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            self._handle_callback(callback)
            return

        message = update.get("message")
        if isinstance(message, dict):
            self._handle_message(message)

    def _handle_message(self, message: dict) -> None:
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not is_authorized_chat(chat_id):
            return
        text = str(message.get("text") or "").strip().lower()
        if text in {"/panel", "/start", "panel", "원격", "원격제어"}:
            send_control_panel()

    def _handle_callback(self, callback: dict) -> None:
        query_id = str(callback.get("id") or "")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not is_authorized_chat(chat_id):
            answer_callback_query(query_id, "허용되지 않은 채팅입니다.")
            return

        data = str(callback.get("data") or "")
        action_pair = REMOTE_ACTIONS.get(data)
        if not action_pair:
            answer_callback_query(query_id, "알 수 없는 명령입니다.")
            return

        action, label = action_pair
        result = self.command_callback(action)
        answer_callback_query(query_id, result or f"{label} 요청 완료")
        if action == "status":
            send_message(result)
        else:
            send_message(f"📲 원격 명령 접수\n------------\n작업: {label}\n결과: {result}")

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)
