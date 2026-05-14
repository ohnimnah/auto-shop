import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from services.lock_service import (
    acquire_upload_lock,
    build_upload_account_id,
    get_upload_lock_dir,
    get_upload_lock_info,
    is_upload_locked,
    release_upload_lock,
)


class UploadLockServiceTests(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = patch("services.lock_service.time.sleep", return_value=None)
        self.sleep_patch.start()

    def tearDown(self):
        self.sleep_patch.stop()

    def test_same_account_duplicate_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            ok, _info = acquire_upload_lock("buyma_main", "형", lock_dir=lock_dir)
            self.assertTrue(ok)

            ok, info = acquire_upload_lock("buyma_main", "누나", lock_dir=lock_dir)

            self.assertFalse(ok)
            self.assertEqual(info["owner"], "형")

    def test_active_claim_blocks_later_upload_before_main_lock_syncs(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            lock_dir.mkdir(parents=True, exist_ok=True)
            claim_path = lock_dir / "upload_buyma_main.early.claim"
            claim_path.write_text(
                json.dumps(
                    {
                        "account_id": "buyma_main",
                        "owner": "형",
                        "pc_name": "PC-A",
                        "started_at": (datetime.now() - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
                        "claim_id": "early",
                        "type": "buyma_upload",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            ok, info = acquire_upload_lock("buyma_main", "누나", lock_dir=lock_dir)

            self.assertFalse(ok)
            self.assertEqual(info["owner"], "형")
            self.assertEqual(info["pc_name"], "PC-A")

    def test_lock_payload_includes_pc_name(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"COMPUTERNAME": "DESKTOP-HYUNG"}, clear=False):
            lock_dir = Path(tmp)
            ok, info = acquire_upload_lock("buyma_main", "형", lock_dir=lock_dir)

            self.assertTrue(ok)
            self.assertEqual(info["pc_name"], "DESKTOP-HYUNG")
            self.assertEqual(get_upload_lock_info("buyma_main", lock_dir=lock_dir)["pc_name"], "DESKTOP-HYUNG")

    def test_shared_lock_folder_can_be_used_from_multiple_pc_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            with patch.dict(os.environ, {"COMPUTERNAME": "PC-A"}, clear=False):
                ok, _ = acquire_upload_lock("buyma_main", "형", lock_dir=lock_dir)
                self.assertTrue(ok)

            with patch.dict(os.environ, {"COMPUTERNAME": "PC-B"}, clear=False):
                ok, info = acquire_upload_lock("buyma_main", "누나", lock_dir=lock_dir)

            self.assertFalse(ok)
            self.assertEqual(info["pc_name"], "PC-A")

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
            self.assertFalse(list(lock_dir.glob("upload_buyma_main.*.claim")))

    def test_account_id_is_stable_and_filename_safe(self):
        account_id = build_upload_account_id("User.Name+Shop@example.com")

        self.assertTrue(account_id.startswith("buyma_user.name_shop_"))
        self.assertNotIn("@", account_id)

    def test_auto_shop_lock_dir_env_has_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            configured = Path(tmp) / "Dropbox" / "AutoShop" / "locks"
            with patch.dict(os.environ, {"AUTO_SHOP_LOCK_DIR": str(configured), "AUTO_SHOP_DATA_DIR": str(Path(tmp) / "local")}, clear=False):
                self.assertEqual(get_upload_lock_dir(), configured)

    def test_fallback_uses_local_data_dir_when_lock_dir_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            with patch.dict(os.environ, {"AUTO_SHOP_DATA_DIR": str(data_dir)}, clear=False):
                os.environ.pop("AUTO_SHOP_LOCK_DIR", None)

                self.assertEqual(get_upload_lock_dir(), data_dir / "locks")


if __name__ == "__main__":
    unittest.main()
