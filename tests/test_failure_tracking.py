import json
import os
import unittest
import shutil
import uuid
from unittest.mock import patch

from marketplace.buyma.failure_tracking import capture_failure_artifacts


class _FakeDriver:
    def __init__(self):
        self.saved = []

    def save_screenshot(self, path):
        self.saved.append(path)
        with open(path, "wb") as f:
            f.write(b"x")
        return True


class FailureTrackingTests(unittest.TestCase):
    def test_jsonl_written(self):
        tmp = os.path.join("logs", f"test_failure_tracking_{uuid.uuid4().hex}")
        os.makedirs(tmp, exist_ok=True)
        try:
            driver = _FakeDriver()
            with patch("marketplace.buyma.failure_tracking._runtime_logs_dir", return_value=tmp):
                capture_failure_artifacts(driver, row=12, step="select_category", error="boom", retry_count=2)
            log_path = os.path.join(tmp, "upload_failures.jsonl")
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as fh:
                line = fh.read().strip()
            data = json.loads(line)
            self.assertEqual(data["row"], 12)
            self.assertEqual(data["step"], "select_category")
            self.assertEqual(data["retry_count"], 2)
            self.assertTrue(data["screenshot"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
