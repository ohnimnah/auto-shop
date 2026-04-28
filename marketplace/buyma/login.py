"""BUYMA login/session helpers extracted from the legacy uploader."""

import glob
import json
import os
import platform
import re
import tempfile
import time
from urllib.parse import urlparse
from typing import Callable, Optional, Tuple

from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from marketplace.common.runtime import get_runtime_data_dir
from marketplace.buyma.selectors import (
    BUYMA_LOGIN_URL,
    BUYMA_LOGOUT_URL,
    BUYMA_SELL_URL,
    LOGIN_EMAIL_SELECTOR,
    LOGIN_PASSWORD_SELECTOR,
    LOGIN_SUBMIT_SELECTOR,
)

BUYMA_CRED_PATH = os.path.join(get_runtime_data_dir(), "buyma_credentials.json")
CHROME_PROFILE_DIR = os.path.join(get_runtime_data_dir(), "chrome_profile")
CHROMEDRIVER_LOG_PATH = os.path.join(get_runtime_data_dir(), "chromedriver_buyma.log")


def _sleep(seconds: float, wait_scale: float = 0.6) -> None:
    time.sleep(max(0.0, seconds * wait_scale))


def _is_buyma_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host.endswith("buyma.com")


def _is_buyma_login_url(url: str) -> bool:
    return _is_buyma_url(url) and "/login" in (url or "")


def _ensure_buyma_page(driver, target_url: str, *, wait_scale: float = 0.6, retries: int = 3) -> str:
    last_url = ""
    for attempt in range(1, retries + 1):
        try:
            driver.get(target_url)
            _sleep(2, wait_scale)
            last_url = driver.current_url
            print(f"BUYMA navigate ({attempt}/{retries}): {last_url}")
            if _is_buyma_url(last_url):
                return last_url
        except Exception as exc:
            print(f"BUYMA navigate retry needed: {exc}")
    return last_url


def save_buyma_credentials(email: str, password: str) -> None:
    os.makedirs(os.path.dirname(BUYMA_CRED_PATH), exist_ok=True)
    import base64

    payload = {
        "email": base64.b64encode(email.encode()).decode(),
        "password": base64.b64encode(password.encode()).decode(),
    }
    with open(BUYMA_CRED_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file)
    print("  BUYMA credentials saved.")


