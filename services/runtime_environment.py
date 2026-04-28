from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass
class RuntimeCheckResult:
    selenium_available: bool
    keyring_available: bool
    credentials_exists: bool
    screenshot_dir_writable: bool
    chrome_accessible: bool
    chromedriver_accessible: bool

    @property
    def ok(self) -> bool:
        return all(
            [
                self.selenium_available,
                self.keyring_available,
                self.credentials_exists,
                self.screenshot_dir_writable,
                self.chrome_accessible,
            ]
        )


def check_runtime_environment(credentials_path: str, logs_root: str = "logs") -> RuntimeCheckResult:
    selenium_available = False
    try:
        import selenium  # noqa: F401

        selenium_available = True
    except Exception:
        selenium_available = False

    keyring_available = False
    try:
        import keyring  # noqa: F401

        keyring_available = True
    except Exception:
        keyring_available = False

    credentials_exists = bool(credentials_path and os.path.exists(credentials_path))

    screenshot_dir = os.path.join(logs_root, "screenshots")
    screenshot_dir_writable = False
    try:
        os.makedirs(screenshot_dir, exist_ok=True)
        probe = os.path.join(screenshot_dir, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        screenshot_dir_writable = True
    except Exception:
        screenshot_dir_writable = False

    chrome_accessible = _is_chrome_accessible()
    chromedriver_accessible = _is_chromedriver_accessible()

    return RuntimeCheckResult(
        selenium_available=selenium_available,
        keyring_available=keyring_available,
        credentials_exists=credentials_exists,
        screenshot_dir_writable=screenshot_dir_writable,
        chrome_accessible=chrome_accessible,
        chromedriver_accessible=chromedriver_accessible,
    )


def _is_chrome_accessible() -> bool:
    # PATH candidates first (cross-platform).
    if shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("msedge"):
        return True

    # Windows known install paths.
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates = [
            os.path.join(local_app_data, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(program_files, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(program_files_x86, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(program_files, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(program_files_x86, r"Microsoft\Edge\Application\msedge.exe"),
        ]
        return any(os.path.exists(path) for path in candidates)
    return False


def _is_chromedriver_accessible() -> bool:
    if shutil.which("chromedriver"):
        return True
    if os.name == "nt":
        user_home = os.path.expanduser("~")
        wdm_root = os.path.join(user_home, ".wdm", "drivers", "chromedriver")
        if not os.path.isdir(wdm_root):
            return False
        for root, _dirs, files in os.walk(wdm_root):
            if "chromedriver.exe" in files:
                return True
    return False
