import os
import queue
import random
import re
import json
import base64
import shutil
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog
from tkinter import messagebox
from tkinter import simpledialog
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk

from core.action_runner import ActionRunner
from core.command_builder import CommandBuilder
from core.process_manager import ProcessManager, build_default_env
from app.security import KeyringTokenStore
from config.config_service import load_config as load_profile_config
from services.buyma_service import BuymaCredentialService
from services.dashboard_data_service import DashboardDataService
from services.log_store import FileLogWriter
from services.system_checker import SystemChecker
from state.app_state import AppLogger, AppState, AppStateChange, LogEvent
from state.snapshot_store import StateSnapshotStore
from ui.components import ColorButton
from ui.pages.automation_page import AutomationPage
from ui.pages.buyma_upload_page import BuymaUploadPage
from ui.pages.dashboard_page import DashboardPage
from ui.pages.image_thumbnail_page import ImageThumbnailPage
from ui.pages.scout_page import ScoutPage
from ui.pages.settings_page import SettingsPage
from ui.sidebar import NAV_ITEMS, SHORTCUTS
from ui.theme import CONTENT_PAD_X, CONTENT_PAD_Y, KPI_CARD_HEIGHT


SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROFILE_NAME = "default"
PROFILE_CONFIG_FILENAME = "launcher_profile.json"
DEFAULT_THUMBNAIL_FOOTER_SUFFIX = "angduss k-closet"


def resolve_python_executable() -> str:
    """Prefer project virtualenv python, fall back to current interpreter."""
    windows_python = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "python.exe")
    mac_python = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")

    if os.path.isfile(windows_python):
        return windows_python
    if os.path.isfile(mac_python):
        return mac_python
    return sys.executable


def get_runtime_root_dir() -> str:
    """Return the root runtime data directory for the current OS."""
    local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
    if local_app_data:
        return os.path.join(local_app_data, 'auto_shop')
    return os.path.join(os.path.expanduser('~'), '.auto_shop')


def sanitize_profile_name(raw_value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", (raw_value or "").strip()).strip("-._")
    return value or DEFAULT_PROFILE_NAME


def get_saved_profile_name() -> str:
    env_profile = os.environ.get("AUTO_SHOP_PROFILE", "").strip()
    if env_profile:
        return sanitize_profile_name(env_profile)
    root_dir = get_runtime_root_dir()
    config_path = os.path.join(root_dir, PROFILE_CONFIG_FILENAME)
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return sanitize_profile_name(str(data.get("active_profile") or DEFAULT_PROFILE_NAME))
    except Exception:
        pass
    return DEFAULT_PROFILE_NAME


def save_profile_name(profile_name: str) -> None:
    root_dir = get_runtime_root_dir()
    os.makedirs(root_dir, exist_ok=True)
    config_path = os.path.join(root_dir, PROFILE_CONFIG_FILENAME)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"active_profile": sanitize_profile_name(profile_name)}, f, ensure_ascii=False, indent=2)


def get_default_data_dir(profile_name: str | None = None) -> str:
    """Return the runtime data directory for the active profile."""
    root_dir = get_runtime_root_dir()
    profile = sanitize_profile_name(profile_name or get_saved_profile_name())
    if profile == DEFAULT_PROFILE_NAME:
        return root_dir
    return os.path.join(root_dir, "profiles", profile)


def get_default_images_dir(profile_name: str | None = None) -> str:
    """Return the default image storage directory."""
    env_images_dir = os.environ.get('AUTO_SHOP_IMAGES_DIR', '').strip()
    if env_images_dir:
        return os.path.abspath(os.path.expanduser(env_images_dir))
    cfg_path = os.path.join(get_default_data_dir(profile_name), "sheets_config.json")
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg, dict):
                saved_images_dir = (cfg.get("images_dir") or "").strip()
                if saved_images_dir:
                    return os.path.abspath(os.path.expanduser(saved_images_dir))
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'images')


class AutoShopLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("auto_shop launcher")
        self.geometry("1360x780")
        self.minsize(1180, 640)
        self._icon_image: tk.PhotoImage | None = None
        self._set_window_icon()

        self.log_queue: queue.Queue[LogEvent] = queue.Queue()
        self.state_queue: queue.Queue[AppStateChange] = queue.Queue()
        self.profile_name = get_saved_profile_name()
        self.profile_config = load_profile_config(self.profile_name, create_if_missing=True)
        self.data_dir = get_default_data_dir(self.profile_name)
        self.sheet_config_path = os.path.join(self.data_dir, "sheets_config.json")
        self.state = AppState()
        self.snapshot_store = StateSnapshotStore(os.path.join(self.data_dir, "launcher_state_snapshot.json"))
        self.snapshot_store.load_into(self.state)
        self.logger = AppLogger()
        self.file_log_writer = FileLogWriter(self._get_configured_log_dir)
        self.system_checker = SystemChecker(
            script_dir=SCRIPT_DIR,
            data_dir=self.data_dir,
            sheet_config_path=self.sheet_config_path,
            resolve_python_executable=resolve_python_executable,
            get_images_dir=self._get_configured_images_dir,
        )
        self.buyma_credentials = BuymaCredentialService(self.system_checker.get_buyma_credentials_target_path())
        self.telegram_token_store = KeyringTokenStore(
            service_name="auto_shop.telegram",
            account_key=f"{self.profile_name}.bot_token",
        )
        self.command_builder = CommandBuilder(
            script_dir=SCRIPT_DIR,
            resolve_python_executable=resolve_python_executable,
            load_sheet_config=self.system_checker.load_sheet_config,
        )
        self.process_manager = ProcessManager(
            cwd=SCRIPT_DIR,
            env_factory=lambda: build_default_env(
                self.data_dir,
                self._get_configured_images_dir(),
                self.profile_name,
                thumbnail_blur_faces=self._get_thumbnail_blur_faces_enabled(),
            ),
        )
        self.action_runner = ActionRunner(
            script_dir=SCRIPT_DIR,
            state=self.state,
            logger=self.logger,
            process_manager=self.process_manager,
            command_builder=self.command_builder.build,
            ensure_ready=self._ensure_sheet_config_before_action,
        )
        self.dashboard_data = DashboardDataService(
            data_dir=self.data_dir,
            script_dir=SCRIPT_DIR,
            state=self.state,
            process_manager=self.process_manager,
            system_checker=self.system_checker,
            pipeline_service=self.action_runner.pipeline_service,
            get_log_dir=self._get_configured_log_dir,
        )
        self.logger.subscribe(self._enqueue_log)
        self.logger.subscribe(self.file_log_writer.handle)
        self.logger.subscribe(self.dashboard_data.update_state_from_log)
        self.state.subscribe(self._enqueue_state)
        self.state.subscribe(self.dashboard_data.update_state_from_change)
        self.state.subscribe(lambda change: self.snapshot_store.handle_change(self.state, change))
        self.today_processed = 0
        self.today_success = 0
        self.today_fail = 0
        self.today_processed_var = tk.StringVar(value="0")
        self.today_success_var = tk.StringVar(value="0")
        self.today_fail_var = tk.StringVar(value="0")
        self.kpi_total_var = tk.StringVar(value=f"{self.state.metrics.total:,}")
        self.kpi_running_var = tk.StringVar(value=f"{self.state.metrics.running:,}")
        self.kpi_waiting_var = tk.StringVar(value=f"{self.state.metrics.waiting:,}")
        self.kpi_done_var = tk.StringVar(value=f"{self.state.metrics.done:,}")
        self.kpi_error_var = tk.StringVar(value=f"{self.state.metrics.error:,}")
        self.kpi_total_sub_var = tk.StringVar(value="데이터 동기화 대기")
        self.kpi_running_sub_var = tk.StringVar(value="실행 중인 작업 없음")
        self.kpi_waiting_sub_var = tk.StringVar(value="대기 상품 없음")
        self.kpi_done_sub_var = tk.StringVar(value="오늘 완료 없음")
        self.kpi_error_sub_var = tk.StringVar(value="오류 없음")
        self.data_source_var = tk.StringVar(value=self.state.data_source.label)
        self.last_sync_var = tk.StringVar(value=f"마지막 동기화 {self.state.data_source.last_sync}")
        self.data_source_detail_var = tk.StringVar(value=self.state.data_source.detail)
        self.auto_refresh_var = tk.BooleanVar(value=False)
        self.auto_refresh_job: str | None = None
        self.product_filter_state_var = tk.StringVar(value="전체 상태")
        self.product_filter_category_var = tk.StringVar(value="전체 카테고리")
        self.product_filter_search_var = tk.StringVar(value="")
        self.summary_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.summary_done_var = tk.StringVar(value="0건")
        self.summary_running_var = tk.StringVar(value="0건")
        self.summary_waiting_var = tk.StringVar(value="0건")
        self.summary_error_var = tk.StringVar(value="0건")
        self.clock_var = tk.StringVar(value="")
        self.sheet_status_var = tk.StringVar(value=self.state.system_status.get("sheet", "점검 전"))
        self.credentials_status_var = tk.StringVar(value=self.state.system_status.get("credentials", "점검 전"))
        self.buyma_status_var = tk.StringVar(value=self.state.system_status.get("buyma", "점검 전"))
        self.images_status_var = tk.StringVar(value=self.state.system_status.get("images", "점검 전"))
        self.runtime_status_var = tk.StringVar(value=self.state.system_status.get("runtime", "점검 전"))
        self.last_check_var = tk.StringVar(value=self.state.system_status.get("last_check", "--:--:--"))
        self.pipeline_progress_vars: dict[str, tk.StringVar] = {}
        self.pipeline_canvas_widgets: dict[str, tk.Canvas] = {}
        self.pipeline_ratios: dict[str, float] = {}
        self.pipeline_colors: dict[str, str] = {}
        self.quick_action_buttons: list[ColorButton] = []
        self.nav_buttons: dict[str, tk.Label] = {}
        self.page_container: tk.Frame | None = None
        self.current_page: tk.Frame | None = None
        self.pages: dict[str, tk.Frame] = {}
        self.page_classes: dict[str, type[tk.Frame]] = {}
        self.current_page_name: str = self.state.active_view
        self.log_history: list[str] = []
        self.wizard_summary_var = tk.StringVar(value="첫 실행 준비를 확인하세요.")
        self.wizard_status_vars: dict[str, tk.StringVar] = {
            "runtime": tk.StringVar(value="확인 전"),
            "credentials": tk.StringVar(value="확인 전"),
            "sheet": tk.StringVar(value="확인 전"),
            "mosaic": tk.StringVar(value="확인 전"),
            "buyma": tk.StringVar(value="확인 전"),
        }
        self.stage_vars: dict[str, tk.StringVar] = {
            "scout": tk.StringVar(value=self.state.pipeline_status["scout"]),
            "assets": tk.StringVar(value=self.state.pipeline_status["assets"]),
            "design": tk.StringVar(value=self.state.pipeline_status["design"]),
            "sales": tk.StringVar(value=self.state.pipeline_status["sales"]),
        }
        self.stage_card_widgets: dict[str, tk.Widget] = {}
        self.action_bubble: tk.Toplevel | None = None
        self.team_watch_actions = self.action_runner.team_watch_actions
        self.team_watch_enabled = self.state.team_watch_enabled
        self.team_watch_jobs: dict[str, str] = {}

        self._build_ui()
        self._refresh_action_button_labels()
        self.after(100, self._drain_log_queue)
        self.after(100, self._drain_state_queue)
        # Defer heavy data sync so window renders first.
        self.after(300, self.refresh_dashboard_data)
        self.after(250, self._ensure_sheet_config_on_startup)

    def _enqueue_log(self, event: LogEvent) -> None:
        self.log_queue.put(event)

    def _enqueue_state(self, change: AppStateChange) -> None:
        self.state_queue.put(change)

    def _render_state_change(self, change: AppStateChange) -> None:
        key = change.key
        value = change.value
        if key == "status_text" and hasattr(self, "status_var"):
            self.status_var.set(str(value))
        elif key == "current_action" and hasattr(self, "run_btn"):
            # Queue delivery can be slightly out-of-order; always reflect latest state.
            self._set_running_ui(bool(self.state.current_action))
            self._refresh_action_button_labels()
            if not self.state.current_action:
                # Action completion: immediately resync overview tables/cards.
                self.refresh_dashboard_data()
        elif key == "today_processed":
            self.today_processed_var.set(str(value))
        elif key == "today_success":
            self.today_success_var.set(str(value))
        elif key == "today_fail":
            self.today_fail_var.set(str(value))
        elif key == "metrics":
            self._render_metrics()
        elif key == "pipeline_steps":
            self._render_pipeline_steps()
        elif key == "product_rows":
            self._refresh_product_table()
        elif key == "data_source":
            self._render_data_source()
        elif key == "active_view":
            self._show_active_page(str(value))
        elif key.startswith("system_status."):
            self._render_system_status(key.split(".", 1)[1], str(value))
        elif key.startswith("pipeline_status."):
            stage_key = key.split(".", 1)[1]
            text = str(value)
            var = self.stage_vars.get(stage_key)
            if var is not None:
                var.set(text)
            self._sync_pipeline_badge(stage_key, text)

    def _render_system_status(self, key: str, value: str) -> None:
        target_vars = {
            "sheet": self.sheet_status_var,
            "credentials": self.credentials_status_var,
            "buyma": self.buyma_status_var,
            "images": self.images_status_var,
            "runtime": self.runtime_status_var,
            "last_check": self.last_check_var,
        }
        var = target_vars.get(key)
        if var is not None:
            var.set(value)

    def _render_metrics(self) -> None:
        self.kpi_total_var.set(f"{self.state.metrics.total:,}")
        self.kpi_running_var.set(f"{self.state.metrics.running:,}")
        self.kpi_waiting_var.set(f"{self.state.metrics.waiting:,}")
        self.kpi_done_var.set(f"{self.state.metrics.done:,}")
        self.kpi_error_var.set(f"{self.state.metrics.error:,}")
        self.kpi_total_sub_var.set("동기화된 전체 상품" if self.state.metrics.total else "연결된 상품 데이터 없음")
        self.kpi_running_sub_var.set("현재 처리 중" if self.state.metrics.running else "실행 중인 작업 없음")
        self.kpi_waiting_sub_var.set("다음 처리 대기" if self.state.metrics.waiting else "대기 상품 없음")
        self.kpi_done_sub_var.set("오늘 정상 완료" if self.state.metrics.done else "오늘 완료 없음")
        self.kpi_error_sub_var.set("확인 필요한 항목" if self.state.metrics.error else "오류 없음")
        total = max(1, self.state.metrics.done + self.state.metrics.running + self.state.metrics.waiting + self.state.metrics.error)
        self.summary_date_var.set(datetime.now().strftime("%Y-%m-%d"))
        self.summary_done_var.set(f"{self.state.metrics.done:,}건 ({self.state.metrics.done * 100 // total}%)")
        self.summary_running_var.set(f"{self.state.metrics.running:,}건 ({self.state.metrics.running * 100 // total}%)")
        self.summary_waiting_var.set(f"{self.state.metrics.waiting:,}건 ({self.state.metrics.waiting * 100 // total}%)")
        self.summary_error_var.set(f"{self.state.metrics.error:,}건 ({self.state.metrics.error * 100 // total}%)")
        self._draw_summary_donut()

    def _render_data_source(self) -> None:
        self.data_source_var.set(self.state.data_source.label)
        self.last_sync_var.set(f"마지막 동기화 {self.state.data_source.last_sync}")
        self.data_source_detail_var.set(self.state.data_source.detail)
        if hasattr(self, "empty_products_label") and self.empty_products_label.winfo_exists() and not self.state.product_rows:
            self.empty_products_label.configure(text=self.state.data_source.detail or "표시할 상품이 없습니다.")
            self.empty_products_label.grid()

    def _render_pipeline_steps(self) -> None:
        for step in self.state.pipeline_steps:
            var = self.pipeline_progress_vars.get(step.key)
            if var is not None:
                var.set(f"{step.metric}    {int(step.ratio * 100)}%")
            self.pipeline_ratios[step.key] = step.ratio
            color = self.theme.get(step.color_key, self.theme["blue"]) if hasattr(self, "theme") else "#2563eb"
            self.pipeline_colors[step.key] = color
            self._draw_progress(step.key, step.ratio, color)

    def _populate_log_widget(self) -> None:
        if not hasattr(self, "log") or not self.log.winfo_exists():
            return
        self.log.delete("1.0", tk.END)
        for line in self.log_history:
            self.log.insert(tk.END, line)
        self.log.see(tk.END)

    def _set_window_icon(self) -> None:
        """Create and apply a simple built-in icon without external files."""
        icon = tk.PhotoImage(width=32, height=32)
        icon.put("#111111", to=(0, 0, 31, 31))
        icon.put("#1f7aec", to=(3, 3, 28, 28))
        icon.put("#ffffff", to=(8, 8, 23, 23))
        icon.put("#1f7aec", to=(12, 12, 19, 19))
        self.iconphoto(True, icon)
        self._icon_image = icon

    def _build_ui(self) -> None:
        self.theme = {
            "bg": "#07111f",
            "sidebar": "#0b1728",
            "panel": "#0f1c2e",
            "panel_2": "#122238",
            "panel_3": "#172a45",
            "line": "#223755",
            "muted": "#8da3bd",
            "text": "#f4f8ff",
            "blue": "#2563eb",
            "blue_2": "#1d4ed8",
            "green": "#22c55e",
            "yellow": "#f59e0b",
            "red": "#ef4444",
            "purple": "#8b5cf6",
            "orange": "#d97706",
        }
        self.configure(bg=self.theme["bg"])
        self.title("물류 자동화 런처 - 운영 대시보드")
        self.geometry("1500x860")
        self.minsize(1280, 740)
        self.status_var = tk.StringVar(value=self.state.status_text)
        self._configure_tree_style()

        root = tk.Frame(self, bg=self.theme["bg"])
        root.pack(fill=tk.BOTH, expand=True)
        root.grid_columnconfigure(0, minsize=240)
        root.grid_columnconfigure(1, weight=1)
        root.grid_columnconfigure(2, minsize=300)
        root.grid_rowconfigure(0, weight=1)
        self.root_shell = root

        sidebar = tk.Frame(root, bg=self.theme["sidebar"], padx=12, pady=14, highlightbackground=self.theme["line"], highlightthickness=1)
        content = tk.Frame(root, bg=self.theme["bg"], padx=CONTENT_PAD_X, pady=CONTENT_PAD_Y)
        right_panel = tk.Frame(root, bg=self.theme["bg"], padx=0, pady=CONTENT_PAD_Y)
        self.content_frame = content
        self.right_panel_frame = right_panel
        sidebar.grid(row=0, column=0, sticky="nsew")
        content.grid(row=0, column=1, sticky="nsew")
        right_panel.grid(row=0, column=2, sticky="nsew", padx=(0, 18))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(0, weight=1)

        self._build_sidebar(sidebar)
        self.page_container = tk.Frame(content, bg=self.theme["bg"])
        self.page_container.grid(row=0, column=0, sticky="nsew")
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)
        self.right_panel_container = tk.Frame(right_panel, bg=self.theme["bg"])
        self.right_panel_container.grid(row=0, column=0, sticky="nsew")
        self.right_panel_container.grid_rowconfigure(0, weight=1)
        self.right_panel_container.grid_columnconfigure(0, weight=1)
        self._build_pages()
        self._show_active_page(self.state.active_view)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._refresh_system_status_labels()
        self._render_metrics()
        self._update_clock()

    def _configure_tree_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Ops.Treeview",
            background="#0d1a2c",
            fieldbackground="#0d1a2c",
            foreground="#e6eefb",
            bordercolor="#223755",
            rowheight=31,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Ops.Treeview.Heading",
            background="#14243b",
            foreground="#aabbd0",
            bordercolor="#223755",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Ops.Treeview", background=[("selected", "#1d4ed8")], foreground=[("selected", "#ffffff")])

    def _build_sidebar(self, parent: tk.Frame) -> None:
        brand = tk.Frame(parent, bg=self.theme["sidebar"])
        brand.pack(fill=tk.X, pady=(0, 18))
        icon = tk.Canvas(brand, width=38, height=38, bg=self.theme["sidebar"], highlightthickness=0)
        icon.pack(side=tk.LEFT, padx=(0, 8))
        icon.create_rectangle(8, 7, 30, 29, fill="#13263d", outline="#6b86a7", width=2)
        icon.create_line(8, 7, 19, 1, 30, 7, fill="#b8c7dc", width=2)
        icon.create_line(19, 1, 19, 24, fill="#6b86a7", width=2)
        title = tk.Frame(brand, bg=self.theme["sidebar"])
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(title, text="물류 자동화 런처", bg=self.theme["sidebar"], fg=self.theme["text"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(title, text="관제실 · 관리자 페이지", bg=self.theme["sidebar"], fg=self.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w")

        nav = tk.Frame(parent, bg=self.theme["sidebar"])
        nav.pack(fill=tk.X)
        for label, _active in NAV_ITEMS:
            self._sidebar_button(nav, label, self.state.active_view == label, lambda name=label: self.on_menu_click(name))

        quick = self._card(parent, "빠른 바로가기", pady=(18, 0))
        for label, action, color_key in SHORTCUTS:
            if action == "stop":
                command = self.stop_action
            elif action == "logs":
                command = self._show_log_folder_hint
            elif action == "images-dir":
                command = self.configure_images_directory
            else:
                command = lambda action_name=action: self.run_action(action_name)
            color = "#334155" if color_key == "neutral" else self.theme[color_key]
            self._link_button(quick, label, command, color)
            if action == "stop":
                tk.Frame(quick, height=1, bg=self.theme["line"]).pack(fill=tk.X, pady=10)

        state = self._card(parent, "프로그램 상태", pady=(18, 0))
        dot_row = tk.Frame(state, bg=self.theme["panel"])
        dot_row.pack(fill=tk.X, pady=(4, 8))
        tk.Label(dot_row, text="●", bg=self.theme["panel"], fg=self.theme["green"], font=("Segoe UI", 14)).pack(side=tk.LEFT)
        tk.Label(dot_row, textvariable=self.status_var, bg=self.theme["panel"], fg=self.theme["text"], font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(state, text="런처가 정상적으로 실행 중입니다.", bg=self.theme["panel"], fg=self.theme["muted"], font=("Segoe UI", 8), wraplength=170, justify=tk.LEFT).pack(anchor="w")

    def _build_topbar(self, parent: tk.Frame) -> None:
        top = tk.Frame(parent, bg=self.theme["bg"])
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top.grid_columnconfigure(0, weight=1)
        tk.Label(top, text="대시보드", bg=self.theme["bg"], fg=self.theme["text"], font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(top, text="전체 자동화 시스템의 실시간 현황을 확인할 수 있습니다.", bg=self.theme["bg"], fg=self.theme["muted"], font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(top, textvariable=self.data_source_var, bg="#102033", fg="#93c5fd", font=("Segoe UI", 8, "bold"), padx=10, pady=4).grid(row=0, column=1, sticky="e", padx=(0, 8))
        tk.Label(top, textvariable=self.last_sync_var, bg=self.theme["bg"], fg="#c7d2e4", font=("Segoe UI", 8)).grid(row=0, column=2, sticky="e", padx=(0, 18))
        tk.Label(top, textvariable=self.clock_var, bg=self.theme["bg"], fg="#c7d2e4", font=("Segoe UI", 9)).grid(row=0, column=3, sticky="e")
        tk.Label(top, textvariable=self.data_source_detail_var, bg=self.theme["bg"], fg=self.theme["muted"], font=("Segoe UI", 8)).grid(row=1, column=1, columnspan=3, sticky="e")

    def _build_kpi_section(self, parent: tk.Frame) -> None:
        wrap = tk.Frame(parent, bg=self.theme["bg"])
        wrap.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for idx in range(5):
            wrap.grid_columnconfigure(idx, weight=1)
        cards = [
            ("전체 상품", self.kpi_total_var, self.kpi_total_sub_var, self.theme["blue"]),
            ("진행 중", self.kpi_running_var, self.kpi_running_sub_var, self.theme["green"]),
            ("대기 중", self.kpi_waiting_var, self.kpi_waiting_sub_var, self.theme["yellow"]),
            ("완료", self.kpi_done_var, self.kpi_done_sub_var, self.theme["green"]),
            ("오류 / 보류", self.kpi_error_var, self.kpi_error_sub_var, self.theme["red"]),
        ]
        for col, (title, value_var, sub, accent) in enumerate(cards):
            self._kpi_card(wrap, col, title, value_var, sub, accent)

    def _build_pipeline_section(self, parent: tk.Frame) -> None:
        card = self._grid_card(parent, "파이프라인 진행 현황", row=2, pady=(0, 12))
        steps = list(self.state.pipeline_steps)
        if not steps:
            steps = self.dashboard_data.build_pipeline_from_runtime(self.state.product_rows)
        for idx in range(len(steps)):
            card.grid_columnconfigure(idx, weight=1, uniform="pipeline")
        card.grid_rowconfigure(0, weight=1)
        for idx, step in enumerate(steps):
            self._pipeline_step(card, idx, len(steps), step.key, step.title, step.metric, step.ratio, self.theme[step.color_key])

    def _build_activity_section(self, parent: tk.Frame) -> None:
        wrap = tk.Frame(parent, bg=self.theme["bg"])
        wrap.grid(row=3, column=0, sticky="nsew", pady=(0, 12))
        wrap.grid_columnconfigure(0, weight=3)
        wrap.grid_columnconfigure(1, weight=2)
        wrap.grid_rowconfigure(0, weight=1)

        log_card = self._panel(wrap, padx=12, pady=10)
        log_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)
        header = tk.Frame(log_card, bg=self.theme["panel"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tk.Label(header, text="실시간 로그", bg=self.theme["panel"], fg=self.theme["text"], font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self._mini_button(header, "로그 지우기", self.clear_log, "#1e3350", "#294565").pack(side=tk.RIGHT)
        self._mini_button(header, "전체 복사", self.copy_all_logs, "#1e3350", "#294565").pack(side=tk.RIGHT, padx=(0, 6))
        self.log = ScrolledText(
            log_card,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#081322",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            selectbackground="#1d4ed8",
            selectforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            height=9,
            exportselection=True,
        )
        self.log.grid(row=1, column=0, sticky="nsew")
        self.log.bind("<ButtonRelease-1>", self._focus_log_widget)
        self.log.bind("<Command-c>", self.copy_selected_log)
        self.log.bind("<Command-KeyPress-c>", self.copy_selected_log)
        self.log.bind("<Control-c>", self.copy_selected_log)
        self.log.bind("<Control-KeyPress-c>", self.copy_selected_log)
        self.log.bind("<<Copy>>", self.copy_selected_log)
        self.log.bind("<Command-a>", self.select_all_logs)
        self.log.bind("<Control-a>", self.select_all_logs)
        self.log.bind("<Key>", self._block_log_edit_key)

        # 로그 전용 우클릭 컨텍스트 메뉴
        self.log_menu = tk.Menu(self.log, tearoff=0, bg=self.theme["panel"], fg=self.theme["text"],
                                activebackground=self.theme["blue"], activeforeground="#ffffff", font=("Segoe UI", 9))
        self.log_menu.add_command(label="복사 (Copy)", command=self.copy_selected_log)
        self.log_menu.add_command(label="전체 선택 (Select All)", command=self.select_all_logs)
        self.log_menu.add_separator()
        self.log_menu.add_command(label="로그 지우기 (Clear)", command=self.clear_log)

        self.log.bind("<Button-3>", self._show_log_context_menu)  # Windows/Linux
        self.log.bind("<Button-2>", self._show_log_context_menu)  # macOS
        self.log.bind("<Control-Button-1>", self._show_log_context_menu) # macOS Ctrl+Click

        summary = self._panel(wrap, padx=12, pady=10)
        summary.grid(row=0, column=1, sticky="nsew")
        summary.grid_columnconfigure(0, weight=1)
        tk.Label(summary, text="오늘의 요약", bg=self.theme["panel"], fg=self.theme["text"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(summary, textvariable=self.summary_date_var, bg="#102033", fg="#cbd5e1", font=("Segoe UI", 8), padx=10, pady=4).grid(row=0, column=1, sticky="e")
        body = tk.Frame(summary, bg=self.theme["panel"])
        body.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        self.summary_canvas = tk.Canvas(body, width=142, height=142, bg=self.theme["panel"], highlightthickness=0)
        self.summary_canvas.pack(side=tk.LEFT, padx=(0, 12))
        legend = tk.Frame(body, bg=self.theme["panel"])
        legend.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._legend_row(legend, "정상 완료", self.summary_done_var, self.theme["green"])
        self._legend_row(legend, "진행 중", self.summary_running_var, self.theme["blue"])
        self._legend_row(legend, "대기 중", self.summary_waiting_var, self.theme["yellow"])
        self._legend_row(legend, "오류 / 보류", self.summary_error_var, self.theme["red"])

    def _build_table_section(self, parent: tk.Frame) -> None:
        card = self._grid_card(parent, "상품 관리  (관리자 페이지)", row=4, pady=(0, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        toolbar = tk.Frame(card, bg=self.theme["panel"])
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.product_state_filter = ttk.Combobox(
            toolbar,
            textvariable=self.product_filter_state_var,
            values=["전체 상태", "진행 중", "대기 중", "완료", "오류"],
            state="readonly",
            width=12,
        )
        self.product_state_filter.pack(side=tk.LEFT, padx=(0, 8))
        self.product_state_filter.bind("<<ComboboxSelected>>", lambda _e: self._refresh_product_table())

        self.product_category_filter = ttk.Combobox(
            toolbar,
            textvariable=self.product_filter_category_var,
            values=["전체 카테고리"],
            state="readonly",
            width=16,
        )
        self.product_category_filter.pack(side=tk.LEFT, padx=(0, 8))
        self.product_category_filter.bind("<<ComboboxSelected>>", lambda _e: self._refresh_product_table())

        search = tk.Entry(
            toolbar,
            textvariable=self.product_filter_search_var,
            bg="#091626",
            fg="#dbeafe",
            insertbackground="#dbeafe",
            relief=tk.FLAT,
            width=26,
        )
        search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 8))
        search.bind("<KeyRelease>", lambda _e: self._refresh_product_table())
        tk.Checkbutton(
            toolbar,
            text="자동 새로고침",
            variable=self.auto_refresh_var,
            command=self.toggle_auto_refresh,
            bg=self.theme["panel"],
            fg="#cbd5e1",
            selectcolor="#102033",
            activebackground=self.theme["panel"],
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        self._mini_button(toolbar, "바로고침", self.refresh_dashboard_data, "#1e3350", "#294565").pack(side=tk.LEFT)

        columns = ("no", "state", "name", "brand", "category", "price", "sheet", "updated", "action")
        self.product_table = ttk.Treeview(card, columns=columns, show="headings", style="Ops.Treeview", height=6)
        headings = {
            "no": "No.",
            "state": "상태",
            "name": "상품명",
            "brand": "브랜드",
            "category": "카테고리",
            "price": "가격 (¥)",
            "sheet": "시트",
            "updated": "최종 업데이트",
            "action": "작업",
        }
        widths = {"no": 56, "state": 92, "name": 260, "brand": 118, "category": 76, "price": 78, "sheet": 82, "updated": 104, "action": 88}
        for col in columns:
            self.product_table.heading(col, text=headings[col])
            self.product_table.column(col, width=widths[col], minwidth=widths[col], stretch=(col == "name"))
        self.product_table.grid(row=1, column=0, sticky="nsew")
        y_scrollbar = ttk.Scrollbar(card, orient=tk.VERTICAL, command=self.product_table.yview)
        x_scrollbar = ttk.Scrollbar(card, orient=tk.HORIZONTAL, command=self.product_table.xview)
        self.product_table.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        self.product_table.tag_configure("state_done", background="#153a2f", foreground="#d1fae5")
        self.product_table.tag_configure("state_running", background="#1e3a5f", foreground="#dbeafe")
        self.product_table.tag_configure("state_assets", background="#173e43", foreground="#ccfbf1")
        self.product_table.tag_configure("state_design", background="#3b2a52", foreground="#ede9fe")
        self.product_table.tag_configure("state_upload", background="#4a3318", foreground="#ffedd5")
        self.product_table.tag_configure("state_error", background="#4b1f24", foreground="#fee2e2")
        self.product_table.tag_configure("state_waiting", background="#2a3646", foreground="#e2e8f0")
        y_scrollbar.grid(row=1, column=1, sticky="ns")
        x_scrollbar.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self.empty_products_label = tk.Label(
            card,
            text="표시할 상품이 없습니다. Google Sheet를 연결하거나 로컬 products.json을 추가하면 여기에 표시됩니다.",
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            font=("Segoe UI", 9, "bold"),
            pady=8,
        )
        self.empty_products_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._refresh_product_table()

    def _build_quick_actions_panel(self, parent: tk.Frame) -> None:
        card = self._grid_card(parent, "빠른 실행", row=0, pady=(0, 12))
        def _quick_pair(make_left, make_right):
            row = tk.Frame(card, bg=self.theme["panel"])
            row.pack(fill=tk.X, pady=4)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=1)
            left_btn = make_left(row)
            right_btn = make_right(row)
            left_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            right_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            return left_btn, right_btn

        self.run_btn, self.watch_btn = _quick_pair(
            lambda p: self._quick_button(p, "정찰 1회 실행", "상품 정보 수집", self.theme["green"], lambda: self.run_action("run"), compact=True, auto_pack=False),
            lambda p: self._quick_button(p, "정찰 감시 시작", "정찰 감시 모드", "#334155", self._toggle_scout_watch, compact=True, auto_pack=False),
        )

        self.image_save_btn, self.assets_watch_btn = _quick_pair(
            lambda p: self._quick_button(p, "이미지 1회 실행", "이미지 다운로드", self.theme["blue"], lambda: self.run_action("save-images"), compact=True, auto_pack=False),
            lambda p: self._quick_button(p, "이미지 감시 시작", "이미지 감시 모드", "#334155", lambda: self._toggle_team_watch("assets"), compact=True, auto_pack=False),
        )

        self.thumb_btn, self.design_watch_btn = _quick_pair(
            lambda p: self._quick_button(p, "썸네일 1회 실행", "썸네일 일괄 제작", self.theme["purple"], self.run_thumbnail_action, compact=True, auto_pack=False),
            lambda p: self._quick_button(p, "썸네일 감시 시작", "썸네일 감시 모드", "#334155", lambda: self._toggle_team_watch("design"), compact=True, auto_pack=False),
        )

        self.upload_auto_btn, self.sales_watch_btn = _quick_pair(
            lambda p: self._quick_button(p, "업로드 1회 실행", "BUYMA 자동 업로드", self.theme["orange"], lambda: self.run_action("upload-auto"), compact=True, auto_pack=False),
            lambda p: self._quick_button(p, "업로드 감시 시작", "업로드 감시 모드", "#334155", lambda: self._toggle_team_watch("sales"), compact=True, auto_pack=False),
        )

        self.upload_review_btn = self._quick_button(card, "실패 건 재실행", "오류 상품 재처리", "#334155", lambda: self.run_action("upload-review"), compact=True)
        self.stop_btn = self._quick_button(card, "현재 작업 중지", "실행 중인 작업 종료", self.theme["red"], self.stop_action, compact=True)
        self.stop_btn.configure(state=tk.DISABLED)

    def _build_system_status_panel(self, parent: tk.Frame) -> None:
        card = self._grid_card(parent, "시스템 상태", row=1, pady=(0, 12))
        self._system_row(card, "구글 시트 연결", self.sheet_status_var)
        self._system_row(card, "구글 인증 파일", self.credentials_status_var)
        self._system_row(card, "BUYMA 로그인", self.buyma_status_var)
        self._system_row(card, "이미지 폴더", self.images_status_var)
        self._system_row(card, "프로그램 런타임", self.runtime_status_var)
        self._system_row(card, "마지막 점검", self.last_check_var, value_color="#cbd5e1")
        actions = tk.Frame(card, bg=self.theme["panel"])
        actions.pack(fill=tk.X, pady=(10, 0))
        self._mini_button(actions, "새로고침", self._refresh_system_status_labels, "#1e3350", "#294565").pack(fill=tk.X)
        self._mini_button(actions, "설정 열기", self.configure_sheet_settings, "#111f34", "#1e3350").pack(fill=tk.X, pady=(6, 0))
        self._mini_button(actions, "프로그램 정보", self._show_program_info, "#111f34", "#1e3350").pack(fill=tk.X, pady=(6, 0))

    def _panel(self, parent: tk.Widget, padx: int = 10, pady: int = 10) -> tk.Frame:
        return tk.Frame(parent, bg=self.theme["panel"], padx=padx, pady=pady, highlightbackground=self.theme["line"], highlightthickness=1)

    def _card(self, parent: tk.Widget, title: str, pady: tuple[int, int] = (0, 0)) -> tk.Frame:
        card = self._panel(parent, padx=12, pady=12)
        card.pack(fill=tk.X, pady=pady)
        tk.Label(card, text=title, bg=self.theme["panel"], fg=self.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        return card

    def _grid_card(self, parent: tk.Widget, title: str, row: int, pady: tuple[int, int]) -> tk.Frame:
        card = self._panel(parent, padx=12, pady=10)
        card.grid(row=row, column=0, sticky="nsew", pady=pady)
        tk.Label(card, text=title, bg=self.theme["panel"], fg=self.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        body = tk.Frame(card, bg=self.theme["panel"])
        body.pack(fill=tk.BOTH, expand=True)
        return body

    def _sidebar_button(self, parent: tk.Widget, text: str, active: bool, command=None) -> None:
        bg = self.theme["blue_2"] if active else self.theme["sidebar"]
        fg = "#ffffff" if active else "#d5e0ee"
        label = tk.Label(parent, text=text, bg=bg, fg=fg, font=("Segoe UI", 10, "bold"), anchor="w", padx=14, pady=10, cursor="hand2")
        label.pack(fill=tk.X, pady=2)
        self.nav_buttons[text] = label
        if command:
            label.bind("<Button-1>", lambda _event: command())
            label.bind(
                "<Enter>",
                lambda _event, name=text, widget=label: widget.configure(
                    bg=self.theme["blue_2"] if name == self.state.active_view else self.theme["blue"],
                    fg="#ffffff",
                ),
            )
            label.bind(
                "<Leave>",
                lambda _event, name=text, widget=label: widget.configure(
                    bg=self.theme["blue_2"] if name == self.state.active_view else self.theme["sidebar"],
                    fg="#ffffff" if name == self.state.active_view else "#d5e0ee",
                ),
            )

    def _set_sidebar_active(self, active_name: str) -> None:
        for name, label in self.nav_buttons.items():
            if not label.winfo_exists():
                continue
            is_active = name == active_name
            label.configure(
                bg=self.theme["blue_2"] if is_active else self.theme["sidebar"],
                fg="#ffffff" if is_active else "#d5e0ee",
            )

    def _build_pages(self) -> None:
        if self.page_container is None:
            return
        self.page_classes = {
            "대시보드": DashboardPage,
            "수집 / 정찰": ScoutPage,
            "이미지 / 썸네일": ImageThumbnailPage,
            "BUYMA 업로드": BuymaUploadPage,
            "감시 / 자동화": AutomationPage,
            "관리 / 설정": SettingsPage,
        }
        self.pages = {}

    def _show_active_page(self, view_name: str) -> None:
        if self.page_container is None:
            return
        self._set_sidebar_active(view_name)
        show_right_panel = view_name == "대시보드"
        if hasattr(self, "content_frame") and self.content_frame.winfo_exists():
            if show_right_panel:
                self.content_frame.grid_configure(columnspan=1)
            else:
                self.content_frame.grid_configure(columnspan=2)
        if hasattr(self, "right_panel_frame") and self.right_panel_frame.winfo_exists():
            if show_right_panel:
                self.right_panel_frame.grid()
            else:
                self.right_panel_frame.grid_remove()
        if hasattr(self, "right_panel_container") and self.right_panel_container.winfo_exists():
            for child in self.right_panel_container.winfo_children():
                child.destroy()
        page = self.pages.get(view_name)
        if page is None:
            page_cls = self.page_classes.get(view_name) or self.page_classes.get("대시보드")
            if page_cls is not None and self.page_container is not None:
                page = page_cls(self.page_container, self)
                self.pages[view_name] = page
        if page is None:
            page = self.pages.get("대시보드")
            if page is None:
                page_cls = self.page_classes.get("대시보드")
                if page_cls is not None and self.page_container is not None:
                    page = page_cls(self.page_container, self)
                    self.pages["대시보드"] = page
        if page is None:
            return
        page.tkraise()
        self.current_page = page
        self.current_page_name = view_name
        if show_right_panel and hasattr(self.current_page, "build_right_panel") and self.right_panel_container.winfo_exists():
            self.current_page.build_right_panel(self.right_panel_container)
        if view_name == "대시보드":
            self._populate_log_widget()
            self._refresh_product_table()
            self._render_pipeline_steps()
            self._render_metrics()

    def _link_button(self, parent: tk.Widget, text: str, command, color: str) -> None:
        ColorButton(
            parent,
            text=text,
            command=command,
            bg="#101f34",
            fg="#eaf2ff",
            activebackground=color,
            anchor="w",
            justify=tk.LEFT,
            padx=10,
            pady=7,
            font=("Segoe UI", 9, "bold"),
        ).pack(fill=tk.X, pady=3)

    def _mini_button(self, parent: tk.Widget, text: str, command, bg: str, active: str) -> ColorButton:
        return ColorButton(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg="#eaf2ff",
            activebackground=active,
            padx=12,
            pady=6,
            font=("Segoe UI", 9, "bold"),
        )

    def _kpi_card(self, parent: tk.Widget, col: int, title: str, value_var: tk.StringVar, sub: str | tk.StringVar, accent: str) -> None:
        card = self._panel(parent, padx=12, pady=12)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 5, 0 if col == 4 else 5))
        card.grid_propagate(False)
        card.configure(height=KPI_CARD_HEIGHT)
        tk.Label(card, text=title, bg=self.theme["panel"], fg=accent, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row = tk.Frame(card, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=(6, 0))
        tk.Label(row, textvariable=value_var, bg=self.theme["panel"], fg=self.theme["text"], font=("Segoe UI", 22, "bold")).pack(side=tk.LEFT)
        tk.Label(row, text="건", bg=self.theme["panel"], fg="#cbd5e1", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=(4, 0), pady=(8, 0))
        if isinstance(sub, tk.StringVar):
            tk.Label(card, textvariable=sub, bg=self.theme["panel"], fg=self.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(5, 0))
        else:
            tk.Label(card, text=sub, bg=self.theme["panel"], fg=self.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(5, 0))

    def _pipeline_step(self, parent: tk.Widget, col: int, total: int, key: str, title: str, metric: str, ratio: float, accent: str) -> None:
        bg = "#112b4f" if key == "scout" else self.theme["panel_2"]
        box = tk.Frame(parent, bg=bg, padx=12, pady=10)
        box.grid(
            row=0,
            column=col,
            sticky="nsew",
            padx=(0 if col == 0 else 5, 0 if col == total - 1 else 5),
        )
        box.grid_propagate(False)
        box.configure(height=92)
        tk.Label(box, text=title, bg=bg, fg=accent, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.pipeline_progress_vars[key] = tk.StringVar(value=f"{metric}    {int(ratio * 100)}%")
        self.pipeline_ratios[key] = ratio
        self.pipeline_colors[key] = accent
        tk.Label(box, textvariable=self.pipeline_progress_vars[key], bg=bg, fg="#f8fbff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 6))
        canvas = tk.Canvas(box, height=5, bg=bg, highlightthickness=0)
        canvas.pack(fill=tk.X)
        self.pipeline_canvas_widgets[key] = canvas
        canvas.bind("<Configure>", lambda _e, k=key: self._draw_progress(k, self.pipeline_ratios.get(k, 0.0), self.pipeline_colors.get(k, self.theme["blue"])))
        canvas.bind("<Map>", lambda _e, k=key: self.after_idle(lambda: self._draw_progress(k, self.pipeline_ratios.get(k, 0.0), self.pipeline_colors.get(k, self.theme["blue"]))))
        self.after_idle(lambda k=key: self._draw_progress(k, self.pipeline_ratios.get(k, 0.0), self.pipeline_colors.get(k, self.theme["blue"])))

    def _draw_progress(self, key: str, ratio: float, accent: str) -> None:
        canvas = self.pipeline_canvas_widgets.get(key)
        if not canvas or not canvas.winfo_exists():
            return
        width = max(1, canvas.winfo_width())
        if width <= 2:
            self.after(50, lambda: self._draw_progress(key, ratio, accent))
            return
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, 5, fill="#21334d", outline="")
        canvas.create_rectangle(0, 0, int(width * max(0.0, min(1.0, ratio))), 5, fill=accent, outline="")

    def _legend_row(self, parent: tk.Widget, label: str, value: str | tk.StringVar, color: str) -> None:
        row = tk.Frame(parent, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=5)
        tk.Label(row, text="■", bg=self.theme["panel"], fg=color, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        tk.Label(row, text=label, bg=self.theme["panel"], fg="#dbeafe", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(6, 0))
        if isinstance(value, tk.StringVar):
            tk.Label(row, textvariable=value, bg=self.theme["panel"], fg="#f8fbff", font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)
        else:
            tk.Label(row, text=value, bg=self.theme["panel"], fg="#f8fbff", font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)

    def _draw_summary_donut(self) -> None:
        canvas = getattr(self, "summary_canvas", None)
        if not canvas:
            return
        canvas.delete("all")
        metrics = self.state.metrics
        total = max(1, metrics.done + metrics.running + metrics.waiting + metrics.error)
        values = [
            (metrics.done * 100 / total, self.theme["green"]),
            (metrics.running * 100 / total, self.theme["blue"]),
            (metrics.waiting * 100 / total, self.theme["yellow"]),
            (metrics.error * 100 / total, self.theme["red"]),
        ]
        start = 90
        for value, color in values:
            extent = -360 * value / 100
            canvas.create_arc(10, 10, 132, 132, start=start, extent=extent, fill=color, outline=color)
            start += extent
        canvas.create_oval(44, 44, 98, 98, fill=self.theme["panel"], outline=self.theme["panel"])

    def _quick_button(
        self,
        parent: tk.Widget,
        title: str,
        subtitle: str,
        color: str,
        command,
        *,
        auto_pack: bool = True,
        compact: bool = False,
    ) -> ColorButton:
        text = f"{title}\n{subtitle}"
        btn = ColorButton(
            parent,
            text=text,
            command=command,
            bg=color,
            fg="#ffffff",
            activebackground=color,
            anchor="w",
            justify=tk.LEFT,
            padx=12 if compact else 16,
            pady=7 if compact else 9,
            font=("Segoe UI", 9 if compact else 10, "bold"),
        )
        if compact:
            btn.configure(height=52)
            btn.pack_propagate(False)
        if auto_pack:
            btn.pack(fill=tk.X, pady=4 if compact else 6)
        self.quick_action_buttons.append(btn)
        return btn

    def _system_row(self, parent: tk.Widget, label: str, value_var: tk.StringVar, value_color: str | None = None) -> None:
        row = tk.Frame(parent, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=6)
        tk.Label(row, text=label, bg=self.theme["panel"], fg="#c9d7e8", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Label(row, textvariable=value_var, bg=self.theme["panel"], fg=value_color or self.theme["green"], font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)

    def _refresh_product_table(self) -> None:
        if not hasattr(self, "product_table") or not self.product_table.winfo_exists():
            return
        for item in self.product_table.get_children():
            self.product_table.delete(item)
        rows = [row for row in self.state.product_rows if self._is_valid_dashboard_row(row)]
        self._refresh_product_category_filter_options(rows)
        for row in rows:
            if not self._match_product_filters(row):
                continue
            tag = self._product_state_tag(row.state)
            self.product_table.insert(
                "",
                tk.END,
                values=(row.no, row.state, row.name, row.brand, row.category, row.price, row.sheet, row.updated, row.action),
                tags=(tag,),
            )
        if hasattr(self, "empty_products_label"):
            if self.product_table.get_children():
                self.empty_products_label.configure(text="")
                self.empty_products_label.grid_remove()
            else:
                self.empty_products_label.configure(text=self.state.data_source.detail or "표시할 상품이 없습니다.")
                self.empty_products_label.grid()

    def _is_valid_dashboard_row(self, row) -> bool:
        def _clean(value: str) -> str:
            text = str(value or "").strip()
            if text.lower() in {"", "nan", "none", "#value!"}:
                return ""
            return text

        return bool(_clean(getattr(row, "name", "")) or _clean(getattr(row, "brand", "")))

    def _refresh_product_category_filter_options(self, rows) -> None:
        if not hasattr(self, "product_category_filter") or not self.product_category_filter.winfo_exists():
            return
        categories = sorted({str(row.category or "").strip() for row in rows if str(row.category or "").strip()})
        values = ["전체 카테고리"] + categories
        current = self.product_filter_category_var.get().strip() or "전체 카테고리"
        self.product_category_filter.configure(values=values)
        if current not in values:
            self.product_filter_category_var.set("전체 카테고리")

    def _match_product_filters(self, row) -> bool:
        state_filter = (self.product_filter_state_var.get() or "전체 상태").strip()
        category_filter = (self.product_filter_category_var.get() or "전체 카테고리").strip()
        keyword = (self.product_filter_search_var.get() or "").strip().lower()

        if state_filter != "전체 상태":
            bucket = self._product_state_bucket(row.state)
            if bucket != state_filter:
                return False

        if category_filter != "전체 카테고리":
            if str(row.category or "").strip() != category_filter:
                return False

        if keyword:
            haystack = f"{row.name} {row.no}".lower()
            if keyword not in haystack:
                return False
        return True

    def _product_state_bucket(self, state_text: str) -> str:
        text = str(state_text or "").lower()
        if any(word in text for word in ("완료", "성공", "출품완료", "업로드 완료")):
            return "완료"
        if any(word in text for word in ("오류", "실패", "보류", "exception", "error")):
            return "오류"
        if any(word in text for word in ("업로드", "출품", "썸네일", "디자인", "이미지", "다운로드", "저장", "정찰", "수집", "진행")):
            return "진행 중"
        return "대기 중"

    def _product_state_tag(self, state_text: str) -> str:
        text = str(state_text or "").lower()
        if any(word in text for word in ("완료", "성공", "출품완료", "업로드 완료")):
            return "state_done"
        if any(word in text for word in ("오류", "실패", "보류", "exception", "error")):
            return "state_error"
        if any(word in text for word in ("업로드", "출품")):
            return "state_upload"
        if any(word in text for word in ("썸네일", "디자인")):
            return "state_design"
        if any(word in text for word in ("이미지", "다운로드", "저장")):
            return "state_assets"
        if any(word in text for word in ("정찰", "수집", "진행")):
            return "state_running"
        return "state_waiting"

    def refresh_dashboard_data(self) -> None:
        self.dashboard_data.refresh()
        if self.current_page is not None and self.current_page_name != "대시보드" and hasattr(self.current_page, "refresh_view"):
            self.current_page.refresh_view()

    def toggle_auto_refresh(self) -> None:
        if self.auto_refresh_var.get():
            self._schedule_auto_refresh(delay_ms=1000)
        elif self.auto_refresh_job:
            try:
                self.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
            self.auto_refresh_job = None

    def _schedule_auto_refresh(self, delay_ms: int = 60000) -> None:
        if self.auto_refresh_job:
            try:
                self.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
        self.auto_refresh_job = self.after(delay_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self) -> None:
        self.auto_refresh_job = None
        if not self.auto_refresh_var.get():
            return
        self.refresh_dashboard_data()
        self._schedule_auto_refresh()

    def _refresh_system_status_labels(self) -> None:
        self.state.set_system_status(self.system_checker.collect_status())
        self.refresh_dashboard_data()
        self.refresh_first_run_wizard()

    def _update_clock(self) -> None:
        self.clock_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.after(1000, self._update_clock)

    def _show_log_folder_hint(self) -> None:
        messagebox.showinfo("로그 폴더", f"현재 로그 폴더:\n{self._get_configured_log_dir()}")

    def _show_program_info(self) -> None:
        messagebox.showinfo("프로그램 정보", "물류 자동화 런처 1.0.0\nPython 기반 운영 대시보드")

    def on_menu_click(self, menu_name: str) -> None:
        self.state.set_active_view(menu_name)
        if menu_name == "대시보드":
            self.refresh_dashboard_data()
        elif "BUYMA" in menu_name:
            self._refresh_product_table()
        self.logger.emit(f"메뉴 선택: {menu_name}\n", category="navigation")

    def dispatch_ui_action(self, label: str, callback=None, *, category: str = "ui"):
        self.logger.emit(f"{label}\n", category=category)
        if callback is None:
            return None
        return callback()

    def _build_stat_card(self, parent: tk.Frame, col: int, title: str, value_var: tk.StringVar, accent: str) -> None:
        card = tk.Frame(parent, bg="#161f3e", padx=12, pady=10, highlightbackground=accent, highlightthickness=1)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
        tk.Label(card, text=title, bg="#161f3e", fg="#afc3ef", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(card, textvariable=value_var, bg="#161f3e", fg="#f5fbff", font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(2, 0))

    def _build_first_run_wizard(self, parent: tk.Frame) -> None:
        card = tk.Frame(parent, bg="#182446", padx=12, pady=12, highlightbackground="#5ef2c2", highlightthickness=1)
        card.pack(fill=tk.X, pady=(2, 10))
        tk.Label(card, text="첫 실행 마법사", bg="#182446", fg="#f7fbff", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(
            card,
            text="처음 쓰는 사람도 순서대로 눌러서 준비할 수 있게 만든 안내 영역입니다.",
            bg="#182446",
            fg="#afc3ef",
            justify=tk.LEFT,
            wraplength=260,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 8))
        tk.Label(
            card,
            textvariable=self.wizard_summary_var,
            bg="#182446",
            fg="#5ef2c2",
            justify=tk.LEFT,
            wraplength=260,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        self._build_wizard_step(
            card,
            "1. 실행 준비",
            "Python, 가상환경, 필수 패키지를 준비합니다.",
            self.wizard_status_vars["runtime"],
            self.run_install_from_wizard,
            "필수 설치",
        )
        self._build_wizard_step(
            card,
            "2. Google 키 연결",
            "credentials.json을 연결해서 시트 접근 준비를 합니다.",
            self.wizard_status_vars["credentials"],
            self.import_credentials_file,
            "파일 연결",
        )
        self._build_wizard_step(
            card,
            "3. 작업 시트 연결",
            "Spreadsheet ID, 시트 이름, GID를 저장합니다.",
            self.wizard_status_vars["sheet"],
            self.configure_sheet_settings,
            "시트 설정",
        )
        self._build_wizard_step(
            card,
            "4. 모자이크 준비",
            "썸네일 얼굴 블러에 필요한 OpenCV와 cascade 파일을 확인합니다.",
            self.wizard_status_vars["mosaic"],
            self.run_install_from_wizard,
            "필수 설치",
        )
        self._build_wizard_step(
            card,
            "5. BUYMA 계정",
            "업로드에 쓸 BUYMA 아이디와 비밀번호를 저장합니다.",
            self.wizard_status_vars["buyma"],
            self.configure_buyma_credentials,
            "계정 입력",
        )

        actions = tk.Frame(card, bg="#182446")
        actions.pack(fill=tk.X, pady=(4, 0))
        tk.Button(
            actions,
            text="상태 다시 확인",
            command=self.refresh_first_run_wizard,
            bg="#32466f",
            fg="#eff4ff",
            relief=tk.FLAT,
            activebackground="#3e5a8e",
        ).pack(fill=tk.X, ipady=5)
        tk.Button(
            actions,
            text="연결 테스트",
            command=self.test_google_setup,
            bg="#2b5f8a",
            fg="#eff7ff",
            relief=tk.FLAT,
            activebackground="#3675aa",
        ).pack(fill=tk.X, pady=(6, 0), ipady=5)
        tk.Button(
            actions,
            text="샘플 1건 실행",
            command=self.run_sample_check,
            bg="#2d7b56",
            fg="#effff7",
            relief=tk.FLAT,
            activebackground="#379167",
        ).pack(fill=tk.X, pady=(6, 0), ipady=5)

    def _build_wizard_step(
        self,
        parent: tk.Frame,
        title: str,
        description: str,
        status_var: tk.StringVar,
        command,
        button_text: str,
    ) -> None:
        row = tk.Frame(parent, bg="#1e2b52", padx=10, pady=8, highlightbackground="#30416f", highlightthickness=1)
        row.pack(fill=tk.X, pady=4)
        tk.Label(row, text=title, bg="#1e2b52", fg="#f7fbff", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(
            row,
            text=description,
            bg="#1e2b52",
            fg="#9fb1dd",
            justify=tk.LEFT,
            wraplength=240,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 6))
        bottom = tk.Frame(row, bg="#1e2b52")
        bottom.pack(fill=tk.X)
        bottom.grid_columnconfigure(0, weight=1)
        tk.Label(
            bottom,
            textvariable=status_var,
            bg="#1e2b52",
            fg="#5ef2c2",
            justify=tk.LEFT,
            anchor="w",
            wraplength=165,
            font=("Consolas", 9, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        tk.Button(
            bottom,
            text=button_text,
            command=command,
            bg="#334d86",
            fg="#f3f6ff",
            relief=tk.FLAT,
            activebackground="#4062a6",
        ).grid(row=0, column=1, sticky="e")

    def run_install_from_wizard(self) -> None:
        self.refresh_first_run_wizard()
        if self.process_manager.is_running():
            messagebox.showwarning("실행 중", "이미 작업이 실행 중입니다. 먼저 중지해주세요.")
            return
        self.run_action("install")

    def _build_stage_card(self, parent: tk.Frame, team: str, desc: str, key: str, accent: str) -> None:
        card = tk.Frame(parent, bg="#1a2346", padx=10, pady=10, highlightbackground=accent, highlightthickness=1)
        card.pack(fill=tk.X, pady=5)
        self.stage_card_widgets[key] = card
        row = tk.Frame(card, bg="#1a2346")
        row.pack(fill=tk.X)
        avatar = tk.Canvas(row, width=42, height=42, bg="#1a2346", highlightthickness=0, bd=0)
        avatar.pack(side=tk.LEFT, padx=(0, 8))
        self._draw_pixel_agent(avatar, key)
        info = tk.Frame(row, bg="#1a2346")
        info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        title_lbl = tk.Label(info, text=team, bg="#1a2346", fg="#f7fbff", font=("Segoe UI", 12, "bold"))
        title_lbl.pack(anchor="w")
        desc_lbl = tk.Label(info, text=desc, bg="#1a2346", fg="#9fb1dd", font=("Segoe UI", 10))
        desc_lbl.pack(anchor="w", pady=(1, 2))
        state_lbl = tk.Label(info, textvariable=self.stage_vars[key], bg="#1a2346", fg="#7bf0ca", font=("Consolas", 10, "bold"))
        state_lbl.pack(anchor="w")
        for widget in (card, row, avatar, info, title_lbl, desc_lbl, state_lbl):
            widget.bind("<Button-1>", lambda _e, team_key=key: self._open_team_action_bubble(team_key))

    def _draw_pixel_agent(self, canvas: tk.Canvas, key: str) -> None:
        palette = {
            "scout": ("#d7b58a", "#2f4f9c", "#141414"),
            "assets": ("#d7b58a", "#2d7b56", "#2c2c2c"),
            "design": ("#d7b58a", "#8b5f2d", "#3a2a1f"),
            "sales": ("#d7b58a", "#3d78ad", "#1f2a39"),
        }
        skin, suit, hair = palette.get(key, ("#d7b58a", "#3567a0", "#202020"))
        px = 4
        # desk
        canvas.create_rectangle(2, 30, 40, 40, fill="#2a3557", outline="")
        # head
        canvas.create_rectangle(12, 6, 28, 18, fill=skin, outline="")
        # hair
        canvas.create_rectangle(12, 6, 28, 10, fill=hair, outline="")
        # body
        canvas.create_rectangle(10, 18, 30, 30, fill=suit, outline="")
        # eyes
        canvas.create_rectangle(16, 12, 18, 14, fill="#111111", outline="")
        canvas.create_rectangle(22, 12, 24, 14, fill="#111111", outline="")
        # tie/badge
        canvas.create_rectangle(19, 20, 21, 27, fill="#f6e27a", outline="")
        # pixel trim
        for x in range(0, 42, px):
            canvas.create_line(x, 0, x, 42, fill="#192342")
        for y in range(0, 42, px):
            canvas.create_line(0, y, 42, y, fill="#192342")

    def _get_team_actions(self, team_key: str) -> list[tuple[str, str]]:
        watch_label = "팀 감시 중지" if self.team_watch_enabled.get(team_key, False) else "팀 감시 시작"
        if team_key == "scout":
            scout_watch_label = "팀 감시 중지" if self._is_scout_watch_running() else "팀 감시 시작"
            return [
                ("정찰 시작", "run"),
                ("목록 수집", "collect-listings"),
                (scout_watch_label, "scout-watch-toggle"),
            ]
        if team_key == "assets":
            return [
                ("이미지 저장", "save-images"),
                (watch_label, f"team-watch-toggle:{team_key}"),
            ]
        if team_key == "design":
            return [
                ("썸네일 만들기", "thumbnail-create"),
                (watch_label, f"team-watch-toggle:{team_key}"),
            ]
        if team_key == "sales":
            return [
                ("검토 후 업로드", "upload-review"),
                ("한 번 자동 업로드", "upload-auto"),
                (watch_label, f"team-watch-toggle:{team_key}"),
            ]
        return []

    def _open_team_action_bubble(self, team_key: str) -> None:
        self._close_action_bubble()
        anchor = self.stage_card_widgets.get(team_key)
        if anchor is None:
            return

        bubble = tk.Toplevel(self)
        bubble.overrideredirect(True)
        bubble.configure(bg="#101834")
        bubble.attributes("-topmost", True)

        shell = tk.Frame(bubble, bg="#101834")
        shell.pack()
        tail = tk.Canvas(shell, width=12, height=20, bg="#101834", highlightthickness=0, bd=0)
        tail.pack(side=tk.LEFT, padx=(0, 0), pady=(16, 0))
        tail.create_polygon(12, 0, 0, 10, 12, 20, fill="#eaf0ff", outline="#4d5d87")

        panel = tk.Frame(shell, bg="#eaf0ff", padx=10, pady=8, highlightbackground="#4d5d87", highlightthickness=1)
        panel.pack(side=tk.LEFT)
        tk.Label(panel, text="옵션 선택", bg="#eaf0ff", fg="#2a3559", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

        for label, action in self._get_team_actions(team_key):
            tk.Button(
                panel,
                text=label,
                relief=tk.FLAT,
                bg="#ffffff",
                fg="#243252",
                activebackground="#d7e3ff",
                command=lambda a=action: self._run_bubble_action(a),
            ).pack(fill=tk.X, pady=2, ipady=3)

        tk.Button(
            panel,
            text="닫기",
            relief=tk.FLAT,
            bg="#dce4f7",
            fg="#34415f",
            activebackground="#cad5f0",
            command=self._close_action_bubble,
        ).pack(fill=tk.X, pady=(6, 0), ipady=2)

        self.update_idletasks()
        x = anchor.winfo_rootx() + anchor.winfo_width() + 8
        y = anchor.winfo_rooty() + max(0, (anchor.winfo_height() - bubble.winfo_reqheight()) // 2)
        bubble.geometry(f"+{x}+{y}")
        bubble.focus_force()
        bubble.bind("<FocusOut>", lambda _e: self._close_action_bubble())
        self.action_bubble = bubble

    def _close_action_bubble(self) -> None:
        if self.action_bubble is not None:
            try:
                self.action_bubble.destroy()
            except Exception:
                pass
            self.action_bubble = None

    def _run_bubble_action(self, action: str) -> None:
        self._close_action_bubble()
        if action.startswith("team-watch-toggle:"):
            team_key = action.split(":", 1)[1].strip()
            self._toggle_team_watch(team_key)
            return
        if action == "scout-watch-toggle":
            self._toggle_scout_watch()
            return
        if action == "sheet-config":
            self.configure_sheet_settings()
            return
        if action == "thumbnail-create":
            self.run_thumbnail_action()
            return
        self.run_action(action)

    def _is_scout_watch_running(self) -> bool:
        return bool(self.state.current_action == "watch" and self.process_manager.is_running())

    def _toggle_scout_watch(self) -> None:
        if self._is_scout_watch_running():
            self.stop_action()
            self._refresh_action_button_labels()
            return
        self.run_action("watch")
        self._refresh_action_button_labels()

    def _toggle_team_watch(self, team_key: str) -> None:
        if team_key not in self.team_watch_actions:
            return
        if self.team_watch_enabled.get(team_key):
            self._stop_team_watch(team_key)
        else:
            self._start_team_watch(team_key)
        self._refresh_action_button_labels()

    def _start_team_watch(self, team_key: str) -> None:
        if team_key not in self.team_watch_actions:
            return
        if self.team_watch_enabled.get(team_key):
            return
        self.action_runner.start_team_watch(team_key)
        self._schedule_team_watch_tick(team_key, delay_ms=20000)
        self._refresh_action_button_labels()

    def _stop_team_watch(self, team_key: str) -> None:
        if team_key not in self.team_watch_actions:
            return
        self.action_runner.stop_team_watch(team_key)
        job_id = self.team_watch_jobs.pop(team_key, None)
        if job_id:
            try:
                self.after_cancel(job_id)
            except Exception:
                pass
        self._refresh_action_button_labels()

    def _schedule_team_watch_tick(self, team_key: str, delay_ms: int = 20000) -> None:
        if not self.team_watch_enabled.get(team_key, False):
            return
        job_id = self.after(delay_ms, lambda k=team_key: self._team_watch_tick(k))
        self.team_watch_jobs[team_key] = job_id

    def _team_watch_tick(self, team_key: str) -> None:
        self.team_watch_jobs.pop(team_key, None)
        if not self.team_watch_enabled.get(team_key, False):
            return

        self.action_runner.start_team_watch(team_key)
        self._schedule_team_watch_tick(team_key)

    def _sync_pipeline_badge(self, key: str, text: str) -> None:
        var = self.pipeline_progress_vars.get(key)
        if var is None:
            return
        status_map = {
            "진행중": "실행 중",
            "감시중": "감시 중",
            "완료": "완료",
            "실패": "확인 필요",
            "대기": "대기",
        }
        current = var.get()
        metric = current.split("    ", 1)[0] if "    " in current else current
        var.set(f"{metric}    {status_map.get(text, text)}")

    def append_log(self, text: str) -> None:
        if hasattr(self, "log") and self.log.winfo_exists():
            self.log.insert(tk.END, text)
            self.log.see(tk.END)

    def clear_log(self) -> None:
        self.log_history.clear()
        if hasattr(self, "log") and self.log.winfo_exists():
            self.log.delete("1.0", tk.END)

    def copy_selected_log(self, _event=None) -> str:
        if not hasattr(self, "log") or not self.log.winfo_exists():
            return "break"
        selection = self.log.tag_ranges(tk.SEL)
        if selection:
            text = self.log.get(selection[0], selection[1])
        else:
            text = self.log.get("1.0", tk.END).rstrip()
        self.clipboard_clear()
        self.clipboard_append(text)
        return "break"

    def copy_all_logs(self) -> None:
        text = "\n".join(line.rstrip("\n") for line in self.log_history).rstrip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("로그 복사 완료")

    def select_all_logs(self, _event=None) -> str:
        if not hasattr(self, "log") or not self.log.winfo_exists():
            return "break"
        self.log.tag_add(tk.SEL, "1.0", tk.END)
        self.log.mark_set(tk.INSERT, "1.0")
        self.log.see(tk.INSERT)
        self.log.focus_set()
        return "break"

    def _focus_log_widget(self, _event=None) -> None:
        if hasattr(self, "log") and self.log.winfo_exists():
            self.log.focus_set()

    def _show_log_context_menu(self, event) -> None:
        if hasattr(self, "log_menu"):
            self.log_menu.tk_popup(event.x_root, event.y_root)

    def _block_log_edit_key(self, event=None) -> str | None:
        if not event:
            return "break"
        # 네비게이션 및 선택 키 허용 (방향키, Home, End, PageUp/Down, 각수정키)
        if event.keysym in ("Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End",
                           "Control_L", "Control_R", "Shift_L", "Shift_R", "Meta_L", "Meta_R"):
            return None
        # 복사(C) 및 전체선택(A) 단축키 조합 허용 (Ctrl, Cmd, Mod 등 대응)
        if (event.state & (0x4 | 0x8 | 0x10)) and str(event.keysym).lower() in {"a", "c"}:
            return None
        # 그 외의 일반 키 입력(텍스트 수정)만 차단
        return "break"

    def _set_running_ui(self, running: bool) -> None:
        one_shot_state = tk.DISABLED if running else tk.NORMAL
        for attr_name in (
            "run_btn",
            "image_save_btn",
            "upload_review_btn",
            "upload_auto_btn",
            "thumb_btn",
        ):
            button = getattr(self, attr_name, None)
            if button is not None and button.winfo_exists():
                button.configure(state=one_shot_state)

        # Watch toggles should stay clickable so users can turn OFF immediately.
        watch_toggle_state = tk.NORMAL
        for attr_name in ("watch_btn", "assets_watch_btn", "design_watch_btn", "sales_watch_btn"):
            button = getattr(self, attr_name, None)
            if button is not None and button.winfo_exists():
                button.configure(state=watch_toggle_state)
        stop_button = getattr(self, "stop_btn", None)
        if stop_button is not None and stop_button.winfo_exists():
            stop_button.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _get_sheet_label_prefix(self) -> str:
        return "정찰팀"

    def _refresh_action_button_labels(self) -> None:
        for attr_name, text in (
            ("run_btn", "정찰 1회 실행\n상품 정보 수집"),
            ("image_save_btn", "이미지 1회 실행\n이미지 다운로드"),
            ("thumb_btn", "썸네일 1회 실행\n썸네일 일괄 제작"),
            ("upload_auto_btn", "업로드 1회 실행\nBUYMA 자동 업로드"),
        ):
            button = getattr(self, attr_name, None)
            if button is not None and button.winfo_exists():
                button.configure(text=text)

        scout_watch_text = "정찰 감시 ON\n정찰 감시 모드" if self._is_scout_watch_running() else "정찰 감시 OFF\n정찰 감시 모드"
        assets_watch_text = "이미지 감시 ON\n이미지 감시 모드" if self.team_watch_enabled.get("assets", False) else "이미지 감시 OFF\n이미지 감시 모드"
        design_watch_text = "썸네일 감시 ON\n썸네일 감시 모드" if self.team_watch_enabled.get("design", False) else "썸네일 감시 OFF\n썸네일 감시 모드"
        sales_watch_text = "업로드 감시 ON\n업로드 감시 모드" if self.team_watch_enabled.get("sales", False) else "업로드 감시 OFF\n업로드 감시 모드"

        for attr_name, text in (
            ("watch_btn", scout_watch_text),
            ("assets_watch_btn", assets_watch_text),
            ("design_watch_btn", design_watch_text),
            ("sales_watch_btn", sales_watch_text),
        ):
            button = getattr(self, attr_name, None)
            if button is not None and button.winfo_exists():
                button.configure(text=text)

        watch_on_colors = {
            "watch_btn": "#0f766e",        # scout
            "assets_watch_btn": "#1d4ed8", # image
            "design_watch_btn": "#6d28d9", # thumbnail
            "sales_watch_btn": "#b45309",  # upload
        }
        watch_on_states = {
            "watch_btn": self._is_scout_watch_running(),
            "assets_watch_btn": self.team_watch_enabled.get("assets", False),
            "design_watch_btn": self.team_watch_enabled.get("design", False),
            "sales_watch_btn": self.team_watch_enabled.get("sales", False),
        }
        for attr_name, is_on in watch_on_states.items():
            button = getattr(self, attr_name, None)
            if button is None or not button.winfo_exists():
                continue
            if is_on:
                on_bg = watch_on_colors[attr_name]
                button.configure(bg=on_bg, activebackground=on_bg)
            else:
                button.configure(bg="#334155", activebackground="#334155")

    def _get_credentials_target_path(self) -> str:
        return self.system_checker.get_credentials_target_path()

    def _get_buyma_credentials_target_path(self) -> str:
        return self.system_checker.get_buyma_credentials_target_path()

    def _get_available_credentials_path(self) -> str:
        return self.system_checker.get_available_credentials_path()

    def _has_buyma_credentials(self) -> bool:
        return self.system_checker.has_buyma_credentials()

    def _load_buyma_email(self) -> str:
        return self.system_checker.load_buyma_email()

    def _has_ready_runtime(self) -> bool:
        return self.system_checker.has_ready_runtime()

    def _get_mosaic_runtime_state(self) -> str:
        return self.system_checker.get_mosaic_runtime_state()

    def _has_credentials_file(self) -> bool:
        return bool(self._get_available_credentials_path())

    def _has_valid_sheet_config(self) -> bool:
        return self.system_checker.has_valid_sheet_config()

    def refresh_first_run_wizard(self) -> None:
        runtime_ready = self._has_ready_runtime()
        credentials_ready = self._has_credentials_file()
        sheet_ready = self._has_valid_sheet_config()
        mosaic_state = self._get_mosaic_runtime_state()
        mosaic_ready = mosaic_state in {"ready", "installed"}
        buyma_ready = self._has_buyma_credentials()

        runtime_text = f"{'완료' if runtime_ready else '필요'} · Python {os.path.basename(resolve_python_executable())}"
        self.wizard_status_vars["runtime"].set(runtime_text)

        credentials_path = self._get_available_credentials_path()
        if credentials_ready:
            self.wizard_status_vars["credentials"].set(f"완료 · {os.path.basename(credentials_path)} 연결됨")
        else:
            self.wizard_status_vars["credentials"].set("필요 · credentials.json 파일을 연결해주세요")

        cfg = self._load_sheet_config()
        if sheet_ready:
            sheet_name = (cfg.get("sheet_name") or "").strip()
            self.wizard_status_vars["sheet"].set(f"완료 · {sheet_name} 연결됨")
        else:
            self.wizard_status_vars["sheet"].set("필요 · Spreadsheet ID와 시트 이름을 입력해주세요")

        if mosaic_state == "ready":
            self.wizard_status_vars["mosaic"].set("완료 · 얼굴 모자이크 사용 가능")
        elif mosaic_state == "installed":
            self.wizard_status_vars["mosaic"].set("완료 · OpenCV 설치됨 (얼굴 블러는 일부 환경에서 제한될 수 있음)")
        else:
            self.wizard_status_vars["mosaic"].set("필요 · OpenCV 모자이크 구성요소를 설치해주세요")

        if buyma_ready:
            email = self._load_buyma_email()
            self.wizard_status_vars["buyma"].set(f"완료 · {email or 'BUYMA 계정 저장됨'}")
        else:
            self.wizard_status_vars["buyma"].set("선택 · 업로드 전 BUYMA 계정을 저장해주세요")

        if runtime_ready and credentials_ready and sheet_ready and mosaic_ready:
            if buyma_ready:
                self.wizard_summary_var.set("준비 완료. 이제 샘플 1건 실행이나 감시 모드를 시작할 수 있습니다.")
            else:
                self.wizard_summary_var.set("준비 완료. 업로드를 쓰려면 BUYMA 계정만 입력하면 됩니다.")
        elif runtime_ready and credentials_ready and sheet_ready and mosaic_state == "missing":
            self.wizard_summary_var.set("거의 준비 완료. 얼굴 모자이크를 쓰려면 한 번 더 필수 설치를 실행해주세요.")
        elif not credentials_ready:
            self.wizard_summary_var.set("다음 단계: Google 키 파일(credentials.json)을 연결해주세요.")
        elif not sheet_ready:
            self.wizard_summary_var.set("다음 단계: 작업할 Google 시트 정보를 입력해주세요.")
        else:
            self.wizard_summary_var.set("실행 준비를 마쳤습니다. 연결 테스트를 눌러 확인해보세요.")

    def configure_buyma_credentials(self) -> bool:
        current_email = self.buyma_credentials.load_email()
        email = simpledialog.askstring(
            "BUYMA 계정",
            "BUYMA 아이디(이메일)를 입력하세요.",
            initialvalue=current_email,
            parent=self,
        )
        if email is None:
            return False
        email = email.strip()
        if not email:
            messagebox.showwarning("입력 오류", "BUYMA 아이디를 입력해주세요.")
            return False

        password = simpledialog.askstring(
            "BUYMA 계정",
            "BUYMA 비밀번호를 입력하세요.",
            parent=self,
            show="*",
        )
        if password is None:
            return False
        password = password.strip()
        if not password:
            messagebox.showwarning("입력 오류", "BUYMA 비밀번호를 입력해주세요.")
            return False

        try:
            target_path = self._get_buyma_credentials_target_path()
            self.buyma_credentials.save(email, password)
            self.logger.emit(f"BUYMA 계정 저장 완료: {target_path}\n", category="settings")
            messagebox.showinfo("BUYMA 계정 저장", "BUYMA 아이디와 비밀번호를 저장했습니다.")
            self.refresh_first_run_wizard()
            return True
        except Exception as exc:
            messagebox.showerror("저장 실패", f"BUYMA 계정 저장 실패: {exc}")
            return False

    def import_buyma_credentials_file(self) -> bool:
        selected_path = filedialog.askopenfilename(
            title="BUYMA 계정 파일 선택",
            initialdir=os.path.expanduser("~"),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            parent=self,
        )
        if not selected_path:
            return False
        try:
            with open(selected_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            email = str(data.get("email", "")).strip()
            password = str(data.get("password", "")).strip()
            if email and password and "@" in email:
                self.buyma_credentials.save(email, password)
            else:
                decoded_email, decoded_password = "", ""
                try:
                    decoded_email = base64.b64decode(email.encode()).decode().strip()
                    decoded_password = base64.b64decode(password.encode()).decode().strip()
                except Exception:
                    pass
                if decoded_email and decoded_password and "@" in decoded_email:
                    self.buyma_credentials.save(decoded_email, decoded_password)
                else:
                    shutil.copy2(selected_path, self._get_buyma_credentials_target_path())
                    self.buyma_credentials = BuymaCredentialService(self._get_buyma_credentials_target_path())
                    if not self.buyma_credentials.exists():
                        raise ValueError("지원하지 않는 BUYMA 계정 파일 형식입니다.")
            self.logger.emit(f"BUYMA 계정 파일 가져오기 완료: {self._get_buyma_credentials_target_path()}\n", category="settings")
            messagebox.showinfo("가져오기 완료", "BUYMA 계정 파일을 현재 프로필에 연결했습니다.")
            self.refresh_first_run_wizard()
            self.refresh_dashboard_data()
            return True
        except Exception as exc:
            messagebox.showerror("가져오기 실패", f"BUYMA 계정 파일을 불러오지 못했습니다: {exc}")
            return False

    def configure_user_profile(self) -> bool:
        new_profile = simpledialog.askstring(
            "프로필 변경",
            "사용할 운영자 프로필명을 입력하세요.",
            initialvalue=self.profile_name,
            parent=self,
        )
        if new_profile is None:
            return False
        new_profile = sanitize_profile_name(new_profile)
        if new_profile == self.profile_name:
            return True
        save_profile_name(new_profile)
        messagebox.showinfo(
            "프로필 변경",
            f"활성 프로필을 '{new_profile}'(으)로 저장했습니다.\n런처를 다시 실행하면 해당 프로필 데이터 폴더를 사용합니다.",
        )
        self.logger.emit(f"프로필 변경 저장: {self.profile_name} -> {new_profile}\n", category="settings")
        self.profile_name = new_profile
        return True

    def import_credentials_file(self) -> bool:
        initial_dir = os.path.expanduser("~/Downloads")
        selected_path = filedialog.askopenfilename(
            title="credentials.json 선택",
            initialdir=initial_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            parent=self,
        )
        if not selected_path:
            return False

        try:
            os.makedirs(self.data_dir, exist_ok=True)
            target_path = self._get_credentials_target_path()
            shutil.copy2(selected_path, target_path)
            self.logger.emit(f"자격증명 파일 연결 완료: {target_path}\n", category="settings")
            messagebox.showinfo("키 연결 완료", f"credentials.json을 연결했습니다.\n저장 위치: {target_path}")
            self.refresh_first_run_wizard()
            return True
        except Exception as exc:
            messagebox.showerror("키 연결 실패", f"credentials.json 복사 실패: {exc}")
            return False

    def test_google_setup(self) -> bool:
        credentials_path = self._get_available_credentials_path()
        if not credentials_path:
            messagebox.showwarning(
                "키 파일 필요",
                "먼저 credentials.json 파일을 연결해주세요.\n보통 Downloads에 받은 JSON 파일을 선택하면 됩니다.",
            )
            self.refresh_first_run_wizard()
            return False

        cfg = self._load_sheet_config()
        spreadsheet_id = self._normalize_spreadsheet_id(cfg.get("spreadsheet_id", ""))
        if not self._is_valid_spreadsheet_id(spreadsheet_id):
            messagebox.showwarning("시트 설정 필요", "먼저 Spreadsheet ID 또는 시트 URL을 입력해주세요.")
            self.refresh_first_run_wizard()
            return False

        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
            service = build("sheets", "v4", credentials=creds)
            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            title = str(spreadsheet.get("properties", {}).get("title", "")).strip() or "제목 미확인"
            self.logger.emit(f"Google Sheets 연결 테스트 성공: {title}\n", category="system")
            messagebox.showinfo("연결 성공", f"Google Sheets 연결 확인 완료\n시트 제목: {title}")
            self.refresh_first_run_wizard()
            return True
        except Exception as exc:
            messagebox.showerror(
                "연결 실패",
                "Google Sheets 연결 확인에 실패했습니다.\n"
                "1) credentials.json 파일\n"
                "2) Spreadsheet ID\n"
                "3) 시트 공유 대상(client_email)\n"
                f"를 확인해주세요.\n\n상세 오류: {exc}",
            )
            self.refresh_first_run_wizard()
            return False

    def run_sample_check(self) -> None:
        if not self.test_google_setup():
            return
        if self.process_manager.is_running():
            messagebox.showwarning("실행 중", "이미 작업이 실행 중입니다. 먼저 중지해주세요.")
            return
        if not messagebox.askyesno(
            "샘플 1건 실행",
            "현재 시트 기준으로 첫 작업 1건을 확인해보려면 정찰팀 시작을 실행합니다.\n계속할까요?",
        ):
            return
        self.run_action("run")

    def _load_sheet_config(self) -> dict:
        return self.system_checker.load_sheet_config()

    def _get_configured_images_dir(self) -> str:
        cfg = self._load_sheet_config()
        configured = (cfg.get("images_dir") or "").strip()
        if configured:
            return os.path.abspath(os.path.expanduser(configured))
        return get_default_images_dir()

    def _get_configured_log_dir(self) -> str:
        cfg = self._load_sheet_config()
        configured = (cfg.get("log_dir") or "").strip()
        if configured:
            return os.path.abspath(os.path.expanduser(configured))
        return os.path.join(self.data_dir, "logs")

    def _save_sheet_config(self, config: dict) -> bool:
        try:
            return self.system_checker.save_sheet_config(config)
        except Exception as e:
            messagebox.showerror("저장 실패", f"시트 설정 저장 실패: {e}")
            return False

    def _get_thumbnail_footer_suffix(self) -> str:
        cfg = self._load_sheet_config()
        configured = (cfg.get("thumbnail_footer_suffix") or "").strip()
        return configured or DEFAULT_THUMBNAIL_FOOTER_SUFFIX

    def _get_thumbnail_blur_faces_enabled(self) -> bool:
        options = ((self.profile_config.get("crawling") or {}).get("options") or {})
        if "blur_faces" in options:
            return bool(options.get("blur_faces"))
        return True

    def configure_images_directory(self) -> bool:
        current_dir = self._get_configured_images_dir()
        selected_dir = filedialog.askdirectory(
            title="이미지 저장 폴더 선택",
            initialdir=current_dir,
            mustexist=False,
            parent=self,
        )
        if not selected_dir:
            return False

        selected_dir = os.path.abspath(os.path.expanduser(selected_dir))
        try:
            os.makedirs(selected_dir, exist_ok=True)
        except Exception as exc:
            messagebox.showerror("폴더 생성 실패", f"선택한 폴더를 준비하지 못했습니다: {exc}")
            return False

        current = self._load_sheet_config()
        current["images_dir"] = selected_dir
        if not self._save_sheet_config(current):
            return False

        self.logger.emit(f"이미지 저장 경로 설정 완료: {selected_dir}\n", category="settings")
        messagebox.showinfo("이미지 경로 저장", f"앞으로 이미지 저장 기본 경로로 사용합니다.\n{selected_dir}")
        return True

    def configure_thumbnail_footer_suffix(self) -> bool:
        current = self._load_sheet_config()
        current_suffix = (current.get("thumbnail_footer_suffix") or "").strip() or DEFAULT_THUMBNAIL_FOOTER_SUFFIX
        value = simpledialog.askstring(
            "썸네일 푸터 문구",
            "브랜드 뒤에 붙는 고정 문구를 입력하세요.\n예: angduss k-closet",
            initialvalue=current_suffix,
            parent=self,
        )
        if value is None:
            return False
        suffix = value.strip() or DEFAULT_THUMBNAIL_FOOTER_SUFFIX
        current["thumbnail_footer_suffix"] = suffix
        if not self._save_sheet_config(current):
            return False
        self.logger.emit(f"썸네일 푸터 문구 저장: {suffix}\n", category="settings")
        messagebox.showinfo("저장 완료", f"썸네일 푸터 문구를 저장했습니다.\n{suffix}")
        return True

    def _has_sheet_config(self) -> bool:
        cfg = self._load_sheet_config()
        return bool((cfg.get("spreadsheet_id") or "").strip())

    def _normalize_spreadsheet_id(self, raw_value: str) -> str:
        return self.system_checker.normalize_spreadsheet_id(raw_value)

    def _is_valid_spreadsheet_id(self, spreadsheet_id: str) -> bool:
        return self.system_checker.is_valid_spreadsheet_id(spreadsheet_id)

    def configure_sheet_settings(self) -> bool:
        """시트 설정 팝업을 띄우고 저장한다."""
        current = self._load_sheet_config()
        cur_id = (current.get("spreadsheet_id") or "").strip()
        cur_name = (current.get("sheet_name") or "시트1").strip() or "시트1"
        cur_gids = current.get("sheet_gids") or [1698424449]
        cur_gid_text = ",".join(str(x) for x in cur_gids if isinstance(x, int))

        spreadsheet_input = simpledialog.askstring(
            "시트 설정",
            "Google Spreadsheet ID 또는 시트 URL을 입력하세요.",
            initialvalue=cur_id,
            parent=self,
        )
        if spreadsheet_input is None:
            return False

        spreadsheet_id = self._normalize_spreadsheet_id(spreadsheet_input)
        if not self._is_valid_spreadsheet_id(spreadsheet_id):
            messagebox.showwarning(
                "입력 오류",
                "유효한 Spreadsheet ID가 아닙니다.\n이메일이 아니라 시트 URL의 /d/ 뒤 문자열을 입력해주세요.",
            )
            return False

        sheet_name = simpledialog.askstring(
            "시트 설정",
            "시트 이름을 입력하세요. (기본: 시트1)",
            initialvalue=cur_name,
            parent=self,
        )
        if sheet_name is None:
            return False
        sheet_name = sheet_name.strip() or "시트1"

        gid_text = simpledialog.askstring(
            "시트 설정",
            "시트 GID를 입력하세요. (여러 개면 쉼표로 구분)",
            initialvalue=cur_gid_text or "1698424449",
            parent=self,
        )
        if gid_text is None:
            return False

        gids: list[int] = []
        for token in [t.strip() for t in gid_text.split(",") if t.strip()]:
            if token.isdigit():
                gids.append(int(token))
        if not gids:
            gids = [1698424449]

        queue_sheet_url = simpledialog.askstring(
            "시트 설정",
            "목록 수집 탭 URL을 입력하세요. (선택, gid 포함 URL 권장)",
            initialvalue=(current.get("queue_sheet_url") or "").strip(),
            parent=self,
        )
        if queue_sheet_url is None:
            return False

        config = {
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "sheet_gids": gids,
            "row_start": 2,
            "images_dir": (current.get("images_dir") or "").strip(),
            "queue_sheet_url": (queue_sheet_url or "").strip(),
            "thumbnail_footer_suffix": (current.get("thumbnail_footer_suffix") or "").strip(),
        }
        if not self._save_sheet_config(config):
            return False

        self.logger.emit(f"시트 설정 저장 완료: {self.sheet_config_path}\n", category="settings")
        self._refresh_action_button_labels()
        self.refresh_first_run_wizard()
        return True

    def _ensure_sheet_config_on_startup(self) -> None:
        self.refresh_first_run_wizard()

    def _ensure_sheet_config_before_action(self, action: str) -> bool:
        if action not in {"run", "collect-listings", "watch", "watch-images", "watch-thumbnails", "watch-upload", "upload-review", "upload-auto", "save-images"}:
            return True
        cfg = self._load_sheet_config()
        sid = self._normalize_spreadsheet_id(cfg.get("spreadsheet_id", ""))
        if self._is_valid_spreadsheet_id(sid):
            return True
        messagebox.showwarning("시트 설정 필요", "시트 ID가 없거나 잘못되었습니다. 시트 설정을 다시 입력해주세요.")
        return self.configure_sheet_settings()

    def _ensure_buyma_credentials_before_action(self, action: str) -> bool:
        if action not in {"watch-upload", "upload-review", "upload-auto"}:
            return True
        if self._has_buyma_credentials():
            return True
        messagebox.showwarning("BUYMA 계정 필요", "업로드를 실행하려면 먼저 BUYMA 계정을 저장해주세요.")
        return self.configure_buyma_credentials()

    def run_action(self, action: str) -> None:
        self._close_action_bubble()
        if self.process_manager.is_running():
            messagebox.showwarning("실행 중", "이미 작업이 실행 중입니다. 먼저 중지해주세요.")
            return
        if not self._ensure_buyma_credentials_before_action(action):
            self.logger.emit("BUYMA 계정이 없어 업로드 실행을 중단했습니다.\n", category="buyma", level="WARNING")
            return
        self.action_runner.run(action)

    def _ask_style(self) -> str | None:
        """split / banner 踰꾪듉 ?좏깮 ?앹뾽. 痍⑥냼 ??None 諛섑솚."""
        result: list[str | None] = [None]
        dlg = tk.Toplevel(self)
        dlg.title("레이아웃 선택")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.focus_set()

        tk.Label(dlg, text="썸네일 레이아웃을 선택하세요.", font=("Arial", 11), pady=10).pack()

        desc_frame = tk.Frame(dlg, padx=20, pady=4)
        desc_frame.pack()
        tk.Label(desc_frame, text="split  : 좌측 큰 사진 + 우측 2칸 + 하단 텍스트", fg="#555").pack(anchor="w")
        tk.Label(desc_frame, text="banner : 상단 타이틀 + 중앙 텍스트 + 하단 3칸", fg="#555").pack(anchor="w")
        tk.Label(desc_frame, text="auto   : split 또는 banner를 자동으로 선택", fg="#555").pack(anchor="w")

        btn_frame = tk.Frame(dlg, padx=20, pady=12)
        btn_frame.pack()

        def choose(s: str):
            result[0] = s
            dlg.destroy()

        ColorButton(btn_frame, text="split", bg="#d97706", command=lambda: choose("split"), padx=22, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=8)
        ColorButton(btn_frame, text="banner", bg="#2563eb", command=lambda: choose("banner"), padx=22, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=8)
        ColorButton(btn_frame, text="자동 선택", bg="#22c55e", command=lambda: choose("auto"), padx=22, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=8)

        cancel_frame = tk.Frame(dlg, pady=(0))
        cancel_frame.pack(pady=(0, 10))
        ColorButton(cancel_frame, text="취소", bg="#334155", command=dlg.destroy, padx=18, font=("Arial", 10, "bold")).pack()

        # Center the dialog on the launcher window.
        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"+{x}+{y}")

        self.wait_window(dlg)
        return result[0]

    def _guess_brand(self, folder_path: str) -> str:
        name = os.path.basename(folder_path.rstrip("/\\"))
        # Remove a leading folder sequence like "1. Brand Name".
        return re.sub(r"^\d+\.\s*", "", name).strip()

    def _fetch_brand_from_sheets(self, folder_path: str) -> str:
        """Fetch the brand from sheet column D using the numbered image folder."""
        try:
            folder_name = os.path.basename(folder_path.rstrip("/\\"))
            m = re.match(r"^(\d+)\.", folder_name)
            if not m:
                return ""
            idx = int(m.group(1))  # 1-based folder sequence.

            if SCRIPT_DIR not in sys.path:
                sys.path.insert(0, SCRIPT_DIR)
            import importlib
            bu = importlib.import_module("buyma_upload")

            service = bu.get_sheets_service()
            sheet_name = bu.get_sheet_name(service)
            result = service.spreadsheets().values().get(
                spreadsheetId=bu.SPREADSHEET_ID,
                range=f"'{sheet_name}'!A{bu.ROW_START}:D1000",
            ).execute()
            rows = result.get("values", [])
            # idx=1 maps to rows[0], the first data row.
            row = rows[idx - 1] if 0 < idx <= len(rows) else []
            return row[3].strip() if len(row) > 3 else ""
        except Exception:
            return ""

    def run_thumbnail_action(self) -> None:
        if self.process_manager.is_running():
            messagebox.showwarning("실행 중", "이미 작업이 실행 중입니다. 먼저 중지해주세요.")
            return

        folder = filedialog.askdirectory(
            title="?몃꽕???몄쭛???대?吏 ?대뜑 ?좏깮",
            initialdir=get_default_images_dir(),
            mustexist=True,
        )
        if not folder:
            return

        sheets_brand = self._fetch_brand_from_sheets(folder)
        default_brand = sheets_brand or self._guess_brand(folder)
        brand = simpledialog.askstring(
            "釉뚮옖?쒕챸",
            "?곷떒 釉뚮옖?쒕챸???낅젰?섏꽭??",
            initialvalue=default_brand,
            parent=self,
        )
        if brand is None:
            return
        brand = brand.strip() or default_brand or "BRAND"

        style = self._ask_style()
        if style is None:
            return
        if style == "auto":
            style = random.choice(["split", "banner"])
            self.logger.emit(f"썸네일 레이아웃 자동 선택: {style}\n", category="thumbnail")

        python_cmd = resolve_python_executable()
        footer = f"{brand} / {self._get_thumbnail_footer_suffix()}"
        command = [
            python_cmd,
            os.path.join(SCRIPT_DIR, "make_thumbnails.py"),
            folder,
            "--style",
            style,
            "--brand",
            brand,
            "--footer",
            footer,
        ]
        if self._get_thumbnail_blur_faces_enabled():
            command.append("--blur-face")
        self.action_runner.run_command(command, action="thumbnail-create", stage_key="design")

    def _drain_log_queue(self) -> None:
        try:
            while not self.log_queue.empty():
                event = self.log_queue.get_nowait()
                formatted = event.format()
                self.log_history.append(formatted)
                if len(self.log_history) > 1000:
                    self.log_history = self.log_history[-1000:]
                self.append_log(formatted)
        finally:
            self.after(100, self._drain_log_queue)

    def _drain_state_queue(self) -> None:
        try:
            pending_changes = []
            while not self.state_queue.empty():
                pending_changes.append(self.state_queue.get_nowait())
            for change in pending_changes:
                self._render_state_change(change)
        finally:
            self.after(100, self._drain_state_queue)

    def stop_action(self) -> None:
        if not self.process_manager.is_running():
            self.state.set_status("대기중")
            self.state.set_current_action("", "")
            self._set_running_ui(False)
            self._refresh_action_button_labels()
            return
        self.action_runner.stop()
        # `on_done` 콜백 도착 전에도 즉시 UI를 복구해 체감 지연을 줄인다.
        self.state.set_current_action("", "")
        self._set_running_ui(False)
        self._refresh_action_button_labels()

    def on_close(self) -> None:
        self._close_action_bubble()
        if self.auto_refresh_job:
            try:
                self.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
            finally:
                self.auto_refresh_job = None
        if self.process_manager.is_running() or any(self.process_manager.is_team_running(key) for key in self.team_watch_actions):
            if not messagebox.askyesno("종료", "실행 중인 작업을 중지하고 종료할까요?"):
                return
        self.action_runner.stop_all()
        self.destroy()

def main() -> None:
    app = AutoShopLauncher()
    app.mainloop()
