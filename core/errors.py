"""Common application exceptions and error codes."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    ACTION_ALREADY_RUNNING = "ACTION_ALREADY_RUNNING"
    ACTION_NOT_READY = "ACTION_NOT_READY"
    ACTION_UNKNOWN = "ACTION_UNKNOWN"
    PROCESS_START_FAILED = "PROCESS_START_FAILED"
    PROCESS_STOP_FAILED = "PROCESS_STOP_FAILED"
    TEAM_WATCH_ALREADY_RUNNING = "TEAM_WATCH_ALREADY_RUNNING"
    TEAM_WATCH_FAILURE_LIMIT = "TEAM_WATCH_FAILURE_LIMIT"
    SNAPSHOT_IO_FAILED = "SNAPSHOT_IO_FAILED"
    LOG_WRITE_FAILED = "LOG_WRITE_FAILED"


class AppError(Exception):
    """Base error with a stable code for UI/log/reporting layers."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"


class ProcessStartError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PROCESS_START_FAILED, message)


class ProcessStopError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PROCESS_STOP_FAILED, message)
