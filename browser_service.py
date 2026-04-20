"""Browser/WebDriver setup helpers."""

import glob
import os
import tempfile

from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def _create_profile_dir(prefix: str) -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    candidates = []
    if local_app_data:
        candidates.append(os.path.join(local_app_data, "auto_shop", "chrome_profiles"))
    candidates.append(os.path.join(os.path.expanduser("~"), ".auto_shop", "chrome_profiles"))
    candidates.append(os.path.join(os.getcwd(), ".runtime", "chrome_profiles"))

    last_error = None
    for root in candidates:
        try:
            os.makedirs(root, exist_ok=True)
            return tempfile.mkdtemp(prefix=prefix, dir=root)
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("Chrome profile directory 생성 실패")


def setup_chrome_driver(headless: bool = False):
    """Create configured Chrome WebDriver."""
    def _build_options(profile_dir: str | None) -> ChromeOptions:
        chrome_options = ChromeOptions()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--remote-debugging-port=0")
        chrome_options.add_argument("--window-size=1920,1080")
        if profile_dir:
            chrome_options.add_argument(f"--user-data-dir={profile_dir}")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return chrome_options

    profile_dir = _create_profile_dir("autoshop_chrome_")
    chrome_options = _build_options(profile_dir)
    # Prefer cached chromedriver first to avoid webdriver_manager chmod permission errors
    cached_candidates = sorted(
        glob.glob(
            os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver", "**", "chromedriver.exe"),
            recursive=True,
        )
    )
    driver_path = cached_candidates[-1] if cached_candidates else None

    try:
        service = Service(driver_path or ChromeDriverManager().install())
    except PermissionError:
        if not driver_path:
            raise
        service = Service(driver_path)

    try:
        return webdriver.Chrome(service=service, options=chrome_options)
    except SessionNotCreatedException as exc:
        err_text = str(exc)
        if "DevToolsActivePort" not in err_text and "cannot create default profile directory" not in err_text:
            raise
        # Retry 1: fresh profile dir
        try:
            fallback_profile_dir = _create_profile_dir("autoshop_chrome_fallback_")
            return webdriver.Chrome(service=service, options=_build_options(fallback_profile_dir))
        except SessionNotCreatedException as retry_exc:
            retry_text = str(retry_exc)
            if "cannot create default profile directory" not in retry_text:
                raise
            # Retry 2: launch without custom user-data-dir
            return webdriver.Chrome(service=service, options=_build_options(None))
