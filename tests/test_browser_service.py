import unittest

from services.browser_service import find_cached_chromedrivers


class BrowserServiceTests(unittest.TestCase):
    def test_find_cached_chromedrivers_sorts_versions_descending(self):
        paths = [
            "/tmp/.wdm/drivers/chromedriver/mac64/147.0.7727.57/chromedriver-mac-arm64/chromedriver",
            "/tmp/.wdm/drivers/chromedriver/mac64/146.0.7680.165/chromedriver-mac-arm64/chromedriver",
            "/tmp/.wdm/drivers/chromedriver/mac64/147.0.7727.117/chromedriver-mac-arm64/chromedriver",
        ]

        original_glob = __import__("services.browser_service", fromlist=["glob"]).glob.glob
        original_isfile = __import__("services.browser_service", fromlist=["os"]).os.path.isfile
        original_access = __import__("services.browser_service", fromlist=["os"]).os.access
        try:
            module = __import__("services.browser_service", fromlist=["glob", "os"])
            module.glob.glob = lambda *_args, **_kwargs: paths[:]
            module.os.path.isfile = lambda _path: True
            module.os.access = lambda _path, _mode: True

            result = find_cached_chromedrivers()
        finally:
            module.glob.glob = original_glob
            module.os.path.isfile = original_isfile
            module.os.access = original_access

        self.assertEqual(
            result,
            [
                "/tmp/.wdm/drivers/chromedriver/mac64/147.0.7727.117/chromedriver-mac-arm64/chromedriver",
                "/tmp/.wdm/drivers/chromedriver/mac64/147.0.7727.57/chromedriver-mac-arm64/chromedriver",
                "/tmp/.wdm/drivers/chromedriver/mac64/146.0.7680.165/chromedriver-mac-arm64/chromedriver",
            ],
        )


if __name__ == "__main__":
    unittest.main()
