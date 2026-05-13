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
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

from app.security import KeyringTokenStore
from config.config_service import DEFAULT_PROFILE_NAME, load_config


DEDUP_SECONDS = 300
MAX_FIELD_CHARS = 120
MAX_MESSAGE_CHARS = 1200
MESSAGE_DIVIDER = "------------"

_DEDUP_CACHE: dict[str, float] = {}
_TELEGRAM_TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")
_MISSING_TRANSLATION_CACHE: set[str] = set()
_MISSING_TRANSLATION_LOG_PATH = os.path.join("logs", "missing_buyma_category_translations.jsonl")

BUYMA_CATEGORY_KR_MAP = {
    "メンズファッション": "남성패션",
    "レディースファッション": "여성패션",
    "トップス": "상의",
    "パンツ・ボトムス": "하의",
    "アウター・ジャケット": "아우터/재킷",
    "靴・ブーツ・サンダル": "신발/부츠/샌들",
    "バッグ・カバン": "가방",
    "アクセサリー": "액세서리",
    "腕時計": "시계",
    "財布・雑貨": "지갑/잡화",
    "アイウェア": "아이웨어",
    "帽子": "모자",
    "ファッション雑貨・小物": "패션잡화/소품",
    "スマホケース・テックアクセサリー": "폰케이스/테크액세서리",
    "インナー・ルームウェア": "이너/홈웨어",
    "水着・ビーチグッズ": "수영복/비치용품",
    "フィットネス": "피트니스",
    "スーツ": "수트",
    "セットアップ": "셋업",
    "ゴルフ": "골프",
    "その他ファッション": "기타패션",
    "サングラス": "선글라스",
    "ベルト": "벨트",
    "キャップ": "캡",
    "ハット": "햇",
    "ニットキャップ・ビーニー": "니트캡/비니",
    "マフラー・ストール": "머플러/스토ール",
    "ファッション雑貨・小物その他": "패션잡화/소품 기타",
    "Tシャツ・カットソー": "티셔츠/컷소우",
    "パーカー・フーディ": "후디/파카",
    "スウェット・トレーナー": "스웨트/트레이너",
    "シャツ": "셔츠",
    "ニット・セーター": "니트/스웨터",
    "ルームウェア・パジャマ": "룸웨어/파자마",
    "ブラジャー": "브라",
    "ショーツ": "팬티/쇼츠",
    "ブラジャー＆ショーツ": "브라&팬티 세트",
    "スリップ・インナー・キャミ": "슬립/이너/캐미",
    "スパッツ・レギンス": "스패츠/레깅스",
    "タイツ・ソックス": "타이즈/삭스",
    "インナー・ルームウェアその他": "이너/룸웨어 기타",
}
def _read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    default_data_dir = Path(local_app_data) / "auto_shop" if local_app_data else Path.home() / ".auto_shop"
    candidates = [
        Path.cwd() / ".env",
        default_data_dir / ".env",
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

    account_keys = [f"{_profile_name()}.bot_token"]
    fallback_key = f"{DEFAULT_PROFILE_NAME}.bot_token"
    if fallback_key not in account_keys:
        account_keys.append(fallback_key)
    account_keys.append("bot_token")
    for account_key in account_keys:
        token = KeyringTokenStore(service_name="auto_shop.telegram", account_key=account_key).load()
        if token:
            return token
    return ""


def _load_chat_id(config: dict[str, Any], env_file: dict[str, str]) -> str:
    return str(
        os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("AUTO_SHOP_TELEGRAM_CHAT_ID")
        or env_file.get("TELEGRAM_CHAT_ID")
        or env_file.get("AUTO_SHOP_TELEGRAM_CHAT_ID")
        or config.get("chat_id")
        or ""
    ).strip()


def _is_valid_telegram_token(token: str) -> bool:
    value = (token or "").strip()
    if not value:
        return False
    lowered = value.lower()
    if "setx " in lowered or "http_proxy" in lowered or "https_proxy" in lowered:
        return False
    return bool(_TELEGRAM_TOKEN_RE.fullmatch(value))


def _is_valid_chat_id(chat_id: str) -> bool:
    value = (chat_id or "").strip()
    if not value:
        return False
    if value.startswith("@"):
        return len(value) > 1 and " " not in value
    return bool(re.fullmatch(r"-?\d{3,}", value))


def _is_enabled(config: dict[str, Any]) -> bool:
    env_enabled = os.environ.get("TELEGRAM_ENABLED") or os.environ.get("AUTO_SHOP_TELEGRAM_ENABLED")
    if env_enabled is not None:
        return env_enabled.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(config.get("enabled", False))


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


def _truncate(value: Any, limit: int = MAX_FIELD_CHARS) -> str:
    text = _sanitize_text(" ".join(str(value or "").split()))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _truncate_message(value: Any, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = _sanitize_text(str(value or "").replace("\r\n", "\n").replace("\r", "\n"))
    lines = [" ".join(line.split()) for line in text.split("\n")]
    text = "\n".join(lines).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


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


def _telegram_post(token: str, method: str, data: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    if requests is None:
        return {}
    url = f"https://api.telegram.org/bot{token}/{method}"
    if hasattr(requests, "Session"):
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(url, data=data, timeout=timeout)
    else:  # useful for small test doubles
        response = requests.post(url, data=data, timeout=timeout)
    response.raise_for_status()
    try:
        return response.json()
    except Exception:
        return {}


def _telegram_get(token: str, method: str, params: dict[str, Any], timeout: int = 35) -> dict[str, Any]:
    if requests is None:
        return {}
    url = f"https://api.telegram.org/bot{token}/{method}"
    if hasattr(requests, "Session"):
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(url, params=params, timeout=timeout)
    else:
        response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    try:
        return response.json()
    except Exception:
        return {}


def _runtime_credentials() -> tuple[dict[str, Any], str, str]:
    config = _load_telegram_config()
    env_file = _read_env_file()
    token = _load_token(config, env_file)
    chat_id = _load_chat_id(config, env_file)
    return config, token, chat_id


def send_message(text: str, reply_markup: dict[str, Any] | None = None) -> bool:
    """Send a Telegram message if configured; never raise into main flow."""
    try:
        config, token, chat_id = _runtime_credentials()
        if not _is_enabled(config) or not token or not chat_id or requests is None:
            return False
        if not _is_valid_telegram_token(token) or not _is_valid_chat_id(chat_id):
            return False

        message = _truncate_message(text, MAX_MESSAGE_CHARS)
        if reply_markup is None and _deduped(message):
            return False

        data = {"chat_id": chat_id, "text": message}
        if reply_markup is not None:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        _telegram_post(token, "sendMessage", data, timeout=10)
        return True
    except Exception:
        return False


def send_control_panel() -> bool:
    """Send a Telegram remote-control panel with approved actions only."""
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "정찰", "callback_data": "auto_shop:run:scout"},
                {"text": "이미지", "callback_data": "auto_shop:run:image"},
            ],
            [
                {"text": "썸네일", "callback_data": "auto_shop:run:thumbnail"},
                {"text": "업로드", "callback_data": "auto_shop:run:upload"},
            ],
            [
                {"text": "상태", "callback_data": "auto_shop:status"},
                {"text": "중지", "callback_data": "auto_shop:stop"},
            ],
        ]
    }
    return send_message("Auto Shop 원격제어\n------------\n실행할 작업을 선택하세요.", reply_markup=keyboard)


