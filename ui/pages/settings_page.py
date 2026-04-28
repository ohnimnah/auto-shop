from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import BasePage, SECTION_GAP


class SettingsPage(BasePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="관리 / 설정", subtitle="시스템 설정과 연결 정보를 확인하고 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        settings = self.controller.dashboard_data.get_settings_overview()
        metrics = [
            ("Google Sheet", 1 if settings["sheet_enabled"] else 0, "사용 여부"),
            ("BUYMA 계정", 1 if settings["buyma_email"] else 0, "저장 여부"),
            ("경로 설정", 1 if settings["images_dir"] != "-" else 0, "이미지 폴더"),
            ("런타임", 1 if self.controller.state.system_status.get("runtime") == "정상" else 0, self.controller.state.system_status.get("runtime", "-")),
        ]
        _shell, left, right = self.build_dashboard_layout(metrics)
        left.grid_rowconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)

        basic_card, basic_body = self.build_panel_card(left, "기본 / Google Sheet / 계정 경로", level="bottom")
        basic_card.grid(row=0, column=0, sticky="nsew", pady=(0, SECTION_GAP))
        self._section_label(basic_body, 0, "기본 설정")
        self._kv_card(
            basic_body,
            [("프로필", settings["profile_name"]), ("실행 모드", settings["run_mode"]), ("로그 레벨", settings["log_level"])],
            start_row=1,
        )
        self._divider(basic_body, 7)
        self._section_label(basic_body, 8, "Google Sheet 설정")
        self._kv_card(
            basic_body,
            [
                ("Google Sheet 사용", "활성" if settings["sheet_enabled"] else "비활성"),
                ("Spreadsheet ID", settings["spreadsheet_id"] or "-"),
                ("상품 시트명", settings["sheet_name"] or "-"),
                ("로그 시트명", settings["log_sheet_name"] or "-"),
            ],
            start_row=9,
        )
        self._divider(basic_body, 17)
        self._section_label(basic_body, 18, "BUYMA 계정 / 경로")
        self._kv_card(
            basic_body,
            [
                ("BUYMA 계정", settings["buyma_email"] or "-"),
                ("계정 파일", settings["buyma_credentials_path"]),
                ("이미지 폴더", settings["images_dir"]),
                ("로그 폴더", settings["log_dir"]),
            ],
            start_row=19,
        )

        runtime_card, runtime_body = self.build_panel_card(right, "시스템 설정", level="mid", min_height=144)
        runtime_card.grid(row=0, column=0, sticky="nsew", pady=(0, SECTION_GAP))
        self._kv_card(runtime_body, [
            ("동시 실행 수", settings["max_concurrency"]),
            ("재시도 횟수", settings["retry_limit"]),
            ("타임아웃", f"{settings['timeout_seconds']}초"),
            ("프로그램 상태", self.controller.state.status_text),
        ])

        actions_card, actions_body = self.build_panel_card(
            right,
            "경로 / 데이터 관리",
            level="bottom",
            min_height=320,
        )
        actions_card.grid(row=1, column=0, sticky="nsew")
        actions_body.grid_rowconfigure(8, weight=1)
        actions_body.grid_columnconfigure(0, weight=1)
        self._section_label(actions_body, 0, "데이터 관리 / 제어")
        self.controller._mini_button(
            actions_body,
            "시트 설정",
            lambda: self.controller.dispatch_ui_action("설정: 시트 설정 열기", self.controller.configure_sheet_settings, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 4))
        self.controller._mini_button(
            actions_body,
            "BUYMA 계정 입력",
            lambda: self.controller.dispatch_ui_action("설정: BUYMA 계정 설정", self.controller.configure_buyma_credentials, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=2, column=0, sticky="ew", pady=(0, 4))
        self.controller._mini_button(
            actions_body,
            "BUYMA 파일 가져오기",
            lambda: self.controller.dispatch_ui_action("설정: BUYMA 계정 파일 가져오기", self.controller.import_buyma_credentials_file, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=3, column=0, sticky="ew", pady=(0, 4))
        self.controller._mini_button(
            actions_body,
            "프로필 변경",
            lambda: self.controller.dispatch_ui_action("설정: 프로필 변경", self.controller.configure_user_profile, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=4, column=0, sticky="ew", pady=(0, 4))
        self.controller._mini_button(
            actions_body,
            "연결 테스트",
            lambda: self.controller.dispatch_ui_action("설정: 연결 테스트", self.controller.test_google_setup, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=5, column=0, sticky="ew", pady=(0, 4))
        self.controller._mini_button(
            actions_body,
            "이미지 폴더",
            lambda: self.controller.dispatch_ui_action("설정: 이미지 폴더 설정", self.controller.configure_images_directory, category="settings"),
            "#111f34",
            "#1e3350",
        ).grid(row=6, column=0, sticky="ew", pady=(0, 4))
        self.controller._mini_button(
            actions_body,
            "로그 폴더",
            lambda: self.controller.dispatch_ui_action("설정: 로그 폴더 열기", self.controller._show_log_folder_hint, category="settings"),
            "#111f34",
            "#1e3350",
        ).grid(row=7, column=0, sticky="ew", pady=(0, 4))

        spacer = tk.Frame(actions_body, bg=self.controller.theme["panel"])
        spacer.grid(row=8, column=0, sticky="nsew")

        action_row = tk.Frame(actions_body, bg=self.controller.theme["panel"])
        action_row.grid(row=9, column=0, sticky="sew", pady=(10, 0))
        action_row.grid_columnconfigure(0, weight=1)
        action_row.grid_columnconfigure(1, weight=1)
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
            tk.Label(parent, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=row, column=0, sticky="w", pady=(0 if idx == 0 else 3, 1))
            entry = tk.Entry(parent, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT)
            entry.insert(0, value)
            entry.grid(row=row + 1, column=0, sticky="ew", ipady=3)

    def _section_label(self, parent: tk.Widget, row: int, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["text"],
            font=("Segoe UI", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=(0, 4))

    def _divider(self, parent: tk.Widget, row: int) -> None:
        tk.Frame(parent, height=1, bg=self.controller.theme["line"]).grid(row=row, column=0, sticky="ew", pady=8)
