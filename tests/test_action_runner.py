import sys
import time
import unittest

from core.action_runner import ActionRunner
from core.process_manager import ProcessManager
from services.pipeline_service import LauncherPipelineService, WatchPolicy
from state.app_state import AppLogger, AppState


class ActionRunnerTests(unittest.TestCase):
    def _runner(self, command_builder, policy=None):
        state = AppState()
        logger = AppLogger()
        events = []
        logger.subscribe(events.append)
        manager = ProcessManager(".", lambda: {})
        runner = ActionRunner(
            script_dir=".",
            state=state,
            logger=logger,
            process_manager=manager,
            command_builder=command_builder,
            ensure_ready=lambda _action: True,
            pipeline_service=LauncherPipelineService(policy),
        )
        return runner, state, manager, events

    def test_run_completes_and_updates_state(self):
        runner, state, _manager, events = self._runner(
            lambda _action: [sys.executable, "-u", "-c", "print('main.py --download-images')"]
        )

        self.assertTrue(runner.run("save-images"))
        time.sleep(0.8)

        self.assertEqual(state.status_text, "대기중")
        self.assertEqual(state.today_processed, 1)
        self.assertEqual(state.pipeline_status["assets"], "완료")
        self.assertEqual(events[0].__class__.__name__, "LogEvent")

    def test_running_action_duplicate_is_rejected(self):
        runner, _state, manager, events = self._runner(
            lambda _action: [sys.executable, "-u", "-c", "import time; time.sleep(2)"]
        )

        self.assertTrue(runner.run("watch"))
        self.assertFalse(runner.run("run"))
        runner.stop()

        self.assertFalse(manager.is_running())
        self.assertTrue(any("ACTION_ALREADY_RUNNING" in event.message for event in events))

    def test_team_watch_failure_limit_pauses_watch(self):
        runner, state, _manager, events = self._runner(
            lambda _action: [sys.executable, "-u", "-c", "import sys; sys.exit(1)"],
            policy=WatchPolicy(max_failures_before_pause=2),
        )

        self.assertTrue(runner.start_team_watch("assets"))
        time.sleep(0.5)
        self.assertTrue(runner.start_team_watch("assets"))
        time.sleep(0.5)

        self.assertFalse(state.team_watch_enabled["assets"])
        self.assertEqual(state.pipeline_status["assets"], "실패")
        self.assertTrue(any("TEAM_WATCH_FAILURE_LIMIT" in event.message for event in events))


if __name__ == "__main__":
    unittest.main()
