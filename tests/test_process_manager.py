import sys
import time
import unittest

from core.process_manager import ProcessManager, build_default_env


class ProcessManagerTests(unittest.TestCase):
    def test_single_process_stop_joins_thread(self):
        manager = ProcessManager(".", lambda: {})
        lines = []
        done = []

        started = manager.start(
            [sys.executable, "-u", "-c", "import time; print('start', flush=True); time.sleep(5)"],
            lines.append,
            done.append,
        )
        time.sleep(0.3)
        manager.stop()

        self.assertTrue(started)
        self.assertFalse(manager.is_running())
        self.assertIsNone(manager.thread)
        self.assertIn("start\n", lines)
        self.assertTrue(done)

    def test_team_process_duplicate_is_rejected(self):
        manager = ProcessManager(".", lambda: {})
        done = []

        first = manager.start_team(
            "assets",
            [sys.executable, "-u", "-c", "import time; print('team', flush=True); time.sleep(1)"],
            lambda _line: None,
            done.append,
        )
        second = manager.start_team(
            "assets",
            [sys.executable, "-u", "-c", "print('duplicate')"],
            lambda _line: None,
            done.append,
        )
        manager.stop_team("assets")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertFalse(manager.is_team_running("assets"))

    def test_default_env_forces_utf8_output(self):
        env = build_default_env("/tmp/data", "/tmp/images")

        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env["PYTHONUTF8"], "1")


if __name__ == "__main__":
    unittest.main()
