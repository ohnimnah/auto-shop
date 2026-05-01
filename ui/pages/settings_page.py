from __future__ import annotations

import os
import shutil
import tkinter as tk
from copy import deepcopy
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from config.config_service import get_profile_config_path, load_config, save_config
from ui.pages.base_page import BasePage, SECTION_GAP


class SettingsPage(BasePage):
    TAB_FIELDS = (
        ("product_input", "상품 입력 탭"),
        ("category", "카테고리 탭"),
        ("candidate", "후보 상품 탭"),
        ("scout_queue", "정찰 큐 탭"),
        ("log", "로그 탭"),
        ("category_mapping_candidates", "매핑 후보 탭"),
    )

    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="관리 / 설정", subtitle="시스템 설정과 연결 정보를 편집하고 검증합니다.")
        self.last_saved_config: dict | None = None
        self.sheet_validation_rows: list[tuple[str, str, str, str]] = []
        self._init_vars()
        self._load_config_into_form()
        self.build()

    def _init_vars(self) -> None:
        self.spreadsheet_id_var = tk.StringVar()
        self.service_account_path_var = tk.StringVar()
        self.images_dir_var = tk.StringVar()
        self.log_dir_var = tk.StringVar()
        self.buyma_email_var = tk.StringVar()
        self.buyma_password_var = tk.StringVar()
        self.connection_status_var = tk.StringVar(value="연결 테스트 전")
        self.permission_status_var = tk.StringVar(value="권한 확인 전")
        self.tabs_status_var = tk.StringVar(value="시트 탭 확인 전")
        self.validation_summary_var = tk.StringVar(value="설정을 저장하거나 연결 테스트를 실행해 주세요.")
        self.last_saved_var = tk.StringVar(value="-")
        self.config_path_var = tk.StringVar(value=self._config_path())
        self.status_color_vars = {
            "connection": tk.StringVar(value=self.controller.theme["muted"]),
            "permission": tk.StringVar(value=self.controller.theme["muted"]),
            "tabs": tk.StringVar(value=self.controller.theme["muted"]),
        }
        self.tab_vars = {key: tk.StringVar() for key, _label in self.TAB_FIELDS}

    def build(self) -> None:
        self.build_header()
        metrics = self._build_settings_metrics()
        _shell, left, right = self.build_dashboard_layout(metrics)
        left.grid_rowconfigure(0, weight=0)
        left.grid_rowconfigure(1, weight=0)
        left.grid_rowconfigure(2, weight=0)
        left.grid_rowconfigure(3, weight=1)
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(2, weight=0)

        self._build_google_sheet_card(left)
        self._build_sheet_tabs_card(left)
        self._build_paths_card(left)
        self._build_buyma_card(left)

        self._build_status_card(right)
        self._build_tab_validation_card(right)
        self._build_actions_card(right)

    def _build_settings_metrics(self) -> list[tuple[str, int, str]]:
        tab_values = [var.get().strip() for var in self.tab_vars.values()]
        configured_tabs = sum(1 for value in tab_values if value)
        return [
            ("활성 프로필", 1, self.controller.profile_name),
            ("시트 탭", configured_tabs, f"{configured_tabs}개 입력"),
            ("경로 설정", 2 if self.images_dir_var.get().strip() and self.log_dir_var.get().strip() else 0, "이미지 / 로그"),
            ("BUYMA 계정", 1 if self.buyma_email_var.get().strip() else 0, "이메일 저장"),
        ]

    def _build_google_sheet_card(self, parent: tk.Widget) -> None:
        card, body = self.build_panel_card(parent, "Google Sheets", level="mid", min_height=176)
        card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self._build_labeled_entry(body, 0, "Spreadsheet ID", self.spreadsheet_id_var)
        self._build_labeled_entry(
            body,
            2,
            "서비스 계정 키 파일 경로",
            self.service_account_path_var,
            button_text="파일 선택",
            button_command=self._choose_service_account_file,
        )

    def _build_sheet_tabs_card(self, parent: tk.Widget) -> None:
        card, body = self.build_panel_card(parent, "Sheet Tabs", level="mid", min_height=244)
        card.grid(row=1, column=0, sticky="ew", pady=(0, SECTION_GAP))
        body.grid_columnconfigure(0, weight=1, uniform="tabs")
        body.grid_columnconfigure(1, weight=1, uniform="tabs")
        for idx, (key, label) in enumerate(self.TAB_FIELDS):
            col = idx % 2
            block_row = (idx // 2) * 2
            self._build_grid_field(body, block_row, col, label, self.tab_vars[key])

    def _build_paths_card(self, parent: tk.Widget) -> None:
        card, body = self.build_panel_card(parent, "Paths", level="mid", min_height=168)
        card.grid(row=2, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self._build_labeled_entry(
            body,
            0,
            "이미지 저장 경로",
            self.images_dir_var,
            button_text="폴더 선택",
            button_command=lambda: self._choose_directory(self.images_dir_var),
        )
        self._build_labeled_entry(
            body,
            2,
            "로그 저장 경로",
            self.log_dir_var,
            button_text="폴더 선택",
            button_command=lambda: self._choose_directory(self.log_dir_var),
        )

    def _build_buyma_card(self, parent: tk.Widget) -> None:
        card, body = self.build_panel_card(parent, "BUYMA Account", level="bottom", min_height=176)
        card.grid(row=3, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1, uniform="buyma")
        body.grid_columnconfigure(1, weight=1, uniform="buyma")
        self._build_grid_field(body, 0, 0, "이메일", self.buyma_email_var)
        self._build_grid_field(body, 0, 1, "비밀번호", self.buyma_password_var, show="*")
        tk.Label(
            body,
            text="비밀번호는 OS 키체인에 저장되며, 비워두면 기존 저장값을 유지합니다.",
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 8),
            wraplength=620,
            justify=tk.LEFT,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_status_card(self, parent: tk.Widget) -> None:
        card, body = self.build_panel_card(parent, "연결 상태", level="mid", min_height=220)
        card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self._build_status_item(body, 0, "Google Sheets 연결", self.connection_status_var, self.status_color_vars["connection"], "연결 상태")
        self._build_status_item(body, 1, "권한 상태", self.permission_status_var, self.status_color_vars["permission"], "권한 확인")
        self._build_status_item(body, 2, "시트 탭 상태", self.tabs_status_var, self.status_color_vars["tabs"], "탭 확인")
        tk.Label(
            body,
            textvariable=self.validation_summary_var,
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 8),
            wraplength=340,
            justify=tk.LEFT,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _build_tab_validation_card(self, parent: tk.Widget) -> None:
        card, body = self.build_panel_card(parent, "시트 탭 검증 결과", level="bottom", min_height=272)
        card.grid(row=1, column=0, sticky="nsew", pady=(0, SECTION_GAP))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        columns = ("tab_name", "status", "rows", "cols")
        self.validation_table = ttk.Treeview(body, columns=columns, show="headings", style="Ops.Treeview", height=7)
        headings = {"tab_name": "탭 이름", "status": "상태", "rows": "행 수", "cols": "열 수"}
        widths = {"tab_name": 170, "status": 70, "rows": 58, "cols": 58}
        for column in columns:
            self.validation_table.heading(column, text=headings[column])
            self.validation_table.column(column, width=widths[column], minwidth=widths[column], stretch=(column == "tab_name"))
        self.validation_table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.validation_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.validation_table.configure(yscrollcommand=scrollbar.set)
        self.validation_table.tag_configure("ok", foreground="#4ade80")
        self.validation_table.tag_configure("missing", foreground="#f87171")
        self.validation_table.tag_configure("pending", foreground="#cbd5e1")
        self._render_validation_rows()

    def _build_actions_card(self, parent: tk.Widget) -> None:
        card, body = self.build_panel_card(parent, "작업", level="mid", min_height=210)
        card.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)
        self._meta_line(body, 0, "마지막 저장", self.last_saved_var)
        self._meta_line(body, 1, "설정 파일", self.config_path_var, wraplength=320)
        spacer = tk.Frame(body, bg=self.controller.theme["panel"])
        spacer.grid(row=2, column=0, sticky="nsew")

        button_wrap = tk.Frame(body, bg=self.controller.theme["panel"])
        button_wrap.grid(row=3, column=0, sticky="sew")
        button_wrap.grid_columnconfigure(0, weight=1)
        button_wrap.grid_columnconfigure(1, weight=1)
        button_wrap.grid_columnconfigure(2, weight=1)
        self.controller._mini_button(
            button_wrap,
            "Save Config",
            lambda: self.controller.dispatch_ui_action("설정: config 저장", self.save_current_config, category="settings"),
            self.controller.theme["blue"],
            self.controller.theme["blue_2"],
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.controller._mini_button(
            button_wrap,
            "Test Connection",
            lambda: self.controller.dispatch_ui_action("설정: 연결 테스트", self.test_connection, category="settings"),
            "#1e3350",
            "#294565",
        ).grid(row=0, column=1, sticky="ew", padx=6)
        self.controller._mini_button(
            button_wrap,
            "Cancel",
            lambda: self.controller.dispatch_ui_action("설정: 변경 취소", self.reset_to_saved_config, category="settings"),
            "#334155",
            "#475569",
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def _build_labeled_entry(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        variable: tk.StringVar,
        *,
        button_text: str | None = None,
        button_command=None,
    ) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=0)
        tk.Label(parent, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0 if row == 0 else 6, 4))
        entry = tk.Entry(parent, textvariable=variable, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT)
        entry.grid(row=row + 1, column=0, sticky="ew", ipady=5)
        if button_text and button_command:
            self.controller._mini_button(parent, button_text, button_command, "#1e3350", "#294565").grid(row=row + 1, column=1, sticky="e", padx=(8, 0))

    def _build_grid_field(
        self,
        parent: tk.Widget,
        row: int,
        col: int,
        label: str,
        variable: tk.StringVar,
        *,
        show: str | None = None,
    ) -> None:
        wrapper = tk.Frame(parent, bg=self.controller.theme["panel"])
        wrapper.grid(row=row, column=col, sticky="ew", padx=(0, 8) if col == 0 else (8, 0), pady=(0, 8))
        wrapper.grid_columnconfigure(0, weight=1)
        tk.Label(wrapper, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))
        entry = tk.Entry(wrapper, textvariable=variable, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT, show=show or "")
        entry.grid(row=1, column=0, sticky="ew", ipady=5)

    def _build_status_item(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        value_var: tk.StringVar,
        color_var: tk.StringVar,
        button_label: str,
    ) -> None:
        row_frame = tk.Frame(parent, bg=self.controller.theme["panel"])
        row_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        row_frame.grid_columnconfigure(0, weight=1)
        text_frame = tk.Frame(row_frame, bg=self.controller.theme["panel"])
        text_frame.grid(row=0, column=0, sticky="w")
        tk.Label(text_frame, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        status_label = tk.Label(text_frame, textvariable=value_var, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9))
        status_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
        color_var.trace_add("write", lambda *_args, target=status_label, source=color_var: target.configure(fg=source.get()))
        self.controller._mini_button(
            row_frame,
            button_label,
            lambda: self.controller.dispatch_ui_action("설정: 연결 테스트", self.test_connection, category="settings"),
            "#111f34",
            "#1e3350",
        ).grid(row=0, column=1, rowspan=2, sticky="e")

    def _meta_line(self, parent: tk.Widget, row: int, label: str, value_var: tk.StringVar, *, wraplength: int = 280) -> None:
        tk.Label(parent, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=row * 2, column=0, sticky="w", pady=(0 if row == 0 else 6, 2))
        tk.Label(
            parent,
            textvariable=value_var,
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["text"],
            font=("Segoe UI", 9),
            wraplength=wraplength,
            justify=tk.LEFT,
        ).grid(row=row * 2 + 1, column=0, sticky="w")

    def _choose_service_account_file(self) -> None:
        path = filedialog.askopenfilename(
            title="서비스 계정 키 파일 선택",
            initialdir=os.path.expanduser("~"),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self.service_account_path_var.set(os.path.abspath(os.path.expanduser(path)))

    def _choose_directory(self, variable: tk.StringVar) -> None:
        initialdir = variable.get().strip() or os.path.expanduser("~")
        path = filedialog.askdirectory(title="폴더 선택", initialdir=initialdir, mustexist=False, parent=self)
        if path:
            variable.set(os.path.abspath(os.path.expanduser(path)))

    def _config_path(self) -> str:
        return get_profile_config_path(self.controller.profile_name)

    def _load_config_into_form(self) -> None:
        config = load_config(self.controller.profile_name, create_if_missing=True)
        self.last_saved_config = deepcopy(config)
        spreadsheet_cfg = config.get("spreadsheet") or {}
        tabs_cfg = spreadsheet_cfg.get("tabs") or {}
        paths_cfg = config.get("paths") or {}
        buyma_cfg = config.get("buyma") or {}

        self.spreadsheet_id_var.set(str(spreadsheet_cfg.get("id") or "").strip())
        self.service_account_path_var.set(
            str(spreadsheet_cfg.get("credentials_path") or "").strip() or self.controller._get_available_credentials_path()
        )
        for key, _label in self.TAB_FIELDS:
            self.tab_vars[key].set(str(tabs_cfg.get(key) or "").strip())
        self.images_dir_var.set(
            str(paths_cfg.get("images_dir") or "").strip() or self.controller._get_configured_images_dir()
        )
        self.log_dir_var.set(
            str(paths_cfg.get("log_dir") or "").strip() or os.path.join(self.controller.data_dir, "logs")
        )
        self.buyma_email_var.set(str(buyma_cfg.get("email") or "").strip() or self.controller.buyma_credentials.load_email())
        self.buyma_password_var.set("")
        self.last_saved_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._set_neutral_status("설정을 검증하거나 저장해 주세요.")

    def _set_neutral_status(self, summary: str) -> None:
        muted = self.controller.theme["muted"]
        self.status_color_vars["connection"].set(muted)
        self.status_color_vars["permission"].set(muted)
        self.status_color_vars["tabs"].set(muted)
        self.connection_status_var.set("연결 테스트 전")
        self.permission_status_var.set("권한 확인 전")
        self.tabs_status_var.set("시트 탭 확인 전")
        self.validation_summary_var.set(summary)
        self.sheet_validation_rows = [(self.tab_vars[key].get().strip() or key, "대기", "-", "-") for key, _label in self.TAB_FIELDS]
        self._render_validation_rows()

    def _collect_config_payload(self) -> dict:
        current = deepcopy(self.last_saved_config or load_config(self.controller.profile_name, create_if_missing=True))
        spreadsheet_cfg = current.setdefault("spreadsheet", {})
        paths_cfg = current.setdefault("paths", {})
        buyma_cfg = current.setdefault("buyma", {})
        tabs_cfg = spreadsheet_cfg.setdefault("tabs", {})

        spreadsheet_cfg["id"] = self.controller._normalize_spreadsheet_id(self.spreadsheet_id_var.get())
        spreadsheet_cfg["credentials_path"] = self.service_account_path_var.get().strip()
        for key, _label in self.TAB_FIELDS:
            tabs_cfg[key] = self.tab_vars[key].get().strip()
        paths_cfg["images_dir"] = self.images_dir_var.get().strip()
        paths_cfg["log_dir"] = self.log_dir_var.get().strip()
        buyma_cfg["email"] = self.buyma_email_var.get().strip()
        return current

    def _validate_inputs(self) -> list[str]:
        issues: list[str] = []
        spreadsheet_id = self.controller._normalize_spreadsheet_id(self.spreadsheet_id_var.get())
        if not self.controller._is_valid_spreadsheet_id(spreadsheet_id):
            issues.append("Spreadsheet ID가 비어 있거나 형식이 올바르지 않습니다.")
        service_path = self.service_account_path_var.get().strip()
        if service_path and not os.path.isfile(os.path.abspath(os.path.expanduser(service_path))):
            issues.append("서비스 계정 키 파일 경로를 확인해 주세요.")
        for key, label in self.TAB_FIELDS:
            if not self.tab_vars[key].get().strip():
                issues.append(f"{label}을 입력해 주세요.")
        for label, value in (("이미지 저장 경로", self.images_dir_var.get()), ("로그 저장 경로", self.log_dir_var.get())):
            path = os.path.abspath(os.path.expanduser(value.strip()))
            if not path:
                issues.append(f"{label}를 입력해 주세요.")
                continue
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as exc:
                issues.append(f"{label}를 준비하지 못했습니다: {exc}")
        current_email = self.controller.buyma_credentials.load_email().strip()
        entered_email = self.buyma_email_var.get().strip()
        entered_password = self.buyma_password_var.get().strip()
        if entered_password and not entered_email:
            issues.append("BUYMA 비밀번호를 저장하려면 이메일도 함께 입력해 주세요.")
        if entered_email and not entered_password and entered_email != current_email:
            issues.append("BUYMA 이메일을 변경하려면 비밀번호도 함께 입력해 주세요.")
        return issues

    def save_current_config(self) -> bool:
        issues = self._validate_inputs()
        if issues:
            self.status_color_vars["connection"].set(self.controller.theme["red"])
            self.validation_summary_var.set("\n".join(issues[:3]))
            messagebox.showwarning("입력 확인", "\n".join(issues))
            return False

        config = self._collect_config_payload()
        try:
            credentials_path = self.service_account_path_var.get().strip()
            if credentials_path and os.path.isfile(os.path.abspath(os.path.expanduser(credentials_path))):
                os.makedirs(self.controller.data_dir, exist_ok=True)
                shutil.copy2(
                    os.path.abspath(os.path.expanduser(credentials_path)),
                    self.controller._get_credentials_target_path(),
                )

            email = self.buyma_email_var.get().strip()
            password = self.buyma_password_var.get().strip()
            if email and password:
                self.controller.buyma_credentials.save(email, password)

            config_path = save_config(self.controller.profile_name, config)
            self.controller.profile_config = deepcopy(config)
            self.last_saved_config = deepcopy(config)
            self.config_path_var.set(config_path)
            self.last_saved_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            self.buyma_password_var.set("")

            legacy = self.controller._load_sheet_config()
            legacy.update(
                {
                    "spreadsheet_id": config["spreadsheet"]["id"],
                    "sheet_name": config["spreadsheet"]["tabs"]["product_input"],
                    "category_sheet_name": config["spreadsheet"]["tabs"]["category"],
                    "candidate_sheet_name": config["spreadsheet"]["tabs"]["candidate"],
                    "queue_sheet_name": config["spreadsheet"]["tabs"]["scout_queue"],
                    "log_sheet_name": config["spreadsheet"]["tabs"]["log"],
                    "category_mapping_candidates_sheet_name": config["spreadsheet"]["tabs"]["category_mapping_candidates"],
                    "images_dir": config["paths"]["images_dir"],
                    "log_dir": config["paths"]["log_dir"],
                    "credentials_path": config["spreadsheet"].get("credentials_path", ""),
                }
            )
            self.controller._save_sheet_config(legacy)
            self.controller.refresh_first_run_wizard()
            self.controller.refresh_dashboard_data()
            self.status_color_vars["connection"].set(self.controller.theme["green"])
            self.validation_summary_var.set("설정을 저장했습니다. 다음 실행부터 같은 프로필 설정을 그대로 사용합니다.")
            messagebox.showinfo("설정 저장", f"설정을 저장했습니다.\n{config_path}")
            return True
        except Exception as exc:
            self.status_color_vars["connection"].set(self.controller.theme["red"])
            self.validation_summary_var.set(f"설정 저장 실패: {exc}")
            messagebox.showerror("저장 실패", f"config.json 저장에 실패했습니다: {exc}")
            return False

    def test_connection(self) -> bool:
        issues = self._validate_inputs()
        if issues:
            self.status_color_vars["connection"].set(self.controller.theme["red"])
            self.validation_summary_var.set("\n".join(issues[:3]))
            messagebox.showwarning("입력 확인", "\n".join(issues))
            return False

        credentials_path = self.service_account_path_var.get().strip() or self.controller._get_available_credentials_path()
        credentials_path = os.path.abspath(os.path.expanduser(credentials_path))
        if not credentials_path or not os.path.isfile(credentials_path):
            self.status_color_vars["connection"].set(self.controller.theme["red"])
            self.connection_status_var.set("키 파일 필요")
            self.validation_summary_var.set("서비스 계정 키 파일을 먼저 연결해 주세요.")
            return False

        spreadsheet_id = self.controller._normalize_spreadsheet_id(self.spreadsheet_id_var.get())
        tab_names = {key: self.tab_vars[key].get().strip() for key, _label in self.TAB_FIELDS}
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
            service = build("sheets", "v4", credentials=creds)
            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = spreadsheet.get("sheets", [])
            by_title = {str(item.get("properties", {}).get("title") or "").strip(): item for item in sheets}

            self.status_color_vars["connection"].set(self.controller.theme["green"])
            self.connection_status_var.set("연결 성공")
            self.status_color_vars["permission"].set(self.controller.theme["green"])
            self.permission_status_var.set("읽기 권한 확인됨")

            missing: list[str] = []
            rows: list[tuple[str, str, str, str]] = []
            for key, label in self.TAB_FIELDS:
                tab_name = tab_names[key]
                sheet = by_title.get(tab_name)
                if sheet is None:
                    missing.append(tab_name)
                    rows.append((tab_name, "누락", "-", "-"))
                    continue
                props = sheet.get("properties", {})
                grid = props.get("gridProperties", {})
                rows.append(
                    (
                        tab_name,
                        "정상",
                        str(grid.get("rowCount", "-")),
                        str(grid.get("columnCount", "-")),
                    )
                )

            self.sheet_validation_rows = rows
            self._render_validation_rows()
            if missing:
                self.status_color_vars["tabs"].set(self.controller.theme["red"])
                self.tabs_status_var.set(f"누락 {len(missing)}개")
                self.validation_summary_var.set(f"누락된 탭: {', '.join(missing)}")
            else:
                self.status_color_vars["tabs"].set(self.controller.theme["green"])
                self.tabs_status_var.set("모든 탭 정상")
                self.validation_summary_var.set("Google Sheets 연결과 필수 시트 탭 검증이 모두 완료되었습니다.")
            return not missing
        except Exception as exc:
            self.status_color_vars["connection"].set(self.controller.theme["red"])
            self.status_color_vars["permission"].set(self.controller.theme["red"])
            self.status_color_vars["tabs"].set(self.controller.theme["red"])
            self.connection_status_var.set("연결 실패")
            self.permission_status_var.set("권한 확인 실패")
            self.tabs_status_var.set("검증 중단")
            self.validation_summary_var.set(f"Google Sheets 연결 확인 실패: {exc}")
            self.sheet_validation_rows = [(self.tab_vars[key].get().strip() or key, "오류", "-", "-") for key, _label in self.TAB_FIELDS]
            self._render_validation_rows()
            messagebox.showerror("연결 실패", f"Google Sheets 연결 확인에 실패했습니다.\n\n{exc}")
            return False

    def reset_to_saved_config(self) -> bool:
        self._load_config_into_form()
        self.controller.refresh_first_run_wizard()
        self.refresh_view()
        return True

    def _render_validation_rows(self) -> None:
        if not hasattr(self, "validation_table") or not self.validation_table.winfo_exists():
            return
        for item in self.validation_table.get_children():
            self.validation_table.delete(item)
        for name, status, rows, cols in self.sheet_validation_rows:
            tag = "ok" if status == "정상" else "missing" if status in {"누락", "오류"} else "pending"
            self.validation_table.insert("", tk.END, values=(name, status, rows, cols), tags=(tag,))
