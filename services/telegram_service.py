"""Telegram notification helpers for operational events."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover - notification must never block app startup.
    requests = None  # type: ignore[assignment]

from app.security import KeyringTokenStore
from config.config_service import DEFAULT_PROFILE_NAME, load_config


DEDUP_SECONDS = 300
MAX_FIELD_CHARS = 120
MAX_MESSAGE_CHARS = 1200

_DEDUP_CACHE: dict[str, float] = {}


def _read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    candidates = [
        Path.cwd() / ".env",
        Path(os.environ.get("AUTO_SHOP_DATA_DIR", "")).expanduser() / ".env"
        if os.environ.get("AUTO_SHOP_DATA_DIR")
        else None,
    ]
    for path in candidates:
        if not path or not path.exists():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            continue
    return values


def _profile_name() -> str:
    return (os.environ.get("AUTO_SHOP_PROFILE") or DEFAULT_PROFILE_NAME).strip() or DEFAULT_PROFILE_NAME


def _load_telegram_config() -> dict[str, Any]:
    try:
        return ((load_config(_profile_name(), create_if_missing=False).get("notification") or {}).get("telegram") or {})
    except Exception:
        return {}


def _load_token(config: dict[str, Any], env_file: dict[str, str]) -> str:
    env_token = (
        os.environ.get("TELEGRAM_BOT_TOKEN")
        or os.environ.get("AUTO_SHOP_TELEGRAM_BOT_TOKEN")
        or env_file.get("TELEGRAM_BOT_TOKEN")
        or env_file.get("AUTO_SHOP_TELEGRAM_BOT_TOKEN")
    )
    if env_token:
        return str(env_token).strip()

    legacy_config_token = str(config.get("bot_token") or "").strip()
    if legacy_config_token:
        return legacy_config_token

    return KeyringTokenStore(
        service_name="auto_shop.telegram",
        account_key=f"{_profile_name()}.bot_token",
    ).load()


def _load_chat_id(config: dict[str, Any], env_file: dict[str, str]) -> str:
    return str(
        os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("AUTO_SHOP_TELEGRAM_CHAT_ID")
        or env_file.get("TELEGRAM_CHAT_ID")
        or env_file.get("AUTO_SHOP_TELEGRAM_CHAT_ID")
        or config.get("chat_id")
        or ""
    ).strip()


def _is_enabled(config: dict[str, Any]) -> bool:
    env_enabled = os.environ.get("TELEGRAM_ENABLED") or os.environ.get("AUTO_SHOP_TELEGRAM_ENABLED")
    if env_enabled is not None:
        return env_enabled.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(config.get("enabled", False))


def _truncate(value: Any, limit: int = MAX_FIELD_CHARS) -> str:
    text = _sanitize_text(" ".join(str(value or "").split()))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _sanitize_text(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[masked-email]", value)
    value = re.sub(
        r"(?i)(/[^ ]*)?(credentials|buyma_credentials|token|cookie|chrome_profile)[^ \n]*",
        "[masked-sensitive-path]",
        value,
    )
    value = re.sub(
        r"(?i)[A-Z]:\\[^ \n]*(credentials|buyma_credentials|token|cookie|chrome_profile)[^ \n]*",
        "[masked-sensitive-path]",
        value,
    )
    value = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", "[masked-telegram-token]", value)
    return value


def _message_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _deduped(text: str) -> bool:
    now = time.time()
    key = _message_key(text)
    last_sent = _DEDUP_CACHE.get(key, 0)
    if now - last_sent < DEDUP_SECONDS:
        return True
    _DEDUP_CACHE[key] = now
    for cache_key, timestamp in list(_DEDUP_CACHE.items()):
        if now - timestamp > DEDUP_SECONDS:
            _DEDUP_CACHE.pop(cache_key, None)
    return False


def send_message(text: str) -> bool:
    """Send a Telegram message if configured; never raise into main work."""
    try:
        config = _load_telegram_config()
        env_file = _read_env_file()
        token = _load_token(config, env_file)
        chat_id = _load_chat_id(config, env_file)
        if not _is_enabled(config) or not token or not chat_id or requests is None:
            return False

        message = _truncate(text, MAX_MESSAGE_CHARS)
        if _deduped(message):
            return False

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": message},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception:
        return False


def notify_job_started(job_name: str) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return send_message(f"🚀 Auto Shop 작업 시작\n작업: {_truncate(job_name)}\n시간: {now}")


def notify_job_finished(job_name: str, success_count: int, fail_count: int, duration: str | float | int) -> bool:
    return send_message(
        "✅ 작업 완료\n"
        f"작업: {_truncate(job_name)}\n"
        f"성공: {int(success_count or 0)}\n"
        f"실패: {int(fail_count or 0)}\n"
        f"소요시간: {_format_duration(duration)}"
    )


def notify_upload_success(product: dict[str, Any]) -> bool:
    return send_message(
        "✅ BUYMA 업로드 성공\n"
        f"상품명: {_truncate(product.get('product_name') or product.get('product_name_kr'))}\n"
        f"브랜드: {_truncate(product.get('brand'))}\n"
        f"가격: {_truncate(product.get('price') or product.get('buyma_price'))}\n"
        f"카테고리: {_truncate(product.get('category'))}"
    )


def notify_upload_failed(product: dict[str, Any], error: Any) -> bool:
    return send_message(
        "❌ BUYMA 업로드 실패\n"
        f"상품명: {_truncate(product.get('product_name') or product.get('product_name_kr'))}\n"
        f"사유: {_truncate(error, 220)}"
    )


def notify_critical_error(module_name: str, error: Any) -> bool:
    return send_message(
        "🚨 치명적 에러 발생\n"
        f"위치: {_truncate(module_name)}\n"
        f"내용: {_truncate(error, 240)}"
    )


def notify_emergency_stop(reason: str) -> bool:
    return send_message(f"🛑 긴급 중지\n사유: {_truncate(reason, 240)}")


def _format_duration(duration: str | float | int) -> str:
    if isinstance(duration, str):
        return _truncate(duration, 40)
    seconds = max(0, int(duration or 0))
    minutes, rem = divmod(seconds, 60)
    if minutes:
        return f"{minutes}분 {rem}초" if rem else f"{minutes}분"
    return f"{rem}초"


"""
사용 예시:

notify_job_started("BUYMA 업로드")
notify_job_finished("이미지/썸네일 처리", success_count=38, fail_count=2, duration="12분")
notify_upload_success({"product_name": "상품명", "brand": "BRAND", "buyma_price": "12000", "category": "トップス"})
notify_upload_failed({"product_name": "상품명"}, "가격 입력 필드를 찾을 수 없습니다")
notify_critical_error("buyma_upload", "ChromeDriver start failed")
notify_emergency_stop("사용자가 전체 중지를 눌렀습니다")
"""
