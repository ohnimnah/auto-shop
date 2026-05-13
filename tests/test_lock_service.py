import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from services.lock_service import (
    acquire_upload_lock,
    build_upload_account_id,
    get_upload_lock_info,
    is_upload_locked,
    release_upload_lock,
)


class UploadLockServiceTests(unittest.TestCase):
    def test_same_account_duplicate_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            ok, _info = acquire_upload_lock("buyma_main", "형", lock_dir=lock_dir)
            self.assertTrue(ok)

            ok, info = acquire_upload_lock("buyma_main", "누나", lock_dir=lock_dir)

            self.assertFalse(ok)
            self.assertEqual(info["owner"], "형")

    def test_different_accounts_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            ok_a, _ = acquire_upload_lock("buyma_main", "형", lock_dir=lock_dir)
            ok_b, _ = acquire_upload_lock("buyma_sub", "누나", lock_dir=lock_dir)

            self.assertTrue(ok_a)
            self.assertTrue(ok_b)

    def test_stale_lock_is_removed_and_reacquired(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            lock_path = lock_dir / "upload_buyma_main.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {
                        "account_id": "buyma_main",
                        "owner": "형",
                        "started_at": (datetime.now() - timedelta(minutes=31)).strftime("%Y-%m-%d %H:%M:%S"),
                        "type": "buyma_upload",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            ok, info = acquire_upload_lock("buyma_main", "누나", lock_dir=lock_dir)

            self.assertTrue(ok)
            self.assertEqual(info["owner"], "누나")

    def test_release_upload_lock_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            acquire_upload_lock("buyma_main", "형", lock_dir=lock_dir)

            release_upload_lock("buyma_main", lock_dir=lock_dir)

            self.assertFalse(is_upload_locked("buyma_main", lock_dir=lock_dir))
            self.assertIsNone(get_upload_lock_info("buyma_main", lock_dir=lock_dir))

    def test_account_id_is_stable_and_filename_safe(self):
        account_id = build_upload_account_id("User.Name+Shop@example.com")

        self.assertTrue(account_id.startswith("buyma_user.name_shop_"))
        self.assertNotIn("@", account_id)


if __name__ == "__main__":
    unittest.main()
