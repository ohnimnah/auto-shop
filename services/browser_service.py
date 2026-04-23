"""Browser/WebDriver setup helpers."""

import glob
import os
import re

from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def _parse_version_parts(text: str) -> tuple[int, ...]:
    match = re.search(r"(\d+(?:\.\d+){1,3})", text or "")
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def find_cached_chromedrivers() -> list[str]:
    candidates = [
        path
        for path in glob.glob(
            os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver", "**", "chromedriver*"),
            recursive=True,
        )
        if os.path.isfile(path) and os.access(path, os.X_OK)
    ]
    return sorted(candidates, key=_parse_version_parts, reverse=True)


def setup_chrome_driver(headless: bool = False):
    """Create configured Chrome WebDriver."""
    def _build_options(*, use_headless: bool) -> ChromeOptions:
        chrome_options = ChromeOptions()
        if use_headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--remote-debugging-port=0")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return chrome_options

    cached_candidates = find_cached_chromedrivers()
    cached_driver = cached_candidates[0] if cached_candidates else ""

    if cached_driver:
        service = Service(cached_driver)
    else:
        # Fallback to webdriver-manager download only when cache is unavailable.
        service = Service(ChromeDriverManager().install())

    options = _build_options(use_headless=headless)
    try:
        return webdriver.Chrome(service=service, options=options)
    except SessionNotCreatedException:
        # Retry once with classic headless flag when Chrome runtime rejects `--headless=new`.
        fallback_options = _build_options(use_headless=False)
        if headless:
            fallback_options.add_argument("--headless")
        return webdriver.Chrome(service=service, options=fallback_options)
