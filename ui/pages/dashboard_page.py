from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import BasePage, SECTION_GAP


class DashboardPage(BasePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="대시보드", subtitle="전체 자동화 시스템의 실시간 현황을 확인할 수 있습니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        settings = self.controller.dashboard_data.get_settings_overview()
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        main = tk.Frame(self.body, bg=self.controller.theme["bg"])
        main.grid(row=0, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)

        self.controller._build_kpi_section(main)
        self.controller._build_pipeline_section(main)
        self.controller._build_activity_section(main)
        self.controller._build_table_section(main)

        footer = tk.Frame(main, bg=self.controller.theme["bg"])
        footer.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(1, weight=1)
        tk.Label(footer, text=f"사용자: {settings['user_name']}", bg=self.controller.theme["bg"], fg=self.controller.theme["muted"], font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(footer, text=f"현재 시트: {settings['sheet_name'] or '-'}", bg=self.controller.theme["bg"], fg=self.controller.theme["muted"], font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w", padx=(36, 0))
        auto_watch_text = "활성" if self.controller.state.current_action == "watch" else "대기"
        auto_watch_color = self.controller.theme["green"] if auto_watch_text == "활성" else self.controller.theme["muted"]
        tk.Label(footer, text=f"자동 감시: {auto_watch_text}", bg=self.controller.theme["bg"], fg=auto_watch_color, font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="e")

    def build_right_panel(self, parent: tk.Widget) -> None:
        parent.grid_columnconfigure(0, weight=1)
        self.controller._build_quick_actions_panel(parent)
        self.controller._build_system_status_panel(parent)
