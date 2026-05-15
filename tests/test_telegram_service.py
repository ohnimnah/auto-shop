import os
import json
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
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz",
            "TELEGRAM_CHAT_ID": "456",
        }
        with patch.dict(os.environ, env, clear=False), patch("services.telegram_service.requests", fake_requests):
            self.assertTrue(telegram_service.send_message("hello"))

        self.assertEqual(len(fake_requests.calls), 1)
        self.assertIn("/bot123456:abcdefghijklmnopqrstuvwxyz/sendMessage", fake_requests.calls[0]["url"])
        self.assertEqual(fake_requests.calls[0]["data"]["chat_id"], "456")
        self.assertEqual(fake_requests.calls[0]["timeout"], 10)

    def test_send_message_deduplicates_for_five_minutes(self):
        fake_requests = _FakeRequests()
        env = {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz",
            "TELEGRAM_CHAT_ID": "456",
        }
        with patch.dict(os.environ, env, clear=False), patch("services.telegram_service.requests", fake_requests):
            self.assertTrue(telegram_service.send_message("same error"))
            self.assertFalse(telegram_service.send_message("same error"))

        self.assertEqual(len(fake_requests.calls), 1)

    def test_upload_success_dedup_uses_row_number(self):
        fake_requests = _FakeRequests()
        env = {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz",
            "TELEGRAM_CHAT_ID": "456",
        }
        base = {
            "product_name": "same product",
            "brand": "same brand",
            "price": "10000",
            "category": "Tシャツ・カットソー",
        }
        with patch.dict(os.environ, env, clear=False), patch("services.telegram_service.requests", fake_requests):
            self.assertTrue(telegram_service.notify_upload_success({**base, "row_num": 10}))
            self.assertTrue(telegram_service.notify_upload_success({**base, "row_num": 11}))
            self.assertFalse(telegram_service.notify_upload_success({**base, "row_num": 10}))

        self.assertEqual(len(fake_requests.calls), 2)

    def test_send_message_preserves_notification_line_breaks(self):
        fake_requests = _FakeRequests()
        env = {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz",
            "TELEGRAM_CHAT_ID": "456",
        }
        text = "✅ 작업 완료\n------------\n작업: 정찰\n\n성공: 1\n실패: 0"
        with patch.dict(os.environ, env, clear=False), patch("services.telegram_service.requests", fake_requests):
            self.assertTrue(telegram_service.send_message(text))

        self.assertEqual(fake_requests.calls[0]["data"]["text"], text)

    def test_send_control_panel_posts_inline_keyboard(self):
        fake_requests = _FakeRequests()
        env = {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz",
            "TELEGRAM_CHAT_ID": "456",
        }
        with patch.dict(os.environ, env, clear=False), patch("services.telegram_service.requests", fake_requests):
            self.assertTrue(telegram_service.send_control_panel())

        payload = fake_requests.calls[0]["data"]
        keyboard = json.loads(payload["reply_markup"])
        callbacks = [
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
            if "callback_data" in button
        ]
        self.assertIn("auto_shop:run:collect-listings", callbacks)
        self.assertIn("auto_shop:run:scout", callbacks)
        self.assertIn("auto_shop:run:upload", callbacks)
        self.assertIn("auto_shop:stop", callbacks)

    def test_missing_credentials_disables_notification(self):
        fake_requests = _FakeRequests()
        with patch.dict(os.environ, {"TELEGRAM_ENABLED": "true"}, clear=True), patch(
            "services.telegram_service.requests", fake_requests
        ):
            self.assertFalse(telegram_service.send_message("hello"))

        self.assertEqual(fake_requests.calls, [])

    def test_notification_status_reports_missing_token_without_exposing_values(self):
        with patch.dict(os.environ, {"TELEGRAM_ENABLED": "true", "TELEGRAM_CHAT_ID": "456"}, clear=True), patch(
            "services.telegram_service.KeyringTokenStore"
        ) as store_class:
            store_class.return_value.load.return_value = ""

            status = telegram_service.get_notification_status()

        self.assertTrue(status["enabled"])
        self.assertFalse(status["token_set"])
        self.assertTrue(status["chat_id_set"])
        self.assertNotIn("456", str(status))

    def test_token_load_falls_back_to_default_profile_keyring(self):
        fake_requests = _FakeRequests()

        def store_for_account(*, service_name, account_key):
            class _Store:
                def load(self):
                    return "123456:abcdefghijklmnopqrstuvwxyz" if account_key == "default.bot_token" else ""

            return _Store()

        with patch.dict(
            os.environ,
            {"AUTO_SHOP_PROFILE": "operator-a", "TELEGRAM_ENABLED": "true", "TELEGRAM_CHAT_ID": "456"},
            clear=True,
        ), patch("services.telegram_service.requests", fake_requests), patch(
            "services.telegram_service.KeyringTokenStore", side_effect=store_for_account
        ):
            self.assertTrue(telegram_service.send_message("fallback token"))

        self.assertEqual(len(fake_requests.calls), 1)

    def test_job_finished_message_is_readable_multiline_summary(self):
        with patch("services.telegram_service.send_message") as send_message:
            telegram_service.notify_job_finished("정찰", success_count=1, fail_count=0, duration=6)

        text = send_message.call_args.args[0]
        self.assertIn("✅ 작업 완료", text)
        self.assertIn("------------", text)
        self.assertIn("작업: 정찰\n\n정찰 성공: 1", text)
        self.assertIn("정찰 실패: 0\n소요시간: 6초", text)

    def test_job_finished_warns_when_failures_exist(self):
        with patch("services.telegram_service.send_message") as send_message:
            telegram_service.notify_job_finished("정찰 감시", success_count=0, fail_count=1, duration=10)

        text = send_message.call_args.args[0]
        self.assertIn("⚠️ 작업 완료", text)
        self.assertIn("정찰 실패: 1", text)

    def test_upload_job_finished_uses_korean_upload_count_labels(self):
        with patch("services.telegram_service.send_message") as send_message:
            telegram_service.notify_job_finished("BUYMA 업로드", success_count=5, fail_count=2, duration=70)

        text = send_message.call_args.args[0]
        self.assertIn("업로드 성공: 5", text)
        self.assertIn("업로드 실패: 2", text)

    def test_upload_success_translates_common_buyma_child_categories(self):
        product = {
            "product_name": "sample",
            "brand": "brand",
            "buyma_price": "10000",
            "category": "レディースファッション > ボトムス > デニム・ジーパン",
        }
        with patch("services.telegram_service.send_message") as send_message:
            telegram_service.notify_upload_success(product)

        text = send_message.call_args.args[0]
        self.assertIn("카테고리: デニム・ジーパン (데님/청바지)", text)

    def test_upload_success_translates_missing_log_categories(self):
        expected = {
            "ショートパンツ": "반바지",
            "ワンピース": "원피스",
            "スカート": "스커트",
            "カーディガン": "가디건",
        }

        for category, translated in expected.items():
            with self.subTest(category=category), patch("services.telegram_service.send_message") as send_message:
                telegram_service.notify_upload_success({"product_name": "sample", "category": category})
                text = send_message.call_args.args[0]
                self.assertIn(f"카테고리: {category} ({translated})", text)

    def test_upload_lock_notification_is_readable(self):
        with patch("services.telegram_service.send_message") as send_message:
            telegram_service.notify_upload_locked(
                {
                    "account_id": "buyma_main",
                    "owner": "누나",
                    "pc_name": "DESKTOP-NUNA",
                    "started_at": "2026-05-13 15:22:00",
                }
            )

        text = send_message.call_args.args[0]
        self.assertIn("⚠️ 현재 업로드 실행 중", text)
        self.assertIn("계정: buyma_main", text)
        self.assertIn("사용자: 누나", text)
        self.assertIn("PC: DESKTOP-NUNA", text)
        self.assertIn("시작시간: 15:22", text)

    def test_sensitive_values_are_masked(self):
        fake_requests = _FakeRequests()
        env = {
            "TELEGRAM_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz",
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
