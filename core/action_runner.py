"""Application action orchestration independent from the dashboard view."""

from __future__ import annotations

import time
from typing import Callable

from core.errors import AppError, ErrorCode
from core.process_manager import ProcessManager
from services.pipeline_service import LauncherPipelineService
from services.telegram_service import (
    notify_critical_error,
    notify_emergency_stop,
    notify_job_finished,
    notify_job_started,
)
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
        self._job_started_at: float = 0.0
        self._job_name: str = ""
        self._team_started_at: dict[str, float] = {}

    def run(self, action: str) -> bool:
        if self.process_manager.is_running():
            self._log_error(ErrorCode.ACTION_ALREADY_RUNNING, "이미 작업이 실행 중입니다. 먼저 중지해주세요.\n", level="WARN")
            return False
        if not self.ensure_ready(action):
            self._log_error(ErrorCode.ACTION_NOT_READY, f"실행 준비가 완료되지 않았습니다: {action}\n", level="WARN")
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
        except AppError as exc:
            self._log_error(exc.code, f"실행 실패: {exc.message}\n", category="process")
            notify_critical_error("ActionRunner.run", exc.message)
            self.state.set_status("실행 실패")
            self.state.mark_current_stage_done(False)
            return False
        except Exception as exc:
            self._log(f"실행 실패: {exc}\n", level="ERROR", category="process")
            notify_critical_error("ActionRunner.run", exc)
            self.state.set_status("실행 실패")
            self.state.mark_current_stage_done(False)
            return False
        if started:
            self._job_started_at = time.time()
            self._job_name = self._job_label(action)
            notify_job_started(self._job_name)
            self.state.set_status("작전 진행중")
        return started

    def run_command(self, command: list[str], *, action: str, stage_key: str = "") -> bool:
        if self.process_manager.is_running():
            self._log_error(ErrorCode.ACTION_ALREADY_RUNNING, "이미 작업이 실행 중입니다. 먼저 중지해주세요.\n", level="WARN")
            return False
        stage_key = stage_key or self.pipeline_service.stage_for_action(action)
        self.state.set_current_action(action, stage_key)
        if stage_key:
            self.state.set_stage_status(stage_key, "진행중")
        self.state.set_status("작전 진행중")
        self._log("\n" + "=" * 70 + "\n", category="process")
        self._log(f"실행: {' '.join(command)}\n", category="process")
        try:
            started = self.process_manager.start(
                command,
                on_line=lambda line: self._handle_line(action, line),
                on_done=self._handle_done,
            )
            if started:
                self._job_started_at = time.time()
                self._job_name = self._job_label(action)
                notify_job_started(self._job_name)
            return started
        except AppError as exc:
            self._log_error(exc.code, f"실행 실패: {exc.message}\n", category="process")
            notify_critical_error("ActionRunner.run_command", exc.message)
            self.state.set_status("실행 실패")
            self.state.mark_current_stage_done(False)
            return False
        except Exception as exc:
            self._log(f"실행 실패: {exc}\n", level="ERROR", category="process")
            notify_critical_error("ActionRunner.run_command", exc)
            self.state.set_status("실행 실패")
            self.state.mark_current_stage_done(False)
            return False

    def stop(self) -> None:
        self._log("\n중지 요청 전송...\n", category="process")
        notify_emergency_stop(f"{self._job_name or '현재 작업'} 중지 요청")
        self.state.mark_current_stage_done(False)
        try:
            self.process_manager.stop()
        except AppError as exc:
            self._log_error(exc.code, f"중지 실패: {exc.message}\n", category="process")
        self.state.set_status("대기중")

    def start_team_watch(self, team_key: str) -> bool:
        action = self.team_watch_actions.get(team_key)
        if not action or not self.ensure_ready(action):
            return False
        if self.process_manager.is_team_running(team_key):
            self._log_error(
                ErrorCode.TEAM_WATCH_ALREADY_RUNNING,
                "이미 팀 감시 워커가 실행 중입니다. 중복 시작은 무시합니다.\n",
                level="WARN",
                category=team_key,
            )
            return False
        self.state.set_team_watch_enabled(team_key, True)
        self.state.set_stage_status(team_key, "감시중")
        command = self.command_builder(action)
        self._log(f"워커 실행: {' '.join(command)}\n", category=team_key)
        try:
            started = self.process_manager.start_team(
                team_key,
                command,
                on_line=lambda line: self._log(line, category=team_key),
                on_done=lambda code: self._handle_team_done(team_key, code),
            )
            if started:
                self._team_started_at[team_key] = time.time()
                notify_job_started(self._team_label(team_key))
            return started
        except AppError as exc:
            self._log_error(exc.code, f"워커 실행 실패: {exc.message}\n", category=team_key)
            notify_critical_error(f"ActionRunner.start_team_watch.{team_key}", exc.message)
            self.state.set_stage_status(team_key, "실패")
            return False
        except Exception as exc:
            self._log(f"워커 실행 실패: {exc}\n", level="ERROR", category=team_key)
            notify_critical_error(f"ActionRunner.start_team_watch.{team_key}", exc)
            self.state.set_stage_status(team_key, "실패")
            return False

    def stop_team_watch(self, team_key: str) -> None:
        self.state.set_team_watch_enabled(team_key, False)
        notify_emergency_stop(f"{self._team_label(team_key)} 중지 요청")
        try:
            self.process_manager.stop_team(team_key)
        except AppError as exc:
            self._log_error(exc.code, f"팀 감시 중지 실패: {exc.message}\n", category=team_key)
        self.state.set_stage_status(team_key, "대기")
        self._log("팀 감시 중지\n", category=team_key)

    def stop_all(self) -> None:
        notify_emergency_stop("전체 작업 중지 요청")
        try:
            self.process_manager.stop()
            self.process_manager.stop_all_teams()
        except AppError as exc:
            self._log_error(exc.code, f"전체 중지 실패: {exc.message}\n", category="process")

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
        job_name = self._job_name or self._job_label(self.state.current_action)
        duration = max(0, time.time() - self._job_started_at) if self._job_started_at else 0
        notify_job_finished(job_name, 1 if success else 0, 0 if success else 1, duration)
        if not success:
            notify_critical_error(job_name, f"작업이 비정상 종료되었습니다. code={return_code}")
        self.state.record_process_done(success)
        self.state.mark_current_stage_done(success)
        current_stage = self.state.current_stage_key
        if current_stage and self.state.team_watch_enabled.get(current_stage, False):
            self.state.set_stage_status(current_stage, "감시중")
        self.state.set_current_action("", "")
        self.state.set_status("대기중")
        self._job_started_at = 0.0
        self._job_name = ""

    def _handle_team_done(self, team_key: str, return_code: int) -> None:
        self._log(f"워커 종료 (code: {return_code})\n", category=team_key)
        duration = max(0, time.time() - self._team_started_at.pop(team_key, 0))
        success = return_code == 0
        notify_job_finished(self._team_label(team_key), 1 if success else 0, 0 if success else 1, duration)
        if not success:
            notify_critical_error(self._team_label(team_key), f"워커가 비정상 종료되었습니다. code={return_code}")
        enabled = self.state.team_watch_enabled.get(team_key, False)
        policy = self.pipeline_service.watch_policy
        if policy.should_count_failure(return_code, enabled):
            failure_count = self.state.record_team_watch_failure(team_key)
            self._log(f"팀 감시 실패 누적: {failure_count}/{policy.max_failures_before_pause}\n", level="WARN", category=team_key)
            if policy.should_pause_after_failure(failure_count):
                self.state.set_team_watch_enabled(team_key, False)
                self.state.set_stage_status(team_key, "실패")
                self._log_error(
                    ErrorCode.TEAM_WATCH_FAILURE_LIMIT,
                    "실패 누적 한도에 도달해 팀 감시를 일시 중지합니다.\n",
                    category=team_key,
                )
                return
        elif return_code == 0:
            self.state.reset_team_watch_failures(team_key)
        self.state.set_stage_status(team_key, self.pipeline_service.team_done_status(enabled))

    def _log(self, message: str, *, level: str = "INFO", category: str = "runner") -> None:
        self.logger.log(LogEvent(level=level, category=category, message=message))

    def _log_error(self, code: ErrorCode, message: str, *, level: str = "ERROR", category: str = "runner") -> None:
        self.logger.log(LogEvent(level=level, category=category, message=f"[{code.value}] {message}"))

    def _job_label(self, action: str) -> str:
        return {
            "install": "필수 설치",
            "run": "정찰",
            "collect-listings": "목록 수집",
            "watch": "정찰 감시",
            "watch-images": "이미지 감시",
            "watch-thumbnails": "썸네일 감시",
            "watch-upload": "BUYMA 업로드 감시",
            "save-images": "이미지 저장",
            "upload-review": "BUYMA 업로드 검토",
            "upload-auto": "BUYMA 업로드",
        }.get(action, action or "Auto Shop 작업")

    def _team_label(self, team_key: str) -> str:
        return {
            "assets": "이미지 감시",
            "design": "썸네일 감시",
            "sales": "BUYMA 업로드 감시",
        }.get(team_key, team_key)
