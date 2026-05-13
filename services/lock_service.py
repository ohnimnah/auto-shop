"""Account-scoped upload lock helpers."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


LOCK_TIMEOUT_MINUTES = 30
LOCK_TYPE_BUYMA_UPLOAD = "buyma_upload"
LOCK_RECHECK_DELAY_SECONDS = 1.0


def get_upload_lock_dir() -> Path:
    configured = (os.environ.get("AUTO_SHOP_LOCK_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser()

    data_dir = (os.environ.get("AUTO_SHOP_DATA_DIR") or "").strip()
    if data_dir:
        return Path(data_dir).expanduser() / "locks"

    local_app_data = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        return Path(local_app_data).expanduser() / "auto_shop" / "locks"
    return Path.home() / ".auto_shop" / "locks"


def normalize_upload_account_id(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return "buyma_unknown"
    digest = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:12]
    label = raw.split("@", 1)[0] if "@" in raw else raw
    label = re.sub(r"[^a-z0-9._-]+", "_", label).strip("._-")
    label = label[:24] or "account"
    return f"buyma_{label}_{digest}"


def build_upload_account_id(email: str) -> str:
    return normalize_upload_account_id(email)


def get_pc_name() -> str:
    return (
        os.environ.get("COMPUTERNAME")
        or os.environ.get("HOSTNAME")
        or socket.gethostname()
        or "unknown"
    ).strip() or "unknown"


def _safe_lock_name(account_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", (account_id or "").strip()).strip("._-")
    return safe or "buyma_unknown"


def _lock_path(account_id: str, lock_dir: Path | None = None) -> Path:
    root = lock_dir or get_upload_lock_dir()
    return root / f"upload_{_safe_lock_name(account_id)}.lock"


def _now() -> datetime:
    return datetime.now()


def _parse_started_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _is_stale(info: dict[str, Any], *, now: datetime | None = None, timeout_minutes: int = LOCK_TIMEOUT_MINUTES) -> bool:
    started_at = _parse_started_at(info.get("started_at"))
    if started_at is None:
        return True
    return (now or _now()) - started_at >= timedelta(minutes=timeout_minutes)


def get_upload_lock_info(account_id: str, *, lock_dir: Path | None = None) -> dict[str, Any] | None:
    path = _lock_path(account_id, lock_dir)
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def is_upload_locked(account_id: str, *, lock_dir: Path | None = None) -> bool:
    info = get_upload_lock_info(account_id, lock_dir=lock_dir)
    if not info:
        return False
    if _is_stale(info):
        release_upload_lock(account_id, lock_dir=lock_dir)
        return False
    return True


def acquire_upload_lock(
    account_id: str,
    owner: str,
    *,
    lock_dir: Path | None = None,
) -> tuple[bool, dict[str, Any]]:
    root = lock_dir or get_upload_lock_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = _lock_path(account_id, root)

    info = get_upload_lock_info(account_id, lock_dir=root)
    if info and _is_stale(info):
        release_upload_lock(account_id, lock_dir=root)
        info = None
    if info:
        return False, info

    payload = {
        "account_id": account_id,
        "owner": (owner or "").strip() or "unknown",
        "pc_name": get_pc_name(),
        "started_at": _now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": LOCK_TYPE_BUYMA_UPLOAD,
    }
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        time.sleep(LOCK_RECHECK_DELAY_SECONDS)
        current = get_upload_lock_info(account_id, lock_dir=root)
        if current and current.get("owner") != payload["owner"]:
            return False, current
        return True, payload
    except FileExistsError:
        info = get_upload_lock_info(account_id, lock_dir=root)
        if info and _is_stale(info):
            release_upload_lock(account_id, lock_dir=root)
            return acquire_upload_lock(account_id, owner, lock_dir=root)
        return False, info or payload


def release_upload_lock(account_id: str, *, lock_dir: Path | None = None) -> None:
    path = _lock_path(account_id, lock_dir)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        return
