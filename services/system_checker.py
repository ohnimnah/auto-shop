"""Runtime and configuration checks used by the dashboard."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime

from app.security.credential_store import KeyringCredentialStore


class SystemChecker:
    def __init__(
        self,
        *,
        script_dir: str,
        data_dir: str,
        sheet_config_path: str,
        resolve_python_executable,
        get_images_dir,
    ) -> None:
        self.script_dir = script_dir
        self.data_dir = data_dir
        self.sheet_config_path = sheet_config_path
        self.resolve_python_executable = resolve_python_executable
        self.get_images_dir = get_images_dir

    def get_credentials_target_path(self) -> str:
        return os.path.join(self.data_dir, "credentials.json")

    def get_buyma_credentials_target_path(self) -> str:
        return os.path.join(self.data_dir, "buyma_credentials.json")

    def get_available_credentials_path(self) -> str:
        target = self.get_credentials_target_path()
        if os.path.exists(target):
            return target
        legacy = os.path.join(self.script_dir, "credentials.json")
        if os.path.exists(legacy):
            return legacy
        return ""

    def load_sheet_config(self) -> dict:
        try:
            if not os.path.exists(self.sheet_config_path):
                return {}
            with open(self.sheet_config_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_sheet_config(self, config: dict) -> bool:
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.sheet_config_path, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
        return True

    def normalize_spreadsheet_id(self, raw_value: str) -> str:
        value = (raw_value or "").strip()
        if not value:
            return ""
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
        if match:
            return match.group(1)
        match = re.search(r"(?:^|/)d/([a-zA-Z0-9-_]+)", value)
        if match:
            return match.group(1)
        return value

    def is_valid_spreadsheet_id(self, spreadsheet_id: str) -> bool:
        sid = (spreadsheet_id or "").strip()
        if not sid or "@" in sid:
            return False
        return bool(re.fullmatch(r"[a-zA-Z0-9-_]{20,}", sid))

    def has_valid_sheet_config(self) -> bool:
        config = self.load_sheet_config()
        sid = self.normalize_spreadsheet_id(config.get("spreadsheet_id", ""))
        return self.is_valid_spreadsheet_id(sid) and bool((config.get("sheet_name") or "").strip())

    def has_buyma_credentials(self) -> bool:
        path = self.get_buyma_credentials_target_path()
        return KeyringCredentialStore(path).exists()

    def load_buyma_email(self) -> str:
        path = self.get_buyma_credentials_target_path()
        return KeyringCredentialStore(path).load_email()

    def has_ready_runtime(self) -> bool:
        python_cmd = self.resolve_python_executable()
        if not python_cmd:
            return False
        if os.path.isfile(python_cmd) or shutil.which(python_cmd):
            try:
                result = subprocess.run(
                    [
                        python_cmd,
                        "-c",
                        "import selenium, PIL, bs4, googleapiclient, google.oauth2, webdriver_manager, numpy, cv2",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=20,
                    check=False,
                )
                return result.returncode == 0
            except Exception:
                return False
        return False

    def get_mosaic_runtime_state(self) -> str:
        python_cmd = self.resolve_python_executable()
        if not python_cmd or not (os.path.isfile(python_cmd) or shutil.which(python_cmd)):
            return "missing"
        try:
            result = subprocess.run(
                [
                    python_cmd,
                    "-c",
                    (
                        "import os; "
                        "import cv2; "
                        "p=cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'; "
                        "c=cv2.CascadeClassifier(p); "
                        "state='ready' if os.path.exists(p) and not c.empty() else 'installed'; "
                        "print(state)"
                    ),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=20,
                check=False,
            )
            if result.returncode != 0:
                return "missing"
            state = (result.stdout or "").strip().lower()
            return state if state in {"ready", "installed"} else "missing"
        except Exception:
            return "missing"

    def collect_status(self) -> dict[str, str]:
        images_dir = self.get_images_dir()
        return {
            "credentials": "정상" if self.get_available_credentials_path() else "필요",
            "sheet": "정상" if self.has_valid_sheet_config() else "필요",
            "buyma": "정상" if self.has_buyma_credentials() else "선택",
            "images": "정상" if os.path.isdir(images_dir) else "필요",
            "runtime": "정상" if self.has_ready_runtime() else "필요",
            "last_check": datetime.now().strftime("%H:%M:%S"),
        }

