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
        main.grid_rowconfigure(3, weight=1)

        self.controller._build_kpi_section(main)
        self._build_recommended_actions(main, row=2)

        sections = tk.Frame(main, bg=self.controller.theme["bg"])
        sections.grid(row=3, column=0, sticky="nsew")
        sections.grid_columnconfigure(0, weight=1)
        sections.grid_rowconfigure(4, weight=1)
        self.controller._build_pipeline_section(sections)
        self.controller._build_activity_section(sections)
        self.controller._build_table_section(sections)

        footer = tk.Frame(main, bg=self.controller.theme["bg"])
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(1, weight=1)
        tk.Label(footer, text=f"사용자: {settings['user_name']}", bg=self.controller.theme["bg"], fg=self.controller.theme["muted"], font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(footer, text=f"현재 시트: {settings['sheet_name'] or '-'}", bg=self.controller.theme["bg"], fg=self.controller.theme["muted"], font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w", padx=(36, 0))
        auto_watch_text = "활성" if self.controller.state.current_action == "watch" else "대기"
        auto_watch_color = self.controller.theme["green"] if auto_watch_text == "활성" else self.controller.theme["muted"]
        tk.Label(footer, text=f"자동 감시: {auto_watch_text}", bg=self.controller.theme["bg"], fg=auto_watch_color, font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="e")

    def _build_recommended_actions(self, parent: tk.Widget, *, row: int) -> None:
        pending = getattr(self.controller.state.metrics, "waiting", 0)
        failures = getattr(self.controller.state.metrics, "error", 0)
        card, _body, _ = self.build_recommended_action_tiles(
            parent,
            "권장 작업",
            [
                ("목록 수집 실행", "목록 페이지 URL 수집", self.controller.theme["green"], self.controller.theme["green"], lambda: self.controller.dispatch_ui_action("목록 페이지 수집 실행", lambda: self.controller.run_action("collect-listings"), category="scout")),
                ("정찰 1회 실행", f"대기 상품 {pending:,}건", self.controller.theme["blue"], self.controller.theme["blue_2"], lambda: self.controller.dispatch_ui_action("정찰 1회 실행", lambda: self.controller.run_action("run"), category="scout")),
                ("이미지 처리 시작", "이미지 저장 실행", self.controller.theme["purple"], self.controller.theme["purple"], lambda: self.controller.dispatch_ui_action("이미지 처리 시작", lambda: self.controller.run_action("save-images"), category="assets")),
                ("업로드 실행", f"오류/보류 {failures:,}건", self.controller.theme["orange"], self.controller.theme["orange"], lambda: self.controller.dispatch_ui_action("BUYMA 업로드 실행", lambda: self.controller.run_action("upload-auto"), category="buyma")),
            ],
            columns=4,
            min_height=132,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))

    def build_right_panel(self, parent: tk.Widget) -> None:
        parent.grid_columnconfigure(0, weight=1)
        self.controller._build_quick_actions_panel(parent)
        self.controller._build_system_status_panel(parent)
