import unittest
from unittest.mock import patch

from marketplace.buyma import login


class FakeDriver:
    def __init__(self):
        self.visited = []
        self._current_url = "https://www.google.com/"

    def get(self, url):
        self.visited.append(url)
        if url == login.BUYMA_SELL_URL:
            self._current_url = login.BUYMA_LOGIN_URL
        else:
            self._current_url = url

    @property
    def current_url(self):
        if self.visited.count(login.BUYMA_LOGIN_URL) >= 1:
            return login.BUYMA_SELL_URL
        return self._current_url


class BuymaLoginTests(unittest.TestCase):
    def test_opens_buyma_login_page_before_manual_login_when_credentials_missing(self):
        driver = FakeDriver()

        with patch("marketplace.buyma.login.load_buyma_credentials", return_value=(None, None)):
            result = login.wait_for_buyma_login(
                driver,
                safe_input_fn=lambda _prompt: "n",
                wait_scale=0,
            )

        self.assertTrue(result)
        self.assertEqual(driver.visited[0], login.BUYMA_SELL_URL)
        self.assertIn(login.BUYMA_LOGIN_URL, driver.visited)


if __name__ == "__main__":
    unittest.main()
