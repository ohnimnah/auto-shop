"""Central state and event streams for the launcher."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List


@dataclass(frozen=True)
class LogEvent:
    """Structured log record emitted by core services."""

    level: str
    category: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)

    def format(self) -> str:
        message = self.message
        if message.startswith("\n"):
            return message
        return f"[{self.timestamp:%H:%M:%S}] [{self.level}] [{self.category}] {message}"


@dataclass(frozen=True)
class AppStateChange:
    """Small state diff sent to UI subscribers."""

    key: str
    value: object


LogSubscriber = Callable[[LogEvent], None]
StateSubscriber = Callable[[AppStateChange], None]


class AppLogger:
    """Small pub/sub logger independent from Tk widgets."""

    def __init__(self) -> None:
        self._subscribers: List[LogSubscriber] = []

    def subscribe(self, callback: LogSubscriber) -> None:
        self._subscribers.append(callback)

    def log(self, event: LogEvent) -> None:
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                pass

    def emit(self, message: str, *, level: str = "INFO", category: str = "app") -> None:
        self.log(LogEvent(level=level, category=category, message=message))


@dataclass
class DashboardMetrics:
    total: int = 1248
    running: int = 8
    waiting: int = 23
    done: int = 1172
    error: int = 45


@dataclass
class PipelineStep:
    key: str
    title: str
    metric: str
    ratio: float
    color_key: str


@dataclass
class ProductRow:
    no: str
    state: str
    name: str
    brand: str
    category: str
    price: str
    sheet: str
    updated: str
    action: str


@dataclass
class AppState:
    """Single source of truth for UI-visible launcher state."""

    current_action: str = ""
    current_stage_key: str = ""
    status_text: str = "대기중"
    pipeline_status: Dict[str, str] = field(
        default_factory=lambda: {
            "scout": "대기",
            "assets": "대기",
            "design": "대기",
            "sales": "대기",
        }
    )
    team_watch_enabled: Dict[str, bool] = field(
        default_factory=lambda: {
            "assets": False,
            "design": False,
            "sales": False,
        }
    )
    system_status: Dict[str, str] = field(
        default_factory=lambda: {
            "sheet": "점검 전",
            "credentials": "점검 전",
            "buyma": "점검 전",
            "images": "점검 전",
            "runtime": "점검 전",
            "last_check": "--:--:--",
        }
    )
    metrics: DashboardMetrics = field(default_factory=DashboardMetrics)
    today_processed: int = 0
    today_success: int = 0
    today_fail: int = 0
    team_watch_failures: Dict[str, int] = field(
        default_factory=lambda: {
            "assets": 0,
            "design": 0,
            "sales": 0,
        }
    )
    pipeline_steps: List[PipelineStep] = field(
        default_factory=lambda: [
            PipelineStep("scout", "정찰", "142 / 156", 0.91, "blue"),
            PipelineStep("assets", "이미지 저장", "128 / 142", 0.90, "green"),
            PipelineStep("design", "썸네일 생성", "115 / 128", 0.89, "purple"),
            PipelineStep("review", "업로드 대기", "47 / 115", 0.41, "yellow"),
            PipelineStep("sales", "업로드 중", "8 / 47", 0.17, "orange"),
            PipelineStep("done", "출품 완료", "1,172", 1.0, "green"),
        ]
    )
    product_rows: List[ProductRow] = field(
        default_factory=lambda: [
            ProductRow("1248", "업로드 중", "MAISON KITSUNE 더블 폭스 헤드 맨투맨 (블랙)", "MAISON KITSUNE", "맨투맨", "29,800", "collection", "14:30:21", "실행 / 열기"),
            ProductRow("1247", "썸네일 완료", "AMI 하트 로고 스웨트 셔츠 (네이비)", "AMI", "맨투맨", "31,500", "collection", "14:30:18", "실행 / 열기"),
            ProductRow("1246", "출품 완료", "STONE ISLAND 와펜 후드티 (블랙)", "STONE ISLAND", "후드티", "45,000", "collection", "14:30:10", "실행 / 열기"),
            ProductRow("1245", "업로드 실패", "MONCLER 패딩 자켓 (네이비)", "MONCLER", "패딩", "158,000", "collection", "14:30:07", "재실행 / 열기"),
            ProductRow("1244", "이미지저장 중", "CP COMPANY 고글 후드 (그레이)", "CP COMPANY", "후드티", "42,000", "collection", "14:30:03", "실행 / 열기"),
        ]
    )
    _subscribers: List[StateSubscriber] = field(default_factory=list, init=False, repr=False)

    def subscribe(self, callback: StateSubscriber) -> None:
        self._subscribers.append(callback)

    def notify(self, key: str, value: object) -> None:
        change = AppStateChange(key=key, value=value)
        for callback in list(self._subscribers):
            callback(change)

    def set_status(self, text: str) -> None:
        if self.status_text == text:
            return
        self.status_text = text
        self.notify("status_text", text)

    def set_current_action(self, action: str, stage_key: str = "") -> None:
        changed_action = self.current_action != action
        changed_stage = self.current_stage_key != stage_key
        self.current_action = action
        self.current_stage_key = stage_key
        if changed_action:
            self.notify("current_action", action)
        if changed_stage:
            self.notify("current_stage_key", stage_key)

    def set_stage_status(self, key: str, text: str) -> None:
        if not key or self.pipeline_status.get(key) == text:
            return
        self.pipeline_status[key] = text
        self.notify(f"pipeline_status.{key}", text)

    def set_team_watch_enabled(self, key: str, enabled: bool) -> None:
        if self.team_watch_enabled.get(key) == enabled:
            return
        self.team_watch_enabled[key] = enabled
        self.notify(f"team_watch_enabled.{key}", enabled)

    def reset_stage_statuses(self) -> None:
        for key in self.pipeline_status:
            self.set_stage_status(key, "감시중" if self.team_watch_enabled.get(key, False) else "대기")
        if self.current_stage_key:
            self.current_stage_key = ""
            self.notify("current_stage_key", "")

    def mark_current_stage_done(self, success: bool) -> None:
        if self.current_stage_key:
            self.set_stage_status(self.current_stage_key, "완료" if success else "실패")

    def record_process_done(self, success: bool) -> None:
        self.today_processed += 1
        self.notify("today_processed", self.today_processed)
        if success:
            self.today_success += 1
            self.notify("today_success", self.today_success)
        else:
            self.today_fail += 1
            self.notify("today_fail", self.today_fail)

    def record_team_watch_failure(self, key: str) -> int:
        count = self.team_watch_failures.get(key, 0) + 1
        self.team_watch_failures[key] = count
        self.notify(f"team_watch_failures.{key}", count)
        return count

    def reset_team_watch_failures(self, key: str) -> None:
        if self.team_watch_failures.get(key, 0) == 0:
            return
        self.team_watch_failures[key] = 0
        self.notify(f"team_watch_failures.{key}", 0)

    def set_system_status(self, values: Dict[str, str]) -> None:
        for key, value in values.items():
            if self.system_status.get(key) == value:
                continue
            self.system_status[key] = value
            self.notify(f"system_status.{key}", value)

    def to_snapshot(self) -> dict:
        """Return a minimal restart snapshot without transient subprocess state."""
        return {
            "status_text": self.status_text,
            "pipeline_status": dict(self.pipeline_status),
            "team_watch_enabled": dict(self.team_watch_enabled),
            "team_watch_failures": dict(self.team_watch_failures),
            "system_status": dict(self.system_status),
            "today_processed": self.today_processed,
            "today_success": self.today_success,
            "today_fail": self.today_fail,
        }

    def apply_snapshot(self, data: dict) -> None:
        """Restore minimal state silently during startup."""
        if not isinstance(data, dict):
            return
        if isinstance(data.get("pipeline_status"), dict):
            self.pipeline_status.update({str(k): str(v) for k, v in data["pipeline_status"].items()})
        if isinstance(data.get("team_watch_enabled"), dict):
            self.team_watch_enabled.update({str(k): bool(v) for k, v in data["team_watch_enabled"].items()})
        if isinstance(data.get("team_watch_failures"), dict):
            self.team_watch_failures.update({str(k): int(v) for k, v in data["team_watch_failures"].items() if str(v).isdigit()})
        if isinstance(data.get("system_status"), dict):
            self.system_status.update({str(k): str(v) for k, v in data["system_status"].items()})
        self.today_processed = int(data.get("today_processed") or 0)
        self.today_success = int(data.get("today_success") or 0)
        self.today_fail = int(data.get("today_fail") or 0)
        self.status_text = str(data.get("status_text") or "대기중")
        self.current_action = ""
        self.current_stage_key = ""