def get_updates(offset: int = 0, timeout: int = 25) -> list[dict[str, Any]]:
    """Fetch Telegram updates for remote control; returns [] on any issue."""
    try:
        config, token, chat_id = _runtime_credentials()
        if not _is_enabled(config) or not token or not chat_id or requests is None:
            return []
        if not _is_valid_telegram_token(token) or not _is_valid_chat_id(chat_id):
            return []
        payload = _telegram_get(
            token,
            "getUpdates",
            {
                "offset": offset,
                "timeout": max(1, int(timeout)),
                "allowed_updates": json.dumps(["message", "callback_query"]),
            },
            timeout=max(5, int(timeout) + 5),
        )
        result = payload.get("result", [])
        return result if isinstance(result, list) else []
    except Exception:
        return []


def answer_callback_query(callback_query_id: str, text: str = "") -> bool:
    """Acknowledge an inline button click."""
    try:
        config, token, chat_id = _runtime_credentials()
        if not _is_enabled(config) or not token or not chat_id or requests is None:
            return False
        if not callback_query_id or not _is_valid_telegram_token(token):
            return False
        _telegram_post(token, "answerCallbackQuery", {"callback_query_id": callback_query_id, "text": _truncate(text, 180)}, timeout=10)
        return True
    except Exception:
        return False


def is_authorized_chat(chat_id: Any) -> bool:
    """Return whether a Telegram update came from the configured chat."""
    try:
        config, _token, configured_chat_id = _runtime_credentials()
        if not _is_enabled(config) or not configured_chat_id:
            return False
        return str(chat_id or "").strip() == str(configured_chat_id).strip()
    except Exception:
        return False


