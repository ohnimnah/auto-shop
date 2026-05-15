import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.action_runner import ActionRunner
from core.process_manager import ProcessManager
from services.pipeline_service import LauncherPipelineService, WatchPolicy
from state.app_state import AppLogger, AppState


class ActionRunnerTests(unittest.TestCase):
    def _runner(self, command_builder, policy=None, buyma_account_provider=None, owner_provider=None):
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
            buyma_account_provider=buyma_account_provider,
            owner_provider=owner_provider,
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

    def test_same_buyma_account_upload_is_blocked_by_lock(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"AUTO_SHOP_LOCK_DIR": tmp}, clear=False):
            command = lambda _action: [sys.executable, "-u", "-c", "import time; time.sleep(1)"]
            runner_a, _state_a, _manager_a, _events_a = self._runner(
                command,
                buyma_account_provider=lambda: "main@example.com",
                owner_provider=lambda: "형",
            )
            runner_b, state_b, _manager_b, events_b = self._runner(
                command,
                buyma_account_provider=lambda: "main@example.com",
                owner_provider=lambda: "누나",
            )

            self.assertTrue(runner_a.run("upload-auto"))
            self.assertFalse(runner_b.run("upload-auto"))
            runner_a.stop()

            self.assertEqual(state_b.status_text, "업로드 중복 차단")
            self.assertTrue(any("BUYMA 업로드 lock" in event.message for event in events_b))

    def test_different_buyma_account_uploads_are_allowed_by_lock(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"AUTO_SHOP_LOCK_DIR": tmp}, clear=False):
            command = lambda _action: [sys.executable, "-u", "-c", "import time; time.sleep(1)"]
            runner_a, _state_a, _manager_a, _events_a = self._runner(
                command,
                buyma_account_provider=lambda: "main@example.com",
                owner_provider=lambda: "형",
            )
            runner_b, _state_b, _manager_b, _events_b = self._runner(
                command,
                buyma_account_provider=lambda: "sub@example.com",
                owner_provider=lambda: "누나",
            )

            self.assertTrue(runner_a.run("upload-auto"))
            self.assertTrue(runner_b.run("upload-auto"))
            runner_a.stop()
            runner_b.stop()

    def test_upload_lock_is_released_after_process_exception(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"AUTO_SHOP_LOCK_DIR": tmp}, clear=False):
            def bad_command(_action):
                raise RuntimeError("boom")

            runner, _state, _manager, _events = self._runner(
                bad_command,
                buyma_account_provider=lambda: "main@example.com",
                owner_provider=lambda: "형",
            )

            self.assertFalse(runner.run("upload-auto"))

            self.assertFalse(list(Path(tmp).glob("upload_*.lock")))

    def test_upload_completion_notification_uses_row_counts(self):
        script = (
            "print('  10행 상태 업데이트: 출품완료'); "
            "print('  11행 상품입력 실패. 건너뜁니다'); "
            "print('  11행 상태 업데이트: 오류')"
        )
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"AUTO_SHOP_LOCK_DIR": tmp}, clear=False):
            runner, _state, _manager, _events = self._runner(
                lambda _action: [sys.executable, "-u", "-c", script],
                buyma_account_provider=lambda: "main@example.com",
                owner_provider=lambda: "형",
            )

            with patch("core.action_runner.notify_job_finished") as notify_finished:
                self.assertTrue(runner.run("upload-auto"))
                time.sleep(0.8)

        notify_finished.assert_called()
        _job_name, success_count, fail_count, _duration = notify_finished.call_args.args
        self.assertEqual(success_count, 1)
        self.assertEqual(fail_count, 1)

    def test_image_completion_notification_uses_row_counts(self):
        script = (
            "print('2026 [INFO] [IMAGE DONE] SKU=A ROW=3'); "
            "print('2026 [ERROR] [ERROR] SKU=B ROW=4 - image failed')"
        )
        runner, _state, _manager, _events = self._runner(
            lambda _action: [sys.executable, "-u", "-c", script]
        )

        with patch("core.action_runner.notify_job_finished") as notify_finished:
            self.assertTrue(runner.run("save-images"))
            time.sleep(0.8)

        _job_name, success_count, fail_count, _duration = notify_finished.call_args.args
        self.assertEqual(success_count, 1)
        self.assertEqual(fail_count, 1)

    def test_team_watch_completion_notification_uses_row_counts(self):
        script = "print('2026 [INFO] [THUMBNAIL DONE] ROW=7')"
        runner, _state, _manager, _events = self._runner(
            lambda _action: [sys.executable, "-u", "-c", script]
        )

        with patch("core.action_runner.notify_job_finished") as notify_finished:
            self.assertTrue(runner.start_team_watch("design"))
            time.sleep(0.8)

        _job_name, success_count, fail_count, _duration = notify_finished.call_args.args
        self.assertEqual(success_count, 1)
        self.assertEqual(fail_count, 0)


if __name__ == "__main__":
    unittest.main()
