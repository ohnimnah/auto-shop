import json
import os
import unittest
import uuid
from unittest.mock import patch

from app.security.credential_store import KeyringCredentialStore


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


if __name__ == "__main__":
    unittest.main()
