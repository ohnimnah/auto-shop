import tempfile
import unittest

from services.log_store import FileLogWriter
from state.app_state import AppLogger, AppState, LogEvent
from state.snapshot_store import StateSnapshotStore


class AppStateTests(unittest.TestCase):
    def test_state_notifies_changed_key_only(self):
        state = AppState()
        changes = []
        state.subscribe(changes.append)

        state.set_status("실행중")
        state.set_stage_status("scout", "진행중")

        self.assertEqual([change.key for change in changes], ["status_text", "pipeline_status.scout"])

    def test_snapshot_round_trip_restores_minimal_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
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
        with tempfile.TemporaryDirectory() as temp_dir:
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


if __name__ == "__main__":
    unittest.main()
