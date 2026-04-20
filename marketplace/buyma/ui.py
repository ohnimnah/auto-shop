"""BUYMA low-level UI helpers."""

from __future__ import annotations


def scroll_and_click(driver, element, *, sleep_fn) -> None:
    """Scroll element into view and click safely."""
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", element)
    driver.execute_script("window.scrollBy(0, -120);")
    sleep_fn(0.3)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def dismiss_overlay(driver, *, sleep_fn) -> None:
    """Remove onboarding overlays that can block BUYMA interactions."""
    driver.execute_script(
        """
        document.querySelectorAll('#driver-page-overlay, .driver-popover, [id*="driver-"]')
            .forEach(function(el) { el.remove(); });
        """
    )
    sleep_fn(0.3)
