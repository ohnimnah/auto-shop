"""Application action orchestration independent from the dashboard view."""

from __future__ import annotations

from typing import Callable

from core.process_manager import ProcessManager
from services.pipeline_service import LauncherPipelineService
from state.app_state import AppLogger, AppState, LogEvent


class ActionRunner:
    def __init__(
        self,
        *,
        script_dir: str,
        state: AppState,
        logger: AppLogger,
        process_manager: ProcessManager,
        command_builder: Callable[[str], list[str]],
        ensure_ready: Callable[[str], bool],
        pipeline_service: LauncherPipelineService | None = None,
    ) -> None:
        self.script_dir = script_dir
        self.state = state
        self.logger = logger
        self.process_manager = process_manager
        self.command_builder = command_builder
        self.ensure_ready = ensure_ready
        self.pipeline_service = pipeline_service or LauncherPipelineService()
        self.team_watch_actions = dict(self.pipeline_service.team_watch_actions)

    def run(self, action: str) -> bool:
        if self.process_manager.is_running():
            self._log("이미 작업이 실행 중입니다. 먼저 중지해주세요.\n", level="WARN")
            return False
        if not self.ensure_ready(action):
            return False
        self.state.reset_stage_statuses()
        stage_key = self.pipeline_service.stage_for_action(action)
        self.state.set_current_action(action, stage_key)
        if stage_key:
            self.state.set_stage_status(stage_key, "진행중")
        self.state.set_status("작전 준비중")

        command = self.command_builder(action)
        self._log("\n" + "=" * 70 + "\n", category="process")
        self._log(f"실행: {' '.join(command)}\n", category="process")
        try:
            started = self.process_manager.start(
                command,
                on_line=lambda line: self._handle_line(action, line),
                on_done=self._handle_done,
            )
        except Exception as exc:
            self._log(f"실행 실패: {exc}\n", level="ERROR", category="process")
            self.state.set_status("실행 실패")
            self.state.mark_current_stage_done(False)
            return False
        if started:
            self.state.set_status("작전 진행중")
        return started

    def run_command(self, command: list[str], *, action: str, stage_key: str = "") -> bool:
        if self.process_manager.is_running():
            self._log("이미 작업이 실행 중입니다. 먼저 중지해주세요.\n", level="WARN")
            return False
        stage_key = stage_key or self.pipeline_service.stage_for_action(action)
        self.state.set_current_action(action, stage_key)
        if stage_key:
            self.state.set_stage_status(stage_key, "진행중")
        self.state.set_status("작전 진행중")
        self._log("\n" + "=" * 70 + "\n", category="process")
        self._log(f"실행: {' '.join(command)}\n", category="process")
        try:
            return self.process_manager.start(
                command,
                on_line=lambda line: self._handle_line(action, line),
                on_done=self._handle_done,
            )
        except Exception as exc:
            self._log(f"실행 실패: {exc}\n", level="ERROR", category="process")
            self.state.set_status("실행 실패")
            self.state.mark_current_stage_done(False)
            return False

    def stop(self) -> None:
        self._log("\n중지 요청 전송...\n", category="process")
        self.state.mark_current_stage_done(False)
        self.process_manager.stop()
        self.state.set_status("대기중")

    def start_team_watch(self, team_key: str) -> bool:
        action = self.team_watch_actions.get(team_key)
        if not action or not self.ensure_ready(action):
            return False
        self.state.set_team_watch_enabled(team_key, True)
        self.state.set_stage_status(team_key, "감시중")
        command = self.command_builder(action)
        self._log(f"워커 실행: {' '.join(command)}\n", category=team_key)
        try:
            return self.process_manager.start_team(
                team_key,
                command,
                on_line=lambda line: self._log(line, category=team_key),
                on_done=lambda code: self._handle_team_done(team_key, code),
            )
        except Exception as exc:
            self._log(f"워커 실행 실패: {exc}\n", level="ERROR", category=team_key)
            self.state.set_stage_status(team_key, "실패")
            return False

    def stop_team_watch(self, team_key: str) -> None:
        self.state.set_team_watch_enabled(team_key, False)
        self.process_manager.stop_team(team_key)
        self.state.set_stage_status(team_key, "대기")
        self._log("팀 감시 중지\n", category=team_key)

    def stop_all(self) -> None:
        self.process_manager.stop()
        self.process_manager.stop_all_teams()

    def _handle_line(self, action: str, line: str) -> None:
        if action == "watch":
            self._log(line, category="scout")
        else:
            self._log(line, category="process")
        stage_key = self.pipeline_service.stage_from_log(line)
        if stage_key:
            self.state.set_current_action(self.state.current_action, stage_key)
            self.state.set_stage_status(stage_key, "진행중")

    def _handle_done(self, return_code: int) -> None:
        success = return_code == 0
        self._log(f"\n작업 종료 (code: {return_code})\n", category="process")
        self.state.record_process_done(success)
        self.state.mark_current_stage_done(success)
        current_stage = self.state.current_stage_key
        if current_stage and self.state.team_watch_enabled.get(current_stage, False):
            self.state.set_stage_status(current_stage, "감시중")
        self.state.set_current_action("", "")
        self.state.set_status("대기중")

    def _handle_team_done(self, team_key: str, return_code: int) -> None:
        self._log(f"워커 종료 (code: {return_code})\n", category=team_key)
        enabled = self.state.team_watch_enabled.get(team_key, False)
        self.state.set_stage_status(team_key, self.pipeline_service.team_done_status(enabled))

    def _log(self, message: str, *, level: str = "INFO", category: str = "runner") -> None:
        self.logger.log(LogEvent(level=level, category=category, message=message))
