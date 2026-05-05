import tempfile
import unittest
from contextlib import contextmanager
import shutil
import os
import uuid

from services.log_store import FileLogWriter
from state.app_state import AppLogger, AppState, LogEvent
from state.snapshot_store import StateSnapshotStore


class AppStateTests(unittest.TestCase):
    @contextmanager
    def _workspace_tempdir(self):
        os.makedirs("logs", exist_ok=True)
        path = os.path.join("logs", f"test_app_state_{uuid.uuid4().hex}")
        os.makedirs(path, exist_ok=True)
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_state_notifies_changed_key_only(self):
        state = AppState()
        changes = []
        state.subscribe(changes.append)

        state.set_status("실행중")
        state.set_stage_status("scout", "진행중")

        self.assertEqual([change.key for change in changes], ["status_text", "pipeline_status.scout"])

    def test_snapshot_round_trip_restores_minimal_state(self):
        with self._workspace_tempdir() as temp_dir:
            path = f"{temp_dir}/snapshot.json"
            state = AppState()
            state.set_status("대기중")
            state.set_stage_status("assets", "감시중")
            state.set_team_watch_enabled("assets", True)
            state.record_team_watch_failure("assets")
            store = StateSnapshotStore(path)

            store.save(state)
            restored = AppState()
            self.assertTrue(store.load_into(restored))

            self.assertEqual(restored.pipeline_status["assets"], "감시중")
            self.assertTrue(restored.team_watch_enabled["assets"])
            self.assertEqual(restored.team_watch_failures["assets"], 1)

    def test_logger_emits_log_event_and_file_writer_persists_jsonl(self):
        with self._workspace_tempdir() as temp_dir:
            logger = AppLogger()
            events = []
            writer = FileLogWriter(temp_dir)
            logger.subscribe(events.append)
            logger.subscribe(writer.handle)

            logger.log(LogEvent(level="INFO", category="test", message="hello\n"))

            self.assertEqual(events[0].category, "test")
            files = list(__import__("pathlib").Path(temp_dir).glob("launcher-*.log"))
            self.assertEqual(len(files), 1)
            self.assertIn('"message": "hello"', files[0].read_text(encoding="utf-8"))

    def test_file_log_writer_uses_dynamic_log_dir(self):
        with self._workspace_tempdir() as first_dir, self._workspace_tempdir() as second_dir:
            current = {"path": first_dir}
            writer = FileLogWriter(lambda: current["path"])

            writer.handle(LogEvent(level="INFO", category="test", message="first"))
            current["path"] = second_dir
            writer.handle(LogEvent(level="INFO", category="test", message="second"))

            first_files = list(__import__("pathlib").Path(first_dir).glob("launcher-*.log"))
            second_files = list(__import__("pathlib").Path(second_dir).glob("launcher-*.log"))
            self.assertEqual(len(first_files), 1)
            self.assertEqual(len(second_files), 1)


if __name__ == "__main__":
    unittest.main()