def load_buyma_credentials() -> Tuple[Optional[str], Optional[str]]:
    if not os.path.exists(BUYMA_CRED_PATH):
        return None, None
    try:
        import base64

        with open(BUYMA_CRED_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        email = base64.b64decode(data["email"]).decode()
        password = base64.b64decode(data["password"]).decode()
        return email, password
    except Exception:
        return None, None


def prompt_buyma_credentials() -> Tuple[str, str]:
    print("\nEnter BUYMA login credentials (first time only):")
    email = input("  Email: ").strip()
    password = input("  Password: ").strip()
    if email and password:
        save_buyma_credentials(email, password)
    return email, password


def _make_profile_dir() -> str:
    profile_dir = CHROME_PROFILE_DIR
    try:
        os.makedirs(profile_dir, exist_ok=True)
        return profile_dir
    except PermissionError:
        fallback_dir = os.path.join(tempfile.gettempdir(), "auto_shop", "chrome_profile")
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir


def _make_temporary_profile_dir(base_profile_dir: str) -> str:
    try:
        return tempfile.mkdtemp(prefix="buyma_profile_", dir=os.path.dirname(base_profile_dir))
    except Exception:
        return tempfile.mkdtemp(prefix="buyma_profile_")


def _parse_version_parts(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+(?:\.\d+){1,3})", text or "")
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def _find_cached_chromedrivers() -> list[str]:
    candidates = [
        path
        for path in glob.glob(
            os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver", "**", "chromedriver*"),
            recursive=True,
        )
        if os.path.isfile(path) and os.access(path, os.X_OK)
    ]
    return sorted(candidates, key=_parse_version_parts, reverse=True)


def _build_chrome_options(user_data_dir: str) -> ChromeOptions:
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--remote-debugging-port=0")
    chrome_options.add_argument("--window-size=1400,900")
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    if platform.system() == "Darwin":
        chrome_options.add_argument("--disable-features=DialMediaRouteProvider")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    return chrome_options


def _build_chrome_service(driver_path: Optional[str]) -> Service:
    os.makedirs(os.path.dirname(CHROMEDRIVER_LOG_PATH), exist_ok=True)
    executable_path = driver_path or ChromeDriverManager().install()
    return Service(executable_path, log_output=CHROMEDRIVER_LOG_PATH)


def setup_visible_chrome_driver():
    profile_dir = _make_profile_dir()
    chrome_options = _build_chrome_options(profile_dir)
    cached_driver_paths = _find_cached_chromedrivers()
    driver_candidates: list[Optional[str]] = cached_driver_paths[:] or [None]
    last_error: Exception | None = None
    driver = None

    for attempt_index, driver_path in enumerate(driver_candidates, start=1):
        driver_label = driver_path or "webdriver-manager"
        try:
            service = _build_chrome_service(driver_path)
        except PermissionError:
            if not driver_path:
                raise
            service = _build_chrome_service(driver_path)

        try:
            print(f"Starting ChromeDriver ({attempt_index}/{len(driver_candidates)}): {driver_label}")
            driver = webdriver.Chrome(service=service, options=chrome_options)
            break
        except SessionNotCreatedException as exc:
            last_error = exc
            fallback_profile = _make_temporary_profile_dir(profile_dir)
            print(f"Chrome session creation failed. Retrying with temporary profile: {fallback_profile}")
            print(f"ChromeDriver log: {CHROMEDRIVER_LOG_PATH}")
            try:
                service.stop()
            except Exception:
                pass
            retry_service = _build_chrome_service(driver_path)
            try:
                driver = webdriver.Chrome(service=retry_service, options=_build_chrome_options(fallback_profile))
                break
            except SessionNotCreatedException as retry_exc:
                last_error = retry_exc
                print(f"Chrome session retry failed with driver: {driver_label}")
        except Exception as exc:
            last_error = exc
            print(f"ChromeDriver start failed with driver: {driver_label} ({exc})")
        finally:
            if driver is None:
                try:
                    service.stop()
                except Exception:
                    pass
    else:
        print(f"ChromeDriver log: {CHROMEDRIVER_LOG_PATH}")
        if last_error is not None:
            raise last_error
        raise RuntimeError("No usable ChromeDriver candidate was found.")

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def wait_for_buyma_login(
    driver,
    *,
    safe_input_fn: Callable[[str], str],
    scroll_and_click_fn: Callable,
    wait_scale: float = 0.6,
) -> bool:
    email, password = load_buyma_credentials()
    if not email or not password:
        email, password = prompt_buyma_credentials()

    force_relogin = os.environ.get("AUTO_SHOP_FORCE_BUYMA_RELOGIN", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }

    current_url = _ensure_buyma_page(driver, BUYMA_SELL_URL, wait_scale=wait_scale)
    if not _is_buyma_url(current_url):
        print(f"Unexpected startup page detected: {current_url or '(empty url)'}")
        current_url = _ensure_buyma_page(driver, BUYMA_LOGIN_URL, wait_scale=wait_scale)

    if _is_buyma_url(current_url) and not _is_buyma_login_url(current_url) and not (force_relogin and email and password):
        print("Already logged in.")
        if current_url != BUYMA_SELL_URL:
            _ensure_buyma_page(driver, BUYMA_SELL_URL, wait_scale=wait_scale)
        return True

    if email and password:
        print("Trying auto login...")
        try:
            if force_relogin:
                try:
                    driver.get(BUYMA_LOGOUT_URL)
                    _sleep(2, wait_scale)
                except Exception:
                    pass
            current_url = _ensure_buyma_page(driver, BUYMA_LOGIN_URL, wait_scale=wait_scale)
            if not _is_buyma_url(current_url):
                print("BUYMA login page did not open correctly. Please check the browser window.")

            email_input = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, LOGIN_EMAIL_SELECTOR))
            )
            scroll_and_click_fn(driver, email_input)
            email_input.clear()
            email_input.send_keys(email)

            password_input = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, LOGIN_PASSWORD_SELECTOR))
            )
            scroll_and_click_fn(driver, password_input)
            password_input.clear()
            password_input.send_keys(password)

            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, LOGIN_SUBMIT_SELECTOR))
            )
            scroll_and_click_fn(driver, login_btn)
            _sleep(5, wait_scale)

            current_url = driver.current_url
            print(f"Post-login URL: {current_url}")
            if _is_buyma_url(current_url) and not _is_buyma_login_url(current_url):
                print("Auto login success.")
                _ensure_buyma_page(driver, BUYMA_SELL_URL, wait_scale=wait_scale)
                return True

            print("Auto login failed. Please login manually.")
            try:
                os.remove(BUYMA_CRED_PATH)
            except Exception:
                pass
        except Exception as exc:
            print(f"Auto login error: {exc}")

    print("\n" + "=" * 60)
    print("BUYMA login is required.")
    print("Please login manually in the browser window.")
    print("=" * 60 + "\n")

    for _ in range(300):
        _sleep(1, wait_scale)
        try:
            current_url = driver.current_url
            if _is_buyma_url(current_url) and not _is_buyma_login_url(current_url):
                print("Login success. Continuing.")
                _ensure_buyma_page(driver, BUYMA_SELL_URL, wait_scale=wait_scale)
                save = safe_input_fn("Save this account credential? (y/n): ").strip().lower()
                if save == "y":
                    new_email = safe_input_fn("  Email: ").strip()
                    new_pw = safe_input_fn("  Password: ").strip()
                    if new_email and new_pw:
                        save_buyma_credentials(new_email, new_pw)
                _sleep(2, wait_scale)
                return True
        except Exception:
            pass

    print("Login wait timeout (5 minutes).")
    return False
