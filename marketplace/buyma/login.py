"""BUYMA login/session helpers extracted from the legacy uploader."""

import glob
import json
import os
import tempfile
import time
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


def _sleep(seconds: float, wait_scale: float = 0.6) -> None:
    time.sleep(max(0.0, seconds * wait_scale))


def save_buyma_credentials(email: str, password: str) -> None:
    os.makedirs(os.path.dirname(BUYMA_CRED_PATH), exist_ok=True)
    import base64

    payload = {
        "email": base64.b64encode(email.encode()).decode(),
        "password": base64.b64encode(password.encode()).decode(),
    }
    with open(BUYMA_CRED_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file)
    print("  로그인 정보가 저장되었습니다.")


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
    print("\n바이마 로그인 정보를 입력해주세요 (최초 1회만):")
    email = input("  이메일: ").strip()
    password = input("  비밀번호: ").strip()
    if email and password:
        save_buyma_credentials(email, password)
    return email, password


def setup_visible_chrome_driver():
    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)

    def _build_options(user_data_dir: str) -> ChromeOptions:
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1400,900")
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        return chrome_options

    chrome_options = _build_options(CHROME_PROFILE_DIR)

    driver_path = None
    cached_candidates = sorted(
        glob.glob(
            os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver", "**", "chromedriver.exe"),
            recursive=True,
        )
    )
    if cached_candidates:
        driver_path = cached_candidates[-1]

    try:
        service = Service(driver_path or ChromeDriverManager().install())
    except PermissionError:
        if not driver_path:
            raise
        service = Service(driver_path)

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except SessionNotCreatedException as exc:
        if "failed to write prefs file" not in str(exc).lower():
            raise
        fallback_profile = tempfile.mkdtemp(prefix="buyma_profile_", dir=os.path.dirname(CHROME_PROFILE_DIR))
        print(f"Chrome 기본 프로필이 잠겨 있어 임시 프로필로 재시도합니다: {fallback_profile}")
        driver = webdriver.Chrome(service=service, options=_build_options(fallback_profile))

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
        "1", "true", "yes", "y", "on"
    }

    driver.get(BUYMA_SELL_URL)
    _sleep(3, wait_scale)

    if "/login" not in driver.current_url and not (force_relogin and email and password):
        print("이미 로그인 상태입니다.")
        return True

    if email and password:
        print("자동 로그인 시도 중...")
        try:
            if force_relogin:
                try:
                    driver.get(BUYMA_LOGOUT_URL)
                    _sleep(2, wait_scale)
                except Exception:
                    pass
            driver.get(BUYMA_LOGIN_URL)
            _sleep(2, wait_scale)

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

            if "/login" not in driver.current_url:
                print("✓ 자동 로그인 성공!")
                driver.get(BUYMA_SELL_URL)
                _sleep(2, wait_scale)
                return True

            print("✗ 자동 로그인 실패 (비밀번호 오류 또는 캡차 필요)")
            print("  저장된 로그인 정보가 틀리면 다음에 다시 입력해주세요.")
            try:
                os.remove(BUYMA_CRED_PATH)
            except Exception:
                pass
        except Exception as exc:
            print(f"✗ 자동 로그인 오류: {exc}")

    print("\n" + "=" * 60)
    print("  바이마 로그인이 필요합니다.")
    print("  브라우저에서 직접 로그인 해주세요.")
    print("  로그인 완료 감지되면 자동으로 진행됩니다.")
    print("=" * 60 + "\n")

    for _ in range(300):
        _sleep(1, wait_scale)
        try:
            current_url = driver.current_url
            if "/login" not in current_url:
                print("로그인 성공! 출품 페이지로 이동합니다..")
                save = safe_input_fn("  이 계정 정보를 저장하겠습니까? (y/n): ").strip().lower()
                if save == "y":
                    new_email = safe_input_fn("  이메일: ").strip()
                    new_pw = safe_input_fn("  비밀번호: ").strip()
                    if new_email and new_pw:
                        save_buyma_credentials(new_email, new_pw)
                _sleep(2, wait_scale)
                return True
        except Exception:
            pass

    print("로그인 대기시간 초과 (5분)")
    return False
