"""Minimal profile-based config loader for Phase 1 generalization."""

from __future__ import annotations

import json
import os
import threading
import time
from copy import deepcopy
from typing import Any

from config.app_config import DEFAULT_SHEET_NAME, DEFAULT_SPREADSHEET_ID


DEFAULT_PROFILE_NAME = "default"
CONFIG_FILENAME = "config.json"
_CONFIG_WRITE_LOCK = threading.Lock()


def _runtime_root_dir() -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return os.path.join(local_app_data, "auto_shop")
    return os.path.join(os.path.expanduser("~"), ".auto_shop")


def _sanitize_profile_name(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return DEFAULT_PROFILE_NAME
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value).strip("-._")
    return safe or DEFAULT_PROFILE_NAME


def get_profile_config_dir(profile_name: str) -> str:
    profile = _sanitize_profile_name(profile_name)
    return os.path.join(_runtime_root_dir(), "profiles", profile)


def get_profile_config_path(profile_name: str) -> str:
    return os.path.join(get_profile_config_dir(profile_name), CONFIG_FILENAME)


def default_config() -> dict[str, Any]:
    return {
        "spreadsheet": {
            "id": DEFAULT_SPREADSHEET_ID,
            "credentials_path": "",
            "tabs": {
                "product_input": DEFAULT_SHEET_NAME,
                "category": "카테고리",
                "candidate": "후보 상품",
                "scout_queue": "목록 페이지 url",
                "log": "log",
                "category_mapping_candidates": "category_mapping_candidates",
            },
        },
        "paths": {
            "images_dir": "",
            "log_dir": "",
        },
        "buyma": {
            "email": "",
        },
        "runtime": {
            "max_workers": 1,
            "retry_count": 3,
            "timeout_seconds": 120,
        },
        "crawling": {
            "base": {
                "max_pages": 5,
                "delay_seconds": 3,
                "retry_count": 3,
                "timeout": 30,
            },
            "targets": {
                "category_pages": True,
                "product_detail_pages": True,
                "brand_pages": False,
                "keyword_search": False,
                "keyword": "",
            },
            "filters": {
                "min_price": 0,
                "max_price": 10000000,
                "min_reviews": 0,
                "min_sales": 0,
            },
            "options": {
                "download_images": True,
                "generate_thumbnails": True,
                "save_html": False,
                "dedupe": True,
            },
        },
        "upload": {
            "base": {
                "batch_size": 1,
                "max_workers": 1,
                "retry_count": 3,
            },
            "category_mapping": {
                "source_category": "",
                "target_buyma_category": "",
            },
            "price": {
                "markup_percent": 0,
                "minimum_margin": 0,
                "rounding_rule": "100엔",
            },
            "options": {
                "validate_before_upload": True,
                "retry_failed": True,
                "save_logs": True,
                "auto_price": True,
            },
        },
        "notification": {
            "telegram": {
                "enabled": False,
                "chat_id": "",
            },
            "events": {
                "job_start": True,
                "job_complete": True,
                "job_error": True,
                "important_only": False,
            },
            "email": {
                "enabled": False,
                "address": "",
                "password": "",
            },
            "schedule": {
                "start_time": "09:00",
                "end_time": "22:00",
                "timezone": "Asia/Seoul",
            },
        },
        "advanced": {
            "system_paths": {
                "python_path": "",
                "chrome_path": "",
            },
            "execution": {
                "max_workers": 1,
                "cpu_limit": 80,
                "memory_limit": 2048,
            },
            "feature_flags": {
                "async_mode": False,
                "smart_retry": True,
                "ai_category": False,
            },
        },
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _legacy_config_path() -> str:
    env_data_dir = os.environ.get("AUTO_SHOP_DATA_DIR", "").strip()
    if env_data_dir:
        return os.path.join(os.path.abspath(os.path.expanduser(env_data_dir)), "sheets_config.json")
    return os.path.join(_runtime_root_dir(), "sheets_config.json")


def _load_legacy_sheet_config() -> dict[str, Any]:
    path = _legacy_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _legacy_to_config(legacy: dict[str, Any]) -> dict[str, Any]:
    if not legacy:
        return {}
    tabs = {
        "product_input": str(legacy.get("sheet_name") or "").strip(),
        "category": str(legacy.get("category_sheet_name") or "").strip(),
        "candidate": str(legacy.get("candidate_sheet_name") or "").strip(),
        "scout_queue": str(legacy.get("queue_sheet_name") or "").strip(),
        "log": str(legacy.get("log_sheet_name") or "").strip(),
        "category_mapping_candidates": str(legacy.get("category_mapping_candidates_sheet_name") or "").strip(),
    }
    return {
        "spreadsheet": {
            "id": str(legacy.get("spreadsheet_id") or "").strip(),
            "credentials_path": str(legacy.get("credentials_path") or "").strip(),
            "tabs": {key: value for key, value in tabs.items() if value},
        },
        "paths": {
            "images_dir": str(legacy.get("images_dir") or "").strip(),
            "log_dir": str(legacy.get("log_dir") or "").strip(),
        },
    }


def load_config(profile_name: str = DEFAULT_PROFILE_NAME, *, create_if_missing: bool = False) -> dict[str, Any]:
    profile = _sanitize_profile_name(profile_name)
    config = default_config()
    config = _deep_merge(config, _legacy_to_config(_load_legacy_sheet_config()))

    config_path = get_profile_config_path(profile)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, dict):
                config = _deep_merge(config, loaded)
        except Exception:
            pass
    elif create_if_missing:
        try:
            os.makedirs(get_profile_config_dir(profile), exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(config, file, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return config


def save_config(profile_name: str, config: dict[str, Any]) -> str:
    profile = _sanitize_profile_name(profile_name)
    config_path = get_profile_config_path(profile)
    config_dir = get_profile_config_dir(profile)
    os.makedirs(config_dir, exist_ok=True)
    new_content = json.dumps(config, ensure_ascii=False, indent=2)

    with _CONFIG_WRITE_LOCK:
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as existing_file:
                    if existing_file.read() == new_content:
                        return config_path
            except Exception:
                pass

        tmp_path = os.path.join(config_dir, f".{CONFIG_FILENAME}.tmp.{os.getpid()}.{int(time.time()*1000)}")
        with open(tmp_path, "w", encoding="utf-8") as file:
            file.write(new_content)
            file.flush()
            os.fsync(file.fileno())

        last_error: Exception | None = None
        for _ in range(30):
            try:
                os.replace(tmp_path, config_path)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.2)
        if last_error is not None:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise last_error

    return config_path
