from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import PANEL_MIN_HEIGHT, SECTION_GAP, ScrollablePage


class SettingsPage(ScrollablePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="관리 / 설정", subtitle="시스템 설정과 연결 정보를 확인하고 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        settings = self.controller.dashboard_data.get_settings_overview()
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(2, weight=1)

        metrics = [
            ("Google Sheet", 1 if settings["sheet_enabled"] else 0, "사용 여부"),
            ("BUYMA 계정", 1 if settings["buyma_email"] else 0, "저장 여부"),
            ("경로 설정", 1 if settings["images_dir"] != "-" else 0, "이미지 폴더"),
            ("런타임", 1 if self.controller.state.system_status.get("runtime") == "정상" else 0, self.controller.state.system_status.get("runtime", "-")),
        ]
        self.build_metric_row(self.body, row=0, metrics=metrics)

        _shell, left, right = self.build_two_column_section(self.body, row=1)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(1, weight=1)

        basic_card, basic_body = self.build_panel_card(left, "기본 / Google Sheet", min_height=320)
        basic_card.grid(row=0, column=0, sticky="nsew", pady=(0, SECTION_GAP))
        self._kv_card(basic_body, [("사용자명", settings["user_name"]), ("실행 모드", settings["run_mode"]), ("로그 레벨", settings["log_level"])])
        tk.Frame(basic_body, height=1, bg=self.controller.theme["line"]).grid(row=6, column=0, sticky="ew", pady=10)
        self._kv_card(
            basic_body,
            [
                ("Google Sheet 사용", "활성" if settings["sheet_enabled"] else "비활성"),
                ("Spreadsheet ID", settings["spreadsheet_id"] or "-"),
                ("상품 시트명", settings["sheet_name"] or "-"),
                ("로그 시트명", settings["log_sheet_name"] or "-"),
            ],
            start_row=7,
        )

        account_card, account_body = self.build_panel_card(left, "BUYMA 계정 / 경로", min_height=PANEL_MIN_HEIGHT + 70)
        account_card.grid(row=1, column=0, sticky="nsew")
        self._kv_card(account_body, [
            ("BUYMA 계정", settings["buyma_email"] or "-"),
            ("이미지 폴더", settings["images_dir"]),
            ("로그 폴더", settings["log_dir"]),
        ])

        runtime_card, runtime_body = self.build_panel_card(right, "시스템 설정", min_height=250)
        runtime_card.grid(row=0, column=0, sticky="nsew", pady=(0, SECTION_GAP))
        self._kv_card(runtime_body, [
            ("동시 실행 수", settings["max_concurrency"]),
            ("재시도 횟수", settings["retry_limit"]),
            ("타임아웃", f"{settings['timeout_seconds']}초"),
            ("프로그램 상태", self.controller.state.status_text),
        ])

        actions_card, actions_body = self.build_panel_card(right, "데이터 관리 / 제어", min_height=PANEL_MIN_HEIGHT + 90)
        actions_card.grid(row=1, column=0, sticky="nsew")
        self.controller._mini_button(
            actions_body,
            "시트 설정",
            lambda: self.controller.dispatch_ui_action("설정: 시트 설정 열기", self.controller.configure_sheet_settings, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.controller._mini_button(
            actions_body,
            "BUYMA 계정",
            lambda: self.controller.dispatch_ui_action("설정: BUYMA 계정 설정", self.controller.configure_buyma_credentials, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.controller._mini_button(
            actions_body,
            "연결 테스트",
            lambda: self.controller.dispatch_ui_action("설정: 연결 테스트", self.controller.test_google_setup, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=2, column=0, sticky="ew", pady=(0, 4))
        self.controller._mini_button(
            actions_body,
            "이미지 폴더",
            lambda: self.controller.dispatch_ui_action("설정: 이미지 폴더 설정", self.controller.configure_images_directory, category="settings"),
            "#111f34",
            "#1e3350",
        ).grid(row=3, column=0, sticky="ew", pady=(0, 10))

        action_row = tk.Frame(actions_body, bg=self.controller.theme["panel"])
        action_row.grid(row=4, column=0, sticky="ew")
        action_row.grid_columnconfigure(0, weight=1)
        self.controller._mini_button(
            action_row,
            "취소",
            lambda: self.controller.dispatch_ui_action("설정: 변경 취소", self.controller.refresh_dashboard_data, category="settings"),
            "#334155",
            "#475569",
        ).grid(row=0, column=1, sticky="e")
        self.controller._mini_button(
            action_row,
            "저장",
            lambda: self.controller.dispatch_ui_action("설정: 저장", self.controller.refresh_dashboard_data, category="settings"),
            self.controller.theme["blue"],
            self.controller.theme["blue_2"],
        ).grid(row=0, column=0, sticky="e", padx=(0, 8))

    def _kv_card(self, parent: tk.Widget, rows: list[tuple[str, str]], *, start_row: int = 0) -> None:
        for idx, (label, value) in enumerate(rows):
            row = start_row + idx * 2
            tk.Label(parent, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=row, column=0, sticky="w", pady=(0 if idx == 0 else 6, 2))
            entry = tk.Entry(parent, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT)
            entry.insert(0, value)
            entry.grid(row=row + 1, column=0, sticky="ew", ipady=5)
