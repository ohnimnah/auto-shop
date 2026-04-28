from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import ConsolePage


class SettingsPage(ConsolePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="관리 / 설정", subtitle="시스템 설정과 연결 정보를 확인하고 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        settings = self.controller.dashboard_data.get_settings_overview()

        shell = tk.Frame(self, bg=self.controller.theme["bg"])
        shell.pack(fill=tk.BOTH, expand=True)
        top = tk.Frame(shell, bg=self.controller.theme["bg"])
        top.pack(fill=tk.BOTH, expand=True)
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=1)
        top.grid_columnconfigure(2, weight=1)

        basic = self.controller._panel(top, padx=12, pady=10)
        basic.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 12))
        self._kv_card(basic, "기본 설정", [
            ("사용자명", settings["user_name"]),
            ("실행 모드", settings["run_mode"]),
            ("로그 레벨", settings["log_level"]),
        ])

        sheet = self.controller._panel(top, padx=12, pady=10)
        sheet.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=(0, 12))
        self._kv_card(sheet, "Google Sheet 설정", [
            ("사용 여부", "활성" if settings["sheet_enabled"] else "비활성"),
            ("Spreadsheet ID", settings["spreadsheet_id"] or "-"),
            ("상품 시트명", settings["sheet_name"] or "-"),
            ("로그 시트명", settings["log_sheet_name"] or "-"),
        ])

        runtime = self.controller._panel(top, padx=12, pady=10)
        runtime.grid(row=0, column=2, sticky="nsew", pady=(0, 12))
        self._kv_card(runtime, "시스템 설정", [
            ("동시 실행 수", settings["max_concurrency"]),
            ("재시도 횟수", settings["retry_limit"]),
            ("타임아웃", f"{settings['timeout_seconds']}초"),
            ("상태", self.controller.state.status_text),
        ])

        bottom = tk.Frame(shell, bg=self.controller.theme["bg"])
        bottom.pack(fill=tk.X)
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)

        account = self.controller._panel(bottom, padx=12, pady=10)
        account.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._kv_card(account, "BUYMA 계정 / 경로", [
            ("BUYMA 계정", settings["buyma_email"] or "-"),
            ("이미지 폴더", settings["images_dir"]),
            ("로그 폴더", settings["log_dir"]),
        ])

        actions = self.controller._panel(bottom, padx=12, pady=10)
        actions.grid(row=0, column=1, sticky="nsew")
        tk.Label(actions, text="데이터 관리", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        self.controller._mini_button(
            actions,
            "시트 설정",
            lambda: self.controller.dispatch_ui_action("설정: 시트 설정 열기", self.controller.configure_sheet_settings, category="settings"),
            "#1e3350",
            "#294565",
        ).pack(fill=tk.X, pady=4)
        self.controller._mini_button(
            actions,
            "BUYMA 계정",
            lambda: self.controller.dispatch_ui_action("설정: BUYMA 계정 설정", self.controller.configure_buyma_credentials, category="settings"),
            "#1e3350",
            "#294565",
        ).pack(fill=tk.X, pady=4)
        self.controller._mini_button(
            actions,
            "연결 테스트",
            lambda: self.controller.dispatch_ui_action("설정: 연결 테스트", self.controller.test_google_setup, category="settings"),
            "#1e3350",
            "#294565",
        ).pack(fill=tk.X, pady=4)
        self.controller._mini_button(
            actions,
            "이미지 폴더",
            lambda: self.controller.dispatch_ui_action("설정: 이미지 폴더 설정", self.controller.configure_images_directory, category="settings"),
            "#111f34",
            "#1e3350",
        ).pack(fill=tk.X, pady=4)
        action_row = tk.Frame(actions, bg=self.controller.theme["panel"])
        action_row.pack(fill=tk.X, pady=(12, 0))
        self.controller._mini_button(
            action_row,
            "취소",
            lambda: self.controller.dispatch_ui_action("설정: 변경 취소", self.controller.refresh_dashboard_data, category="settings"),
            "#334155",
            "#475569",
        ).pack(side=tk.RIGHT)
        self.controller._mini_button(
            action_row,
            "저장",
            lambda: self.controller.dispatch_ui_action("설정: 저장", self.controller.refresh_dashboard_data, category="settings"),
            self.controller.theme["blue"],
            self.controller.theme["blue_2"],
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def _kv_card(self, parent: tk.Widget, title: str, rows: list[tuple[str, str]]) -> None:
        tk.Label(parent, text=title, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        for label, value in rows:
            row = tk.Frame(parent, bg=self.controller.theme["panel"])
            row.pack(fill=tk.X, pady=4)
            tk.Label(row, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
            entry = tk.Entry(row, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT)
            entry.insert(0, value)
            entry.pack(fill=tk.X, ipady=5, pady=(2, 0))
