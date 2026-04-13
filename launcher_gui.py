import os
import queue
import random
import re
import json
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
        self.stage_vars: dict[str, tk.StringVar] = {
            "leader": tk.StringVar(value="대기"),
            "scout": tk.StringVar(value="대기"),
            "assets": tk.StringVar(value="대기"),
            "design": tk.StringVar(value="대기"),
            "sales": tk.StringVar(value="대기"),
        }
        self.stage_card_widgets: dict[str, tk.Widget] = {}
        self.action_bubble: tk.Toplevel | None = None
        self.team_watch_actions: dict[str, str] = {
            "scout": "watch-crawler",
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

        left = tk.Frame(board, bg="#121a33", padx=12, pady=12, highlightbackground="#2b3760", highlightthickness=1)
        center = tk.Frame(board, bg="#101834", padx=12, pady=12, highlightbackground="#2b3760", highlightthickness=1)
        right = tk.Frame(board, bg="#11182f", padx=12, pady=12, highlightbackground="#2b3760", highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=2, sticky="nsew")

        tk.Label(left, text="작전 패널", bg="#121a33", fg="#f7fbff", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 10))
        tk.Label(
            left,
            text="사무실 직원을 클릭하면\n말풍선으로 작업 옵션이 열립니다.",
            bg="#121a33",
            fg="#9fb1dd",
            justify=tk.LEFT,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 10))
        self.stop_btn = tk.Button(left, text="긴급 중지", command=self.stop_action, state=tk.DISABLED, bg="#5a2330", fg="#ffeef2", relief=tk.FLAT, activebackground="#6d2b3b")
        self.stop_btn.pack(fill=tk.X, pady=(0, 8), ipady=7)

        self.install_btn = tk.Button(left, text="필수 설치", command=lambda: self.run_action("install"), bg="#1f315d", fg="#f3f6ff", relief=tk.FLAT, activebackground="#28417c")
        self.setup_btn = tk.Button(left, text="초기 설정", command=lambda: self.run_action("setup"), bg="#1f315d", fg="#f3f6ff", relief=tk.FLAT, activebackground="#28417c")
        self.sheet_cfg_btn = tk.Button(left, text="시트 설정", command=self.configure_sheet_settings, bg="#284f79", fg="#ebf6ff", relief=tk.FLAT, activebackground="#33659b")
        self.install_btn.pack(fill=tk.X, pady=2, ipady=5)
        self.setup_btn.pack(fill=tk.X, pady=2, ipady=5)
        self.sheet_cfg_btn.pack(fill=tk.X, pady=(2, 8), ipady=5)

        # Keep remaining action button objects for existing run/disable logic compatibility.
        hidden_actions = tk.Frame(left, bg="#121a33")
        self.full_auto_btn = tk.Button(hidden_actions, text="풀 오토 실행", command=lambda: self.run_action("full-auto-upload"))
        self.run_btn = tk.Button(hidden_actions, text="정찰팀 시작", command=lambda: self.run_action("run"))
        self.watch_btn = tk.Button(hidden_actions, text="정찰팀 감시", command=lambda: self.run_action("watch"))
        self.image_save_btn = tk.Button(hidden_actions, text="자료팀 저장", command=lambda: self.run_action("save-images"))
        self.thumb_btn = tk.Button(hidden_actions, text="디자인팀 수동", command=self.run_thumbnail_action)
        self.thumb_auto_btn = tk.Button(hidden_actions, text="디자인팀 자동", command=self.run_thumbnail_auto_action)
        self.thumb_batch_btn = tk.Button(hidden_actions, text="디자인팀 배치", command=lambda: self.run_action("make-thumbnails"))
        self.upload_review_btn = tk.Button(hidden_actions, text="판매팀 확인", command=lambda: self.run_action("upload-review"))
        self.upload_auto_btn = tk.Button(hidden_actions, text="판매팀 자동", command=lambda: self.run_action("upload-auto"))

        tk.Label(center, text="작전 사무실", bg="#101834", fg="#f7fbff", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 10))
        self._build_stage_card(center, "작전 팀장", "필수 설치 / 초기 설정 / 시트 / 풀 오토", "leader", "#8f6cff")
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
            "leader": ("#d7b58a", "#6b54b8", "#1f1a3d"),
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
        if team_key == "leader":
            return [
                ("필수 설치", "install"),
                ("초기 설정", "setup"),
                ("시트 설정", "sheet-config"),
                ("풀 오토 실행", "full-auto-upload"),
            ]
        if team_key == "scout":
            return [
                ("정찰 시작", "run"),
                ("정찰 감시", "watch"),
                (watch_label, f"team-watch-toggle:{team_key}"),
            ]
        if team_key == "assets":
            return [
                ("이미지 저장", "save-images"),
                (watch_label, f"team-watch-toggle:{team_key}"),
            ]
        if team_key == "design":
            return [
                ("썸네일 수동", "thumbnail-manual"),
                ("썸네일 자동", "thumbnail-auto"),
                ("썸네일 배치", "make-thumbnails"),
                (watch_label, f"team-watch-toggle:{team_key}"),
            ]
        if team_key == "sales":
            return [
                ("업로드 확인", "upload-review"),
                ("업로드 자동", "upload-auto"),
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
        if action == "sheet-config":
            self.configure_sheet_settings()
            return
        if action == "thumbnail-manual":
            self.run_thumbnail_action()
            return
        if action == "thumbnail-auto":
            self.run_thumbnail_auto_action()
            return
        self.run_action(action)

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
        if action in {"install", "setup"}:
            self.current_stage_key = "leader"
        elif action in {"run", "watch"}:
            self.current_stage_key = "scout"
        elif action == "save-images":
            self.current_stage_key = "assets"
        elif action == "make-thumbnails":
            self.current_stage_key = "design"
        elif action in {"upload-review", "upload-auto"}:
            self.current_stage_key = "sales"
        elif action == "full-auto-upload":
            self.current_stage_key = "leader"
            self._set_stage_status("scout", "준비")
            self._set_stage_status("assets", "준비")
            self._set_stage_status("design", "준비")
            self._set_stage_status("sales", "준비")
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

        if action == "setup":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "setup.py"))
        if action == "run":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"))
        if action == "watch":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--watch")
        if action == "watch-crawler":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--watch")
        if action == "watch-images":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--watch", "--download-images")
        if action == "watch-thumbnails":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--watch", "--make-thumbnails")
        if action == "watch-upload":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "buyma_upload.py"), "--watch", "--mode", "auto")
        if action == "save-images":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--download-images")
        if action == "make-thumbnails":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "main.py"), "--make-thumbnails")
        if action == "upload-review":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "buyma_upload.py"), "--mode", "review")
        if action == "upload-auto":
            return build_unbuffered_python_command(os.path.join(SCRIPT_DIR, "buyma_upload.py"), "--mode", "auto")

        raise ValueError(f"Unknown action: {action}")

    def _build_full_auto_sequence(self) -> list[list[str]]:
        return [
            self._build_command("run"),
            self._build_command("save-images"),
            self._build_command("make-thumbnails"),
            self._build_command("upload-auto"),
        ]

    def _set_running_ui(self, running: bool) -> None:
        normal = tk.DISABLED if running else tk.NORMAL
        self.install_btn.configure(state=normal)
        self.setup_btn.configure(state=normal)
        self.sheet_cfg_btn.configure(state=normal)
        self.full_auto_btn.configure(state=normal)
        self.run_btn.configure(state=normal)
        self.watch_btn.configure(state=normal)
        self.image_save_btn.configure(state=normal)
        self.upload_review_btn.configure(state=normal)
        self.upload_auto_btn.configure(state=normal)
        self.thumb_btn.configure(state=normal)
        self.thumb_auto_btn.configure(state=normal)
        self.thumb_batch_btn.configure(state=normal)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _get_sheet_label_prefix(self) -> str:
        return "정찰팀"

    def _refresh_action_button_labels(self) -> None:
        prefix = self._get_sheet_label_prefix()
        self.run_btn.configure(text=f"{prefix} 시작")
        self.watch_btn.configure(text=f"{prefix} 감시")
        self.image_save_btn.configure(text="자료팀 저장")

    def _load_sheet_config(self) -> dict:
        try:
            if not os.path.exists(self.sheet_config_path):
                return {}
            with open(self.sheet_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_sheet_config(self, config: dict) -> bool:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.sheet_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            messagebox.showerror("????ㅽ뙣", f"?쒗듃 ?ㅼ젙 ????ㅽ뙣: {e}")
            return False

    def _has_sheet_config(self) -> bool:
        cfg = self._load_sheet_config()
        return bool((cfg.get("spreadsheet_id") or "").strip())

    def _normalize_spreadsheet_id(self, raw_value: str) -> str:
        """?낅젰媛믪뿉??Spreadsheet ID瑜?異붿텧/?뺢퇋?뷀븳??"""
        value = (raw_value or "").strip()
        if not value:
            return ""

        # URL ?꾩껜瑜??ｌ? 寃쎌슦 /d/<id>/ 遺遺꾩뿉??異붿텧
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
        if m:
            return m.group(1)

        # d/<id>, /d/<id> ?뺥깭???덉슜
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
        # 援ш? ?쒗듃 ID??蹂댄넻 ?곷Ц/?レ옄/-/_ 議고빀??湲?臾몄옄??
        return bool(re.fullmatch(r"[a-zA-Z0-9-_]{20,}", sid))

    def configure_sheet_settings(self) -> bool:
        """?쒗듃 ?ㅼ젙 ?앹뾽???닿퀬 ??ν븳??"""
        current = self._load_sheet_config()
        cur_id = (current.get("spreadsheet_id") or "").strip()
        cur_name = (current.get("sheet_name") or "?쒗듃1").strip() or "?쒗듃1"
        cur_gids = current.get("sheet_gids") or [1698424449]
        cur_gid_text = ",".join(str(x) for x in cur_gids if isinstance(x, int))

        spreadsheet_input = simpledialog.askstring(
            "?쒗듃 ?ㅼ젙",
            "Google Spreadsheet ID ?먮뒗 ?쒗듃 URL???낅젰?섏꽭??",
            initialvalue=cur_id,
            parent=self,
        )
        if spreadsheet_input is None:
            return False

        spreadsheet_id = self._normalize_spreadsheet_id(spreadsheet_input)
        if not self._is_valid_spreadsheet_id(spreadsheet_id):
            messagebox.showwarning(
                "?낅젰 ?ㅻ쪟",
                "?좏슚??Spreadsheet ID媛 ?꾨떃?덈떎.\n?대찓?쇱씠 ?꾨땲???쒗듃 URL??/d/ ??臾몄옄?댁쓣 ?낅젰?댁＜?몄슂.",
            )
            return False

        sheet_name = simpledialog.askstring(
            "?쒗듃 ?ㅼ젙",
            "?쒗듃 ?대쫫???낅젰?섏꽭??(湲곕낯: ?쒗듃1):",
            initialvalue=cur_name,
            parent=self,
        )
        if sheet_name is None:
            return False
        sheet_name = sheet_name.strip() or "?쒗듃1"

        gid_text = simpledialog.askstring(
            "?쒗듃 ?ㅼ젙",
            "?쒗듃 GID瑜??낅젰?섏꽭??(?щ윭 媛쒕㈃ 肄ㅻ쭏 援щ텇):",
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
        }
        if not self._save_sheet_config(config):
            return False

        self.append_log(f"?쒗듃 ?ㅼ젙 ????꾨즺: {self.sheet_config_path}\n")
        self._refresh_action_button_labels()
        return True

    def _ensure_sheet_config_on_startup(self) -> None:
        if self._has_sheet_config():
            return
        messagebox.showinfo(
            "珥덇린 ?ㅼ젙",
            "泥섏쓬 ?ㅽ뻾?낅땲?? Google ?쒗듃 媛믪쓣 癒쇱? ?낅젰?댁＜?몄슂.",
        )
        self.configure_sheet_settings()

    def _ensure_sheet_config_before_action(self, action: str) -> bool:
        if action not in {"run", "watch", "watch-crawler", "watch-images", "watch-thumbnails", "watch-upload", "upload-review", "upload-auto", "save-images", "make-thumbnails", "full-auto-upload"}:
            return True
        cfg = self._load_sheet_config()
        sid = self._normalize_spreadsheet_id(cfg.get("spreadsheet_id", ""))
        if self._is_valid_spreadsheet_id(sid):
            return True
        messagebox.showwarning("?쒗듃 ?ㅼ젙 ?꾩슂", "?쒗듃 ID媛 ?녾굅???섎せ?섏뿀?듬땲?? ?쒗듃 ?ㅼ젙???ㅼ떆 ?댁＜?몄슂.")
        return self.configure_sheet_settings()

    def _start_command(self, command: list[str]) -> bool:
        self.append_log("\n" + "=" * 70 + "\n")
        self.append_log(f"실행: {' '.join(command)}\n")

        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
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
        if action == "full-auto-upload":
            self.status_var.set("터미널 시퀀스 실행")
            self._start_sequence_in_terminal(self._build_full_auto_sequence())
            return
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

        btn_frame = tk.Frame(dlg, padx=20, pady=12)
        btn_frame.pack()

        def choose(s: str):
            result[0] = s
            dlg.destroy()

        tk.Button(btn_frame, text="split", width=14, bg="#fff4e5",
                  font=("Arial", 10, "bold"), command=lambda: choose("split")).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="banner", width=14, bg="#e8f0fe",
                  font=("Arial", 10, "bold"), command=lambda: choose("banner")).pack(side=tk.LEFT, padx=8)

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
        self._sync_stage_from_action("make-thumbnails")
        self._start_command(command)

    def run_thumbnail_auto_action(self) -> None:
        """?ㅽ????쒕뜡 ?먮룞 ?좏깮?쇰줈 ?몃꽕???앹꽦."""
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

        style = random.choice(["split", "banner"])
        self.append_log(f"?ㅽ????먮룞?좏깮: {style}\n")

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
        self._sync_stage_from_action("make-thumbnails")
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

