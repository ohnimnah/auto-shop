import os
import queue
import random
import re
import base64
import json
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import simpledialog
from tkinter.scrolledtext import ScrolledText


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def resolve_python_executable() -> str:
    """Prefer project virtualenv python, fall back to current interpreter."""
    windows_python = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "python.exe")
    mac_python = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")

    if os.path.isfile(windows_python):
        return windows_python
    if os.path.isfile(mac_python):
        return mac_python
    return sys.executable


def build_unbuffered_python_command(script_path: str, *args: str) -> list[str]:
    """Run Python in unbuffered mode so launcher log updates are real-time."""
    python_cmd = resolve_python_executable()
    return [python_cmd, "-u", script_path, *args]


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

        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.data_dir = get_default_data_dir()
        self.sheet_config_path = os.path.join(self.data_dir, "sheets_config.json")
        self.current_action: str | None = None
        self.current_stage_key: str | None = None
        self.today_processed = 0
        self.today_success = 0
        self.today_fail = 0
        self.today_processed_var = tk.StringVar(value="0")
        self.today_success_var = tk.StringVar(value="0")
        self.today_fail_var = tk.StringVar(value="0")
        self.wizard_summary_var = tk.StringVar(value="첫 실행 준비를 확인하세요.")
        self.wizard_status_vars: dict[str, tk.StringVar] = {
            "runtime": tk.StringVar(value="확인 전"),
            "credentials": tk.StringVar(value="확인 전"),
            "sheet": tk.StringVar(value="확인 전"),
            "mosaic": tk.StringVar(value="확인 전"),
            "buyma": tk.StringVar(value="확인 전"),
        }
        self.stage_vars: dict[str, tk.StringVar] = {
            "scout": tk.StringVar(value="대기"),
            "assets": tk.StringVar(value="대기"),
            "design": tk.StringVar(value="대기"),
            "sales": tk.StringVar(value="대기"),
        }
        self.stage_card_widgets: dict[str, tk.Widget] = {}
        self.action_bubble: tk.Toplevel | None = None
        self.team_watch_actions: dict[str, str] = {
            "assets": "watch-images",
            "design": "watch-thumbnails",
            "sales": "watch-upload",
        }
        self.team_watch_enabled: dict[str, bool] = {k: False for k in self.team_watch_actions}
        self.team_watch_jobs: dict[str, str] = {}
        self.team_processes: dict[str, subprocess.Popen] = {}

        self._build_ui()
        self._refresh_action_button_labels()
        self.after(100, self._drain_log_queue)
        self.after(250, self._ensure_sheet_config_on_startup)

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
        self.configure(bg="#0c1224")

        shell = tk.Frame(self, bg="#0c1224", padx=14, pady=12)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(2, weight=1)

        header = tk.Frame(shell, bg="#0c1224")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="AUTO SHOP OPS COMMAND",
            bg="#0c1224",
            fg="#eef3ff",
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.status_var = tk.StringVar(value="대기중")
        tk.Label(
            header,
            textvariable=self.status_var,
            bg="#0c1224",
            fg="#5ef2c2",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=1, sticky="e")

        stats = tk.Frame(shell, bg="#0c1224")
        stats.grid(row=1, column=0, sticky="ew", pady=(12, 10))
        for idx in range(3):
            stats.grid_columnconfigure(idx, weight=1)
        self._build_stat_card(stats, 0, "오늘 처리", self.today_processed_var, "#28a7ff")
        self._build_stat_card(stats, 1, "성공", self.today_success_var, "#2ecb84")
        self._build_stat_card(stats, 2, "실패", self.today_fail_var, "#ff5f7a")

        board = tk.Frame(shell, bg="#0c1224")
        board.grid(row=2, column=0, sticky="nsew")
        board.grid_columnconfigure(0, weight=3)
        board.grid_columnconfigure(1, weight=4)
        board.grid_columnconfigure(2, weight=5)
        board.grid_rowconfigure(0, weight=1)

        left = tk.Frame(board, bg="#121a33", highlightbackground="#2b3760", highlightthickness=1)
        center = tk.Frame(board, bg="#101834", padx=12, pady=12, highlightbackground="#2b3760", highlightthickness=1)
        right = tk.Frame(board, bg="#11182f", padx=12, pady=12, highlightbackground="#2b3760", highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=2, sticky="nsew")

        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)
        left_canvas = tk.Canvas(left, bg="#121a33", highlightthickness=0, bd=0)
        left_scrollbar = tk.Scrollbar(left, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scrollbar.grid(row=0, column=1, sticky="ns")

        left_content = tk.Frame(left_canvas, bg="#121a33", padx=12, pady=12)
        left_window = left_canvas.create_window((0, 0), window=left_content, anchor="nw")

        def _sync_left_scrollregion(_event=None) -> None:
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _resize_left_content(_event=None) -> None:
            left_canvas.itemconfigure(left_window, width=left_canvas.winfo_width())

        def _on_left_mousewheel(event) -> str | None:
            if event.delta == 0:
                return None
            left_canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        left_content.bind("<Configure>", _sync_left_scrollregion)
        left_canvas.bind("<Configure>", _resize_left_content)
        left_canvas.bind("<Enter>", lambda _e: left_canvas.bind_all("<MouseWheel>", _on_left_mousewheel))
        left_canvas.bind("<Leave>", lambda _e: left_canvas.unbind_all("<MouseWheel>"))

        tk.Label(left_content, text="작전 패널", bg="#121a33", fg="#f7fbff", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 10))
        tk.Label(
            left_content,
            text="사무실 직원을 클릭하면\n말풍선으로 작업 옵션이 열립니다.",
            bg="#121a33",
            fg="#9fb1dd",
            justify=tk.LEFT,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 10))
        self.stop_btn = tk.Button(left_content, text="긴급 중지", command=self.stop_action, state=tk.DISABLED, bg="#5a2330", fg="#ffeef2", relief=tk.FLAT, activebackground="#6d2b3b")
        self.stop_btn.pack(fill=tk.X, pady=(0, 8), ipady=7)

        self._build_first_run_wizard(left_content)

        # Keep remaining action button objects for existing run/disable logic compatibility.
        hidden_actions = tk.Frame(left_content, bg="#121a33")
        self.run_btn = tk.Button(hidden_actions, text="정찰팀 시작", command=lambda: self.run_action("run"))
        self.watch_btn = tk.Button(hidden_actions, text="정찰팀 감시", command=lambda: self.run_action("watch"))
        self.image_save_btn = tk.Button(hidden_actions, text="자료팀 저장", command=lambda: self.run_action("save-images"))
        self.thumb_btn = tk.Button(hidden_actions, text="썸네일 만들기", command=self.run_thumbnail_action)
        self.upload_review_btn = tk.Button(hidden_actions, text="검토 후 업로드", command=lambda: self.run_action("upload-review"))
        self.upload_auto_btn = tk.Button(hidden_actions, text="한 번 자동 업로드", command=lambda: self.run_action("upload-auto"))

        tk.Label(center, text="작전 사무실", bg="#101834", fg="#f7fbff", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 10))
        self._build_stage_card(center, "정찰팀", "무신사 크롤링", "scout", "#2a67cc")
        self._build_stage_card(center, "자료팀", "이미지 저장", "assets", "#2f9f65")
        self._build_stage_card(center, "디자인팀", "썸네일 작업", "design", "#c0882e")
        self._build_stage_card(center, "판매팀", "BUYMA 업로드", "sales", "#2f78a5")

        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        tk.Label(right, text="전투 로그", bg="#11182f", fg="#f7fbff", font=("Consolas", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.log = ScrolledText(
            right,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#0a0f20",
            fg="#d9ecff",
            insertbackground="#d9ecff",
            relief=tk.FLAT,
            borderwidth=0,
        )
        self.log.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        self.log.insert(tk.END, "실행 로그가 여기에 표시됩니다.\n")
        self.log.configure(state=tk.DISABLED)

        bottom_bar = tk.Frame(right, bg="#11182f")
        bottom_bar.grid(row=2, column=0, sticky="ew")
        tk.Button(bottom_bar, text="로그 지우기", command=self.clear_log, bg="#2b385e", fg="#eff4ff", relief=tk.FLAT, activebackground="#364878").pack(side=tk.LEFT)
        tk.Button(bottom_bar, text="종료", command=self.on_close, bg="#5a2330", fg="#ffeef2", relief=tk.FLAT, activebackground="#6d2b3b").pack(side=tk.RIGHT)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

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
        if self.process and self.process.poll() is None:
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
        return bool(self.current_action == "watch" and self.process and self.process.poll() is None)

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
        self.team_watch_enabled[team_key] = True
        self._set_stage_status(team_key, "감시중")
        self.append_log(f"[{team_key}] 팀 감시 시작 (독립 워커)\n")
        self._start_team_watch_process(team_key)
        self._schedule_team_watch_tick(team_key, delay_ms=20000)

    def _stop_team_watch(self, team_key: str) -> None:
        if team_key not in self.team_watch_actions:
            return
        self.team_watch_enabled[team_key] = False
        job_id = self.team_watch_jobs.pop(team_key, None)
        if job_id:
            try:
                self.after_cancel(job_id)
            except Exception:
                pass
        if self.stage_vars.get(team_key) and self.stage_vars[team_key].get() == "감시중":
            self._set_stage_status(team_key, "대기")
        proc = self.team_processes.pop(team_key, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.append_log(f"[{team_key}] 팀 감시 중지\n")

    def _schedule_team_watch_tick(self, team_key: str, delay_ms: int = 20000) -> None:
        if not self.team_watch_enabled.get(team_key, False):
            return
        job_id = self.after(delay_ms, lambda k=team_key: self._team_watch_tick(k))
        self.team_watch_jobs[team_key] = job_id

    def _team_watch_tick(self, team_key: str) -> None:
        self.team_watch_jobs.pop(team_key, None)
        if not self.team_watch_enabled.get(team_key, False):
            return

        proc = self.team_processes.get(team_key)
        if not proc or proc.poll() is not None:
            self._start_team_watch_process(team_key)
        self._schedule_team_watch_tick(team_key)

    def _start_team_watch_process(self, team_key: str) -> bool:
        action = self.team_watch_actions.get(team_key)
        if not action:
            return False
        if not self._ensure_sheet_config_before_action(action):
            return False
        command = self._build_command(action)
        self.append_log(f"[{team_key}] 워커 실행: {' '.join(command)}\n")
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["AUTO_SHOP_IMAGES_DIR"] = self._get_configured_images_dir()
            proc = subprocess.Popen(
                command,
                cwd=SCRIPT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:
            self.append_log(f"[{team_key}] 워커 실행 실패: {exc}\n")
            self._set_stage_status(team_key, "실패")
            return False
        self.team_processes[team_key] = proc
        self._set_stage_status(team_key, "감시중")
        thread = threading.Thread(target=self._read_team_output, args=(team_key, proc), daemon=True)
        thread.start()
        return True

    def _read_team_output(self, team_key: str, proc: subprocess.Popen) -> None:
        if not proc.stdout:
            return
        for line in proc.stdout:
            self.log_queue.put(f"[{team_key}] {line}")
        return_code = proc.wait()
        self.log_queue.put(f"[{team_key}] 워커 종료 (code: {return_code})\n")
        self.log_queue.put(f"__TEAM_PROCESS_DONE__:{team_key}:{return_code}")

    def _set_stage_status(self, key: str, text: str) -> None:
        var = self.stage_vars.get(key)
        if var is not None:
            var.set(text)

    def _reset_stage_statuses(self) -> None:
        for key in self.stage_vars:
            if self.team_watch_enabled.get(key, False):
                self._set_stage_status(key, "감시중")
            else:
                self._set_stage_status(key, "대기")
        self.current_stage_key = None

    def _sync_stage_from_action(self, action: str) -> None:
        self.current_action = action
        if action in {"run", "watch"}:
            self.current_stage_key = "scout"
        elif action == "save-images":
            self.current_stage_key = "assets"
        elif action in {"upload-review", "upload-auto"}:
            self.current_stage_key = "sales"
        else:
            self.current_stage_key = None
        if self.current_stage_key:
            self._set_stage_status(self.current_stage_key, "진행중")

    def _mark_current_stage_done(self, success: bool) -> None:
        if self.current_stage_key:
            self._set_stage_status(self.current_stage_key, "완료" if success else "실패")

    def _update_stage_from_log(self, msg: str) -> None:
        text = (msg or "").lower()
        if not text:
            return
        if "main.py" in text and "--download-images" in text:
            self.current_stage_key = "assets"
            self._set_stage_status("assets", "진행중")
        elif "main.py" in text and "--make-thumbnails" in text:
            self.current_stage_key = "design"
            self._set_stage_status("design", "진행중")
        elif "make_thumbnails.py" in text:
            self.current_stage_key = "design"
            self._set_stage_status("design", "진행중")
        elif "buyma_upload.py" in text:
            self.current_stage_key = "sales"
            self._set_stage_status("sales", "진행중")
        elif "main.py" in text and "--watch" not in text and "--download-images" not in text and "--make-thumbnails" not in text:
            self.current_stage_key = "scout"
            self._set_stage_status("scout", "진행중")

    def _update_stat_cards(self) -> None:
        self.today_processed_var.set(str(self.today_processed))
        self.today_success_var.set(str(self.today_success))
        self.today_fail_var.set(str(self.today_fail))

    def append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _build_command(self, action: str) -> list[str]:
        if action == "install":
            if os.name == "nt":
                script = os.path.join(SCRIPT_DIR, "bootstrap_windows.ps1")
                return [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script,
                ]
            script = os.path.join(SCRIPT_DIR, "bootstrap_mac.sh")
            return ["bash", script]

        if action == "run":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"))
        if action == "watch":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--watch")
        if action == "watch-images":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--watch", "--download-images")
        if action == "watch-thumbnails":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--watch", "--make-thumbnails")
        if action == "watch-upload":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "buyma_upload.py"), "--watch", "--mode", "auto")
        if action == "save-images":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--download-images")
        if action == "upload-review":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "buyma_upload.py"), "--mode", "review")
        if action == "upload-auto":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "buyma_upload.py"), "--mode", "auto")

        raise ValueError(f"Unknown action: {action}")

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
        prefix = self._get_sheet_label_prefix()
        self.run_btn.configure(text=f"{prefix} 시작")
        self.watch_btn.configure(text=f"{prefix} 감시")
        self.image_save_btn.configure(text="자료팀 저장")

    def _get_credentials_target_path(self) -> str:
        return os.path.join(self.data_dir, "credentials.json")

    def _get_buyma_credentials_target_path(self) -> str:
        return os.path.join(self.data_dir, "buyma_credentials.json")

    def _get_available_credentials_path(self) -> str:
        target = self._get_credentials_target_path()
        if os.path.exists(target):
            return target
        legacy = os.path.join(SCRIPT_DIR, "credentials.json")
        if os.path.exists(legacy):
            return legacy
        return ""

    def _has_buyma_credentials(self) -> bool:
        path = self._get_buyma_credentials_target_path()
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            email = base64.b64decode(str(data.get("email", "")).encode()).decode().strip()
            password = base64.b64decode(str(data.get("password", "")).encode()).decode().strip()
            return bool(email and password)
        except Exception:
            return False

    def _load_buyma_email(self) -> str:
        path = self._get_buyma_credentials_target_path()
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return base64.b64decode(str(data.get("email", "")).encode()).decode().strip()
        except Exception:
            return ""

    def _has_ready_runtime(self) -> bool:
        python_cmd = resolve_python_executable()
        if not python_cmd:
            return False
        if os.path.isfile(python_cmd) or shutil.which(python_cmd):
            try:
                result = subprocess.run(
                    [
                        python_cmd,
                        "-c",
                        "import selenium, PIL, bs4, googleapiclient, google.oauth2, webdriver_manager, numpy, cv2",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=20,
                    check=False,
                )
                return result.returncode == 0
            except Exception:
                return False
        return False

    def _get_mosaic_runtime_state(self) -> str:
        python_cmd = resolve_python_executable()
        if not python_cmd:
            return "missing"
        if not (os.path.isfile(python_cmd) or shutil.which(python_cmd)):
            return "missing"
        try:
            result = subprocess.run(
                [
                    python_cmd,
                    "-c",
                    (
                        "import os; "
                        "import cv2; "
                        "p=cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'; "
                        "c=cv2.CascadeClassifier(p); "
                        "state='ready' if os.path.exists(p) and not c.empty() else 'installed'; "
                        "print(state)"
                    ),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=20,
                check=False,
            )
            if result.returncode != 0:
                return "missing"
            state = (result.stdout or "").strip().lower()
            if state in {"ready", "installed"}:
                return state
            return "missing"
        except Exception:
            return "missing"

    def _has_credentials_file(self) -> bool:
        return bool(self._get_available_credentials_path())

    def _has_valid_sheet_config(self) -> bool:
        cfg = self._load_sheet_config()
        sid = self._normalize_spreadsheet_id(cfg.get("spreadsheet_id", ""))
        return self._is_valid_spreadsheet_id(sid) and bool((cfg.get("sheet_name") or "").strip())

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
        current_email = self._load_buyma_email()
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
            os.makedirs(self.data_dir, exist_ok=True)
            payload = {
                "email": base64.b64encode(email.encode()).decode(),
                "password": base64.b64encode(password.encode()).decode(),
            }
            target_path = self._get_buyma_credentials_target_path()
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.append_log(f"BUYMA 계정 저장 완료: {target_path}\n")
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
            self.append_log(f"자격증명 파일 연결 완료: {target_path}\n")
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
            self.append_log(f"Google Sheets 연결 테스트 성공: {title}\n")
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
        if self.process and self.process.poll() is None:
            messagebox.showwarning("실행 중", "이미 작업이 실행 중입니다. 먼저 중지해주세요.")
            return
        if not messagebox.askyesno(
            "샘플 1건 실행",
            "현재 시트 기준으로 첫 작업 1건을 확인해보려면 정찰팀 시작을 실행합니다.\n계속할까요?",
        ):
            return
        self.run_action("run")

    def _load_sheet_config(self) -> dict:
        try:
            if not os.path.exists(self.sheet_config_path):
                return {}
            with open(self.sheet_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _get_configured_images_dir(self) -> str:
        cfg = self._load_sheet_config()
        configured = (cfg.get("images_dir") or "").strip()
        if configured:
            return os.path.abspath(os.path.expanduser(configured))
        return get_default_images_dir()

    def _save_sheet_config(self, config: dict) -> bool:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.sheet_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
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

        self.append_log(f"이미지 저장 경로 설정 완료: {selected_dir}\n")
        messagebox.showinfo("이미지 경로 저장", f"앞으로 이미지 저장 기본 경로로 사용합니다.\n{selected_dir}")
        return True

    def _has_sheet_config(self) -> bool:
        cfg = self._load_sheet_config()
        return bool((cfg.get("spreadsheet_id") or "").strip())

    def _normalize_spreadsheet_id(self, raw_value: str) -> str:
        """입력값에서 Spreadsheet ID를 추출하고 정리한다."""
        value = (raw_value or "").strip()
        if not value:
            return ""

        # 전체 URL이 들어오면 /d/<id>/ 부분에서 ID를 추출한다.
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
        if m:
            return m.group(1)

        # d/<id>, /d/<id> 형태도 허용한다.
        m = re.search(r"(?:^|/)d/([a-zA-Z0-9-_]+)", value)
        if m:
            return m.group(1)

        return value

    def _is_valid_spreadsheet_id(self, spreadsheet_id: str) -> bool:
        sid = (spreadsheet_id or "").strip()
        if not sid:
            return False
        if "@" in sid:
            return False
        # 구글 시트 ID는 보통 영문/숫자/-/_ 조합의 긴 문자열이다.
        return bool(re.fullmatch(r"[a-zA-Z0-9-_]{20,}", sid))

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

        config = {
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "sheet_gids": gids,
            "row_start": 2,
            "images_dir": (current.get("images_dir") or "").strip(),
        }
        if not self._save_sheet_config(config):
            return False

        self.append_log(f"시트 설정 저장 완료: {self.sheet_config_path}\n")
        self._refresh_action_button_labels()
        self.refresh_first_run_wizard()
        return True

    def _ensure_sheet_config_on_startup(self) -> None:
        self.refresh_first_run_wizard()

    def _ensure_sheet_config_before_action(self, action: str) -> bool:
        if action not in {"run", "watch", "watch-images", "watch-thumbnails", "watch-upload", "upload-review", "upload-auto", "save-images"}:
            return True
        cfg = self._load_sheet_config()
        sid = self._normalize_spreadsheet_id(cfg.get("spreadsheet_id", ""))
        if self._is_valid_spreadsheet_id(sid):
            return True
        messagebox.showwarning("시트 설정 필요", "시트 ID가 없거나 잘못되었습니다. 시트 설정을 다시 입력해주세요.")
        return self.configure_sheet_settings()

    def _start_command(self, command: list[str]) -> bool:
        self.append_log("\n" + "=" * 70 + "\n")
        self.append_log(f"실행: {' '.join(command)}\n")

        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["AUTO_SHOP_IMAGES_DIR"] = self._get_configured_images_dir()
            self.process = subprocess.Popen(
                command,
                cwd=SCRIPT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:
            self.append_log(f"실행 실패: {exc}\n")
            self.status_var.set("실행 실패")
            self._mark_current_stage_done(False)
            return False

        self.status_var.set("작전 진행중")
        self._set_running_ui(True)
        thread = threading.Thread(target=self._read_output, daemon=True)
        thread.start()
        return True

    def _start_command_in_terminal(self, action: str) -> None:
        """?곕???李쎌뿉??紐낅졊???ㅽ뻾?쒕떎 (?ъ슜???낅젰???꾩슂??寃쎌슦)."""
        command = self._build_command(action)
        cmd_str = subprocess.list2cmdline(command)
        
        try:
            if os.name == "nt":  # Windows
                # ?곕???李??좎??섎㈃???ㅽ뻾: cmd /k "python ... && pause"
                terminal_cmd = f'cmd /k "{cmd_str} & pause"'
                subprocess.Popen(terminal_cmd, shell=True, cwd=SCRIPT_DIR)
            else:  # Mac/Linux
                # Mac: open -a Terminal?쇰줈 ?ㅽ뻾
                import subprocess as sp
                script = f"cd '{SCRIPT_DIR}' && {cmd_str} && read -p 'Press enter to exit...'"
                sp.Popen(["open", "-a", "Terminal", "-W"], input=script.encode())
        except Exception as exc:
            messagebox.showerror("?ㅽ뻾 ?ㅽ뙣", f"?곕????ㅽ뻾 ?ㅽ뙣: {exc}")

    def _start_sequence_in_terminal(self, commands: list[list[str]]) -> None:
        try:
            if os.name == "nt":
                cmd_parts = [subprocess.list2cmdline(cmd) for cmd in commands]
                terminal_cmd = f'cmd /k "{" && ".join(cmd_parts)} & pause"'
                subprocess.Popen(terminal_cmd, shell=True, cwd=SCRIPT_DIR)
            else:
                import shlex
                import subprocess as sp
                script = f"cd '{SCRIPT_DIR}' && {' && '.join(shlex.join(cmd) for cmd in commands)} && read -p 'Press enter to exit...'"
                sp.Popen(["open", "-a", "Terminal", "-W"], input=script.encode())
        except Exception as exc:
            messagebox.showerror("?ㅽ뻾 ?ㅽ뙣", f"?곗냽 ?ㅽ뻾 ?ㅽ뙣: {exc}")

    def run_action(self, action: str) -> None:
        self._close_action_bubble()
        if self.process and self.process.poll() is None:
            messagebox.showwarning("실행 중", "이미 작업이 실행 중입니다. 먼저 중지해주세요.")
            return

        if not self._ensure_sheet_config_before_action(action):
            return
        self._reset_stage_statuses()
        self._sync_stage_from_action(action)
        self.status_var.set("작전 준비중")

        # BUYMA ?낅줈???≪뀡? 釉뚮씪?곗?/?낅젰 ?뺤씤???꾪빐 ?곕???李쎌뿉??吏곸젒 ?ㅽ뻾
        if action in {"upload-review", "upload-auto"}:
            self.status_var.set("터미널 업로드 실행")
            self._start_command_in_terminal(action)
            return

        command = self._build_command(action)
        self._start_command(command)

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

        tk.Button(btn_frame, text="split", width=14, bg="#fff4e5",
                  font=("Arial", 10, "bold"), command=lambda: choose("split")).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="banner", width=14, bg="#e8f0fe",
                  font=("Arial", 10, "bold"), command=lambda: choose("banner")).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="자동 선택", width=14, bg="#e8ffe8",
                  font=("Arial", 10, "bold"), command=lambda: choose("auto")).pack(side=tk.LEFT, padx=8)

        cancel_frame = tk.Frame(dlg, pady=(0))
        cancel_frame.pack(pady=(0, 10))
        tk.Button(cancel_frame, text="痍⑥냼", width=10, command=dlg.destroy).pack()

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
        if self.process and self.process.poll() is None:
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
            self.append_log(f"썸네일 레이아웃 자동 선택: {style}\n")

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
        self.current_action = "thumbnail-create"
        self.current_stage_key = "design"
        self._set_stage_status("design", "진행중")
        self._start_command(command)

    def _read_output(self) -> None:
        if not self.process or not self.process.stdout:
            return

        for line in self.process.stdout:
            self.log_queue.put(line)

        return_code = self.process.wait()
        self.log_queue.put(f"\n작업 종료 (code: {return_code})\n")
        self.log_queue.put(f"__PROCESS_DONE__:{return_code}")

    def _drain_log_queue(self) -> None:
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            if msg.startswith("__TEAM_PROCESS_DONE__:"):
                team_key = ""
                return_code = 1
                try:
                    _, team_key, code_text = msg.split(":", 2)
                    return_code = int(code_text)
                except Exception:
                    return_code = 1
                proc = self.team_processes.get(team_key)
                if proc and proc.poll() is not None:
                    self.team_processes.pop(team_key, None)
                if self.team_watch_enabled.get(team_key, False):
                    self._set_stage_status(team_key, "감시중")
                else:
                    self._set_stage_status(team_key, "대기")
            elif msg.startswith("__PROCESS_DONE__:"):
                return_code = 1
                try:
                    return_code = int(msg.split(":", 1)[1])
                except Exception:
                    return_code = 1
                success = return_code == 0
                self.today_processed += 1
                if success:
                    self.today_success += 1
                else:
                    self.today_fail += 1
                self._update_stat_cards()
                self._mark_current_stage_done(success)
                if self.current_stage_key and self.team_watch_enabled.get(self.current_stage_key, False):
                    self._set_stage_status(self.current_stage_key, "감시중")
                self._set_running_ui(False)
                self.status_var.set("대기중")
                self.process = None
            else:
                self._update_stage_from_log(msg)
                self.append_log(msg)

        self.after(100, self._drain_log_queue)

    def stop_action(self) -> None:
        if not self.process or self.process.poll() is not None:
            self.status_var.set("대기중")
            self._set_running_ui(False)
            return

        self.append_log("\n중지 요청 전송...\n")
        self._mark_current_stage_done(False)
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass

    def on_close(self) -> None:
        self._close_action_bubble()
        for team_key in list(self.team_watch_enabled.keys()):
            self._stop_team_watch(team_key)
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("醫낅즺", "?ㅽ뻾 以묒씤 ?묒뾽??以묒??섍퀬 醫낅즺?좉퉴??"):
                return
            self.stop_action()
        self.destroy()


def main() -> None:
    os.chdir(SCRIPT_DIR)
    app = AutoShopLauncher()
    app.mainloop()


if __name__ == "__main__":
    main()
