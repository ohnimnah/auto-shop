"""Minimal profile-based config loader for Phase 1 generalization."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

from config.app_config import DEFAULT_SHEET_NAME, DEFAULT_SPREADSHEET_ID


DEFAULT_PROFILE_NAME = "default"
CONFIG_FILENAME = "config.json"


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
            "tabs": {
                "product_input": DEFAULT_SHEET_NAME,
                "category": "카테고리",
                "candidate": "후보 상품",
                "scout_queue": "목록 페이지 url",
                "log": "log",
            },
        }
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
    }
    return {
        "spreadsheet": {
            "id": str(legacy.get("spreadsheet_id") or "").strip(),
            "tabs": {key: value for key, value in tabs.items() if value},
        }
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