def get_notification_status() -> dict[str, bool | str]:
    """Return non-sensitive Telegram configuration status."""
    config = _load_telegram_config()
    env_file = _read_env_file()
    token = _load_token(config, env_file)
    chat_id = _load_chat_id(config, env_file)
    return {
        "profile": _profile_name(),
        "enabled": _is_enabled(config),
        "token_set": bool(token),
        "chat_id_set": bool(chat_id),
        "requests_available": requests is not None,
    }


def notify_job_started(job_name: str) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return send_message(
        "🚀 작업 시작\n"
        f"{MESSAGE_DIVIDER}\n"
        f"작업: {_truncate(job_name)}\n"
        f"시간: {now}"
    )


def notify_job_finished(job_name: str, success_count: int, fail_count: int, duration: str | float | int) -> bool:
    success = int(success_count or 0)
    fail = int(fail_count or 0)
    title = "✅ 작업 완료" if fail == 0 else "⚠️ 작업 완료(실패 포함)"
    return send_message(
        f"{title}\n"
        f"{MESSAGE_DIVIDER}\n"
        f"작업: {_truncate(job_name)}\n\n"
        f"성공: {success}\n"
        f"실패: {fail}\n"
        f"소요시간: {_format_duration(duration)}"
    )


def notify_upload_success(product: dict[str, Any]) -> bool:
    category_child = _extract_buyma_child_category(product.get("category"))
    category = _truncate(category_child)
    category_kr = _truncate(_translate_buyma_category_to_korean(category_child))
    category_text = category
    if category_kr:
        category_text = f"{category} ({category_kr})" if category else category_kr
    return send_message(
        "✅ BUYMA 업로드 성공\n"
        f"{MESSAGE_DIVIDER}\n"
        f"상품명: {_truncate(product.get('product_name') or product.get('product_name_kr'))}\n\n"
        f"브랜드: {_truncate(product.get('brand'))}\n"
        f"가격: {_truncate(product.get('price') or product.get('buyma_price'))}\n"
        f"카테고리: {category_text}"
    )


def notify_upload_failed(product: dict[str, Any], error: Any) -> bool:
    return send_message(
        "❌ BUYMA 업로드 실패\n"
        f"{MESSAGE_DIVIDER}\n"
        f"상품명: {_truncate(product.get('product_name') or product.get('product_name_kr'))}\n\n"
        f"사유: {_truncate(error, 220)}"
    )


def notify_critical_error(module_name: str, error: Any) -> bool:
    return send_message(
        "🔥 치명적 오류\n"
        f"{MESSAGE_DIVIDER}\n"
        f"위치: {_truncate(module_name)}\n\n"
        f"내용: {_truncate(error, 240)}"
    )


def notify_emergency_stop(reason: str) -> bool:
    return send_message(
        "🛑 긴급 중지\n"
        f"{MESSAGE_DIVIDER}\n"
        f"사유: {_truncate(reason, 240)}"
    )


def _format_duration(duration: str | float | int) -> str:
    if isinstance(duration, str):
        return _truncate(duration, 40)
    seconds = max(0, int(duration or 0))
    minutes, rem = divmod(seconds, 60)
    if minutes:
        return f"{minutes}분 {rem}초" if rem else f"{minutes}분"
    return f"{rem}초"


def _translate_buyma_category_to_korean(category_text: Any) -> str:
    raw = str(category_text or "").strip()
    if not raw:
        return ""
    # Handle common path separators used by logs/messages.
    parts = [part.strip() for part in re.split(r"\s*>\s*", raw) if part.strip()]
    if not parts:
        return ""
    translated = []
    for part in parts:
        mapped = BUYMA_CATEGORY_KR_MAP.get(part)
        if mapped is None:
            _log_missing_buyma_category_translation(part)
            translated.append(part)
        else:
            translated.append(mapped)
    return " > ".join(translated)


def _extract_buyma_child_category(category_text: Any) -> str:
    raw = str(category_text or "").strip()
    if not raw:
        return ""
    parts = [part.strip() for part in re.split(r"\s*>\s*", raw) if part.strip()]
    if parts:
        return parts[-1]
    return raw


def _log_missing_buyma_category_translation(category_part: str) -> None:
    key = (category_part or "").strip()
    if not key:
        return
    if key in _MISSING_TRANSLATION_CACHE:
        return
    _MISSING_TRANSLATION_CACHE.add(key)
    try:
        os.makedirs(os.path.dirname(_MISSING_TRANSLATION_LOG_PATH), exist_ok=True)
        payload = {
            "ts": datetime.now().isoformat(),
            "category_part": key,
            "event": "missing_buyma_translation",
        }
        with open(_MISSING_TRANSLATION_LOG_PATH, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return
