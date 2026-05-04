import os
import unittest
from unittest.mock import patch

from services import telegram_service


class _FakeResponse:
    def raise_for_status(self):
        return None


class _FakeRequests:
    def __init__(self):
        self.calls = []

    def post(self, url, data, timeout):
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        return _FakeResponse()


class TelegramServiceTests(unittest.TestCase):
    def setUp(self):
        telegram_service._DEDUP_CACHE.clear()

    def tearDown(self):
        telegram_service._DEDUP_CACHE.clear()

    def test_send_message_posts_when_configured_by_env(self):
        fake_requests = _FakeRequests()
        env = {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "TELEGRAM_CHAT_ID": "456",
        }
        with patch.dict(os.environ, env, clear=False), patch("services.telegram_service.requests", fake_requests):
            self.assertTrue(telegram_service.send_message("hello"))

        self.assertEqual(len(fake_requests.calls), 1)
        self.assertIn("/bot123:abc/sendMessage", fake_requests.calls[0]["url"])
        self.assertEqual(fake_requests.calls[0]["data"]["chat_id"], "456")
        self.assertEqual(fake_requests.calls[0]["timeout"], 10)

    def test_send_message_deduplicates_for_five_minutes(self):
        fake_requests = _FakeRequests()
        env = {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "TELEGRAM_CHAT_ID": "456",
        }
        with patch.dict(os.environ, env, clear=False), patch("services.telegram_service.requests", fake_requests):
            self.assertTrue(telegram_service.send_message("same error"))
            self.assertFalse(telegram_service.send_message("same error"))

        self.assertEqual(len(fake_requests.calls), 1)

    def test_missing_credentials_disables_notification(self):
        fake_requests = _FakeRequests()
        with patch.dict(os.environ, {"TELEGRAM_ENABLED": "true"}, clear=True), patch(
            "services.telegram_service.requests", fake_requests
        ):
            self.assertFalse(telegram_service.send_message("hello"))

        self.assertEqual(fake_requests.calls, [])

    def test_sensitive_values_are_masked(self):
        fake_requests = _FakeRequests()
        env = {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "TELEGRAM_CHAT_ID": "456",
        }
        message = "user@example.com /tmp/auto_shop/credentials.json 123456:abcdefghijklmnopqrstuvwxyz"
        with patch.dict(os.environ, env, clear=False), patch("services.telegram_service.requests", fake_requests):
            self.assertTrue(telegram_service.send_message(message))

        sent = fake_requests.calls[0]["data"]["text"]
        self.assertIn("[masked-email]", sent)
        self.assertIn("[masked-sensitive-path]", sent)
        self.assertIn("[masked-telegram-token]", sent)
        self.assertNotIn("user@example.com", sent)


if __name__ == "__main__":
    unittest.main()
