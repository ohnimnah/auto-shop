import os
import queue
import random
import re
import json
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
from services.buyma_service import BuymaCredentialService
from services.log_store import FileLogWriter
from services.system_checker import SystemChecker
from state.app_state import AppLogger, AppState, AppStateChange, LogEvent
from state.snapshot_store import StateSnapshotStore
from ui.components import ColorButton
from ui.sidebar import NAV_ITEMS, SHORTCUTS


SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_python_executable() -> str:
    """Prefer project virtualenv python, fall back to current interpreter."""
    windows_python = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "python.exe")
    mac_python = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")

    if os.path.isfile(windows_python):
        return windows_python
    if os.path.isfile(mac_python):
        return mac_python
    return sys.executable


def get_default_data_dir() -> str:
    """湲곕낯 ?고????곗씠??寃쎈줈瑜?OS蹂꾨줈 諛섑솚?쒕떎."""
    local_app_data = os.environ.get('LOCALAPPDATA', '').strip()
    if local_app_data:
        return os.path.join(local_app_data, 'auto_shop')
    return os.path.join(os.path.expanduser('~'), '.auto_shop')


def get_default_images_dir() -> str:
    """湲곕낯 ?대?吏 ???寃쎈줈瑜?諛섑솚?쒕떎."""
    env_images_dir = os.environ.get('AUTO_SHOP_IMAGES_DIR', '').strip()
    if env_images_dir:
        return os.path.abspath(os.path.expanduser(env_images_dir))
    cfg_path = os.path.join(get_default_data_dir(), "sheets_config.json")
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
        self.data_dir = get_default_data_dir()
        self.sheet_config_path = os.path.join(self.data_dir, "sheets_config.json")
        self.state = AppState()
        self.snapshot_store = StateSnapshotStore(os.path.join(self.data_dir, "launcher_state_snapshot.json"))
        self.snapshot_store.load_into(self.state)
        self.logger = AppLogger()
        self.file_log_writer = FileLogWriter(os.path.join(self.data_dir, "logs"))
        self.system_checker = SystemChecker(
            script_dir=SCRIPT_DIR,
            data_dir=self.data_dir,
            sheet_config_path=self.sheet_config_path,
            resolve_python_executable=resolve_python_executable,
            get_images_dir=self._get_configured_images_dir,
        )
        self.buyma_credentials = BuymaCredentialService(self.system_checker.get_buyma_credentials_target_path())
        self.command_builder = CommandBuilder(
            script_dir=SCRIPT_DIR,
            resolve_python_executable=resolve_python_executable,
            load_sheet_config=self.system_checker.load_sheet_config,
        )
        self.process_manager = ProcessManager(
            cwd=SCRIPT_DIR,
            env_factory=lambda: build_default_env(self.data_dir, self._get_configured_images_dir()),
        )
        self.action_runner = ActionRunner(
            script_dir=SCRIPT_DIR,
            state=self.state,
            logger=self.logger,
            process_manager=self.process_manager,
            command_builder=self.command_builder.build,
            ensure_ready=self._ensure_sheet_config_before_action,
        )
        self.logger.subscribe(self._enqueue_log)
        self.logger.subscribe(self.file_log_writer.handle)
        self.state.subscribe(self._enqueue_state)
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
        self.clock_var = tk.StringVar(value="")
        self.sheet_status_var = tk.StringVar(value=self.state.system_status.get("sheet", "점검 전"))
        self.credentials_status_var = tk.StringVar(value=self.state.system_status.get("credentials", "점검 전"))
        self.buyma_status_var = tk.StringVar(value=self.state.system_status.get("buyma", "점검 전"))
        self.images_status_var = tk.StringVar(value=self.state.system_status.get("images", "점검 전"))
        self.runtime_status_var = tk.StringVar(value=self.state.system_status.get("runtime", "점검 전"))
        self.last_check_var = tk.StringVar(value=self.state.system_status.get("last_check", "--:--:--"))
        self.pipeline_progress_vars: dict[str, tk.StringVar] = {}
        self.pipeline_canvas_widgets: dict[str, tk.Canvas] = {}
        self.quick_action_buttons: list[ColorButton] = []
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
            self._set_running_ui(bool(value))
        elif key == "today_processed":
            self.today_processed_var.set(str(value))
        elif key == "today_success":
            self.today_success_var.set(str(value))
        elif key == "today_fail":
            self.today_fail_var.set(str(value))
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
        root.grid_columnconfigure(0, minsize=226)
        root.grid_columnconfigure(1, weight=1)
        root.grid_columnconfigure(2, minsize=292)
        root.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(root, bg=self.theme["sidebar"], padx=12, pady=14, highlightbackground=self.theme["line"], highlightthickness=1)
        main = tk.Frame(root, bg=self.theme["bg"], padx=18, pady=14)
        right = tk.Frame(root, bg=self.theme["bg"], padx=0, pady=14)
        sidebar.grid(row=0, column=0, sticky="nsew")
        main.grid(row=0, column=1, sticky="nsew")
        right.grid(row=0, column=2, sticky="nsew", padx=(0, 18))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        self._build_sidebar(sidebar)
        self._build_topbar(main)
        self._build_kpi_section(main)
        self._build_pipeline_section(main)
        self._build_activity_section(main)
        self._build_table_section(main)
        self._build_quick_actions_panel(right)
        self._build_system_status_panel(right)

        footer = tk.Frame(main, bg=self.theme["bg"])
        footer.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(1, weight=1)
        tk.Label(footer, text="사용자: master", bg=self.theme["bg"], fg=self.theme["muted"], font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(footer, text="현재 시트: collection", bg=self.theme["bg"], fg=self.theme["muted"], font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w", padx=(36, 0))
        tk.Label(footer, text="자동 감시: 활성", bg=self.theme["bg"], fg=self.theme["green"], font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="e")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._refresh_system_status_labels()
        self._draw_summary_donut()
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
        for label, active in NAV_ITEMS:
            self._sidebar_button(nav, label, active)

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
        tk.Label(top, text="버전 1.0.0", bg=self.theme["bg"], fg="#c7d2e4", font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e", padx=(0, 18))
        tk.Label(top, textvariable=self.clock_var, bg=self.theme["bg"], fg="#c7d2e4", font=("Segoe UI", 9)).grid(row=0, column=2, sticky="e")

    def _build_kpi_section(self, parent: tk.Frame) -> None:
        wrap = tk.Frame(parent, bg=self.theme["bg"])
        wrap.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for idx in range(5):
            wrap.grid_columnconfigure(idx, weight=1)
        cards = [
            ("전체 상품", self.kpi_total_var, "전체 처리 대상", self.theme["blue"]),
            ("진행 중", self.kpi_running_var, "현재 처리 중", self.theme["green"]),
            ("대기 중", self.kpi_waiting_var, "다음 처리 대기", self.theme["yellow"]),
            ("완료", self.kpi_done_var, "정상 완료", self.theme["green"]),
            ("오류 / 보류", self.kpi_error_var, "오류 12 / 보류 33", self.theme["red"]),
        ]
        for col, (title, value_var, sub, accent) in enumerate(cards):
            self._kpi_card(wrap, col, title, value_var, sub, accent)

    def _build_pipeline_section(self, parent: tk.Frame) -> None:
        card = self._grid_card(parent, "파이프라인 진행 현황", row=2, pady=(0, 12))
        for idx, step in enumerate(self.state.pipeline_steps):
            self._pipeline_step(card, idx, step.key, step.title, step.metric, step.ratio, self.theme[step.color_key])

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
        )
        self.log.grid(row=1, column=0, sticky="nsew")
        self.logger.emit("1248번 상품 업로드 시작 - MAISON KITSUNE 더블 폭스 헤드 맨투맨\n", category="업로드")
        self.logger.emit("1247번 썸네일 생성 완료\n", category="썸네일")
        self.logger.emit("1247번 이미지 저장 완료 (8/8)\n", category="이미지")
        self.logger.emit("1247번 상품 정찰 완료\n", category="정찰")
        self.logger.emit("1245번 상품 업로드 실패 - 카테고리 미칭 없음\n", level="ERROR", category="업로드")
        self.log.bind("<Key>", lambda _e: "break")

        summary = self._panel(wrap, padx=12, pady=10)
        summary.grid(row=0, column=1, sticky="nsew")
        summary.grid_columnconfigure(0, weight=1)
        tk.Label(summary, text="오늘의 요약", bg=self.theme["panel"], fg=self.theme["text"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(summary, text="2025-05-23", bg="#102033", fg="#cbd5e1", font=("Segoe UI", 8), padx=10, pady=4).grid(row=0, column=1, sticky="e")
        body = tk.Frame(summary, bg=self.theme["panel"])
        body.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        self.summary_canvas = tk.Canvas(body, width=142, height=142, bg=self.theme["panel"], highlightthickness=0)
        self.summary_canvas.pack(side=tk.LEFT, padx=(0, 12))
        legend = tk.Frame(body, bg=self.theme["panel"])
        legend.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._legend_row(legend, "정상 완료", "152건 (72%)", self.theme["green"])
        self._legend_row(legend, "진행 중", "18건 (9%)", self.theme["blue"])
        self._legend_row(legend, "대기 중", "23건 (11%)", self.theme["yellow"])
        self._legend_row(legend, "오류 / 보류", "17건 (8%)", self.theme["red"])

    def _build_table_section(self, parent: tk.Frame) -> None:
        card = self._grid_card(parent, "상품 관리  (관리자 페이지)", row=4, pady=(0, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        toolbar = tk.Frame(card, bg=self.theme["panel"])
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.OptionMenu(toolbar, tk.StringVar(value="전체 상태"), "전체 상태", "진행 중", "대기 중", "완료", "오류").pack(side=tk.LEFT, padx=(0, 8))
        tk.OptionMenu(toolbar, tk.StringVar(value="전체 카테고리"), "전체 카테고리", "맨투맨", "후드티", "패딩").pack(side=tk.LEFT, padx=(0, 8))
        search = tk.Entry(toolbar, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT, width=26)
        search.insert(0, "상품명, 상품코드 검색...")
        search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 8))
        self._mini_button(toolbar, "바로고침", self._refresh_dummy_table, "#1e3350", "#294565").pack(side=tk.LEFT)

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
        scrollbar = ttk.Scrollbar(card, orient=tk.VERTICAL, command=self.product_table.yview)
        self.product_table.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self._refresh_dummy_table()

    def _build_quick_actions_panel(self, parent: tk.Frame) -> None:
        card = self._grid_card(parent, "빠른 실행", row=0, pady=(0, 12))
        self.run_btn = self._quick_button(card, "정찰 실행", "상품 정보 수집", self.theme["green"], lambda: self.run_action("run"))
        self.image_save_btn = self._quick_button(card, "이미지 저장", "이미지 다운로드", self.theme["blue"], lambda: self.run_action("save-images"))
        self.thumb_btn = self._quick_button(card, "썸네일 생성", "썸네일 일괄 제작", self.theme["purple"], self.run_thumbnail_action)
        self.upload_auto_btn = self._quick_button(card, "업로드 실행", "BUYMA 자동 업로드", self.theme["orange"], lambda: self.run_action("upload-auto"))
        self.upload_review_btn = self._quick_button(card, "실패 건 재실행", "오류 상품 재처리", "#334155", lambda: self.run_action("upload-review"))
        self.watch_btn = self._quick_button(card, "테스트 모드", "감시 실행", "#334155", lambda: self.run_action("watch"))
        self.stop_btn = self._quick_button(card, "현재 작업 중지", "실행 중인 작업 종료", self.theme["red"], self.stop_action)
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

    def _sidebar_button(self, parent: tk.Widget, text: str, active: bool) -> None:
        bg = self.theme["blue_2"] if active else self.theme["sidebar"]
        fg = "#ffffff" if active else "#d5e0ee"
        tk.Label(parent, text=text, bg=bg, fg=fg, font=("Segoe UI", 10, "bold"), anchor="w", padx=14, pady=10).pack(fill=tk.X, pady=2)

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

    def _kpi_card(self, parent: tk.Widget, col: int, title: str, value_var: tk.StringVar, sub: str, accent: str) -> None:
        card = self._panel(parent, padx=12, pady=12)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 5, 0 if col == 4 else 5))
        tk.Label(card, text=title, bg=self.theme["panel"], fg=accent, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row = tk.Frame(card, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=(6, 0))
        tk.Label(row, textvariable=value_var, bg=self.theme["panel"], fg=self.theme["text"], font=("Segoe UI", 22, "bold")).pack(side=tk.LEFT)
        tk.Label(row, text="건", bg=self.theme["panel"], fg="#cbd5e1", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=(4, 0), pady=(8, 0))
        tk.Label(card, text=sub, bg=self.theme["panel"], fg=self.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(5, 0))

    def _pipeline_step(self, parent: tk.Widget, col: int, key: str, title: str, metric: str, ratio: float, accent: str) -> None:
        bg = "#112b4f" if key == "scout" else self.theme["panel_2"]
        box = tk.Frame(parent, bg=bg, padx=12, pady=10)
        box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0 if col == 0 else 5, 0 if col == 5 else 5))
        tk.Label(box, text=title, bg=bg, fg=accent, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.pipeline_progress_vars[key] = tk.StringVar(value=f"{metric}    {int(ratio * 100)}%")
        tk.Label(box, textvariable=self.pipeline_progress_vars[key], bg=bg, fg="#f8fbff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 6))
        canvas = tk.Canvas(box, height=5, bg=bg, highlightthickness=0)
        canvas.pack(fill=tk.X)
        self.pipeline_canvas_widgets[key] = canvas
        canvas.bind("<Configure>", lambda _e, k=key, r=ratio, a=accent: self._draw_progress(k, r, a))
        self.after(50, lambda k=key, r=ratio, a=accent: self._draw_progress(k, r, a))

    def _draw_progress(self, key: str, ratio: float, accent: str) -> None:
        canvas = self.pipeline_canvas_widgets.get(key)
        if not canvas:
            return
        width = max(1, canvas.winfo_width())
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, 5, fill="#21334d", outline="")
        canvas.create_rectangle(0, 0, int(width * max(0.0, min(1.0, ratio))), 5, fill=accent, outline="")

    def _legend_row(self, parent: tk.Widget, label: str, value: str, color: str) -> None:
        row = tk.Frame(parent, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=5)
        tk.Label(row, text="■", bg=self.theme["panel"], fg=color, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        tk.Label(row, text=label, bg=self.theme["panel"], fg="#dbeafe", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(row, text=value, bg=self.theme["panel"], fg="#f8fbff", font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)

    def _draw_summary_donut(self) -> None:
        canvas = getattr(self, "summary_canvas", None)
        if not canvas:
            return
        canvas.delete("all")
        values = [(72, self.theme["green"]), (9, self.theme["blue"]), (11, self.theme["yellow"]), (8, self.theme["red"])]
        start = 90
        for value, color in values:
            extent = -360 * value / 100
            canvas.create_arc(10, 10, 132, 132, start=start, extent=extent, fill=color, outline=color)
            start += extent
        canvas.create_oval(44, 44, 98, 98, fill=self.theme["panel"], outline=self.theme["panel"])

    def _quick_button(self, parent: tk.Widget, title: str, subtitle: str, color: str, command) -> ColorButton:
        btn = ColorButton(
            parent,
            text=f"{title}\n{subtitle}",
            command=command,
            bg=color,
            fg="#ffffff",
            activebackground=color,
            anchor="w",
            justify=tk.LEFT,
            padx=16,
            pady=9,
            font=("Segoe UI", 10, "bold"),
        )
        btn.pack(fill=tk.X, pady=6)
        self.quick_action_buttons.append(btn)
        return btn

    def _system_row(self, parent: tk.Widget, label: str, value_var: tk.StringVar, value_color: str | None = None) -> None:
        row = tk.Frame(parent, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=6)
        tk.Label(row, text=label, bg=self.theme["panel"], fg="#c9d7e8", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Label(row, textvariable=value_var, bg=self.theme["panel"], fg=value_color or self.theme["green"], font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)

    def _refresh_dummy_table(self) -> None:
        if not hasattr(self, "product_table"):
            return
        for item in self.product_table.get_children():
            self.product_table.delete(item)
        for row in self.state.product_rows:
            self.product_table.insert(
                "",
                tk.END,
                values=(row.no, row.state, row.name, row.brand, row.category, row.price, row.sheet, row.updated, row.action),
            )

    def _refresh_system_status_labels(self) -> None:
        self.state.set_system_status(self.system_checker.collect_status())
        self.refresh_first_run_wizard()

    def _update_clock(self) -> None:
        self.clock_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.after(1000, self._update_clock)

    def _show_log_folder_hint(self) -> None:
        messagebox.showinfo("로그 폴더", f"현재 작업 폴더:\n{SCRIPT_DIR}")

    def _show_program_info(self) -> None:
        messagebox.showinfo("프로그램 정보", "물류 자동화 런처 1.0.0\nPython 기반 운영 대시보드")

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
            return
        self.run_action("watch")

    def _toggle_team_watch(self, team_key: str) -> None:
        if team_key not in self.team_watch_actions:
            return
        if self.team_watch_enabled.get(team_key):
            self._stop_team_watch(team_key)
        else:
            self._start_team_watch(team_key)

    def _start_team_watch(self, team_key: str) -> None:
        if team_key not in self.team_watch_actions:
            return
        if self.team_watch_enabled.get(team_key):
            return
        self.action_runner.start_team_watch(team_key)
        self._schedule_team_watch_tick(team_key, delay_ms=20000)

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
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def clear_log(self) -> None:
        self.log.delete("1.0", tk.END)

    def _set_running_ui(self, running: bool) -> None:
        normal = tk.DISABLED if running else tk.NORMAL
        self.run_btn.configure(state=normal)
        self.watch_btn.configure(state=normal)
        self.image_save_btn.configure(state=normal)
        self.upload_review_btn.configure(state=normal)
        self.upload_auto_btn.configure(state=normal)
        self.thumb_btn.configure(state=normal)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _get_sheet_label_prefix(self) -> str:
        return "정찰팀"

    def _refresh_action_button_labels(self) -> None:
        self.run_btn.configure(text="정찰 실행\n상품 정보 수집")
        self.watch_btn.configure(text="테스트 모드\n감시 실행")
        self.image_save_btn.configure(text="이미지 저장\n이미지 다운로드")

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

    def _save_sheet_config(self, config: dict) -> bool:
        try:
            return self.system_checker.save_sheet_config(config)
        except Exception as e:
            messagebox.showerror("저장 실패", f"시트 설정 저장 실패: {e}")
            return False

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

    def run_action(self, action: str) -> None:
        self._close_action_bubble()
        if self.process_manager.is_running():
            messagebox.showwarning("실행 중", "이미 작업이 실행 중입니다. 먼저 중지해주세요.")
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

        # ?붾㈃ 以묒븰 諛곗튂
        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"+{x}+{y}")

        self.wait_window(dlg)
        return result[0]

    def _guess_brand(self, folder_path: str) -> str:
        name = os.path.basename(folder_path.rstrip("/\\"))
        # "1. Brand Name" ?뺥깭硫?踰덊샇 ?묐몢???쒓굅
        return re.sub(r"^\d+\.\s*", "", name).strip()

    def _fetch_brand_from_sheets(self, folder_path: str) -> str:
        """?대뜑 踰덊샇濡??쒗듃 D???곷Ц 釉뚮옖????議고쉶. ?ㅽ뙣 ??鍮?臾몄옄??諛섑솚."""
        try:
            folder_name = os.path.basename(folder_path.rstrip("/\\"))
            m = re.match(r"^(\d+)\.", folder_name)
            if not m:
                return ""
            idx = int(m.group(1))  # 1-based ?대뜑 踰덊샇

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
            # idx=1 ??rows[0] (泥?踰덉㎏ ?곗씠????
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
        footer = f"{brand} / angduss k-closet"
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
            "--blur-face",
        ]
        self.action_runner.run_command(command, action="thumbnail-create", stage_key="design")

    def _drain_log_queue(self) -> None:
        try:
            while not self.log_queue.empty():
                event = self.log_queue.get_nowait()
                self.append_log(event.format())
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
            return
        self.action_runner.stop()

    def on_close(self) -> None:
        self._close_action_bubble()
        if self.process_manager.is_running():
            if not messagebox.askyesno("醫낅즺", "?ㅽ뻾 以묒씤 ?묒뾽??以묒??섍퀬 醫낅즺?좉퉴??"):
                return
        self.action_runner.stop_all()
        self.destroy()


def main() -> None:
    os.chdir(SCRIPT_DIR)
    app = AutoShopLauncher()
    app.mainloop()


if __name__ == "__main__":
    main()
