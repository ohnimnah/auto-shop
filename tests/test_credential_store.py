import json
import os
import unittest
import uuid
from unittest.mock import patch

from app.security.credential_store import KeyringCredentialStore, KeyringTokenStore


class CredentialStoreTests(unittest.TestCase):
    def test_save_and_load_with_keyring_mock(self):
        os.makedirs("logs", exist_ok=True)
        path = os.path.join("logs", f"test_credential_store_{uuid.uuid4().hex}.json")
        store = KeyringCredentialStore(path)
        bag = {}

        def set_password(service, account, password):
            bag[(service, account)] = password

        def get_password(service, account):
            return bag.get((service, account))

        with patch("app.security.credential_store.keyring.set_password", side_effect=set_password), patch(
            "app.security.credential_store.keyring.get_password", side_effect=get_password
        ):
            store.save("a@b.com", "pw1")
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            self.assertEqual(meta["email"], "a@b.com")
            record = store.load()
            self.assertIsNotNone(record)
            self.assertEqual(record.password, "pw1")
        if os.path.exists(path):
            os.remove(path)

    def test_token_store_uses_keyring(self):
        bag = {}
        store = KeyringTokenStore(service_name="auto_shop.test.telegram", account_key="default.bot_token")

        def set_password(service, account, password):
            bag[(service, account)] = password

        def get_password(service, account):
            return bag.get((service, account))

        def delete_password(service, account):
            bag.pop((service, account), None)

        with patch("app.security.credential_store.keyring.set_password", side_effect=set_password), patch(
            "app.security.credential_store.keyring.get_password", side_effect=get_password
        ), patch(
            "app.security.credential_store.keyring.delete_password", side_effect=delete_password
        ):
            store.save("123:abc")
            self.assertTrue(store.exists())
            self.assertEqual(store.load(), "123:abc")
            store.delete()
            self.assertFalse(store.exists())


if __name__ == "__main__":
    unittest.main()
