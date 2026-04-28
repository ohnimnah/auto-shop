from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import ConsolePage


class DashboardPage(ConsolePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="대시보드", subtitle="전체 자동화 시스템의 실시간 현황을 확인할 수 있습니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        shell = tk.Frame(self, bg=self.controller.theme["bg"])
        shell.pack(fill=tk.BOTH, expand=True)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_columnconfigure(1, minsize=292)
        shell.grid_rowconfigure(0, weight=1)

        main = tk.Frame(shell, bg=self.controller.theme["bg"])
        right = tk.Frame(shell, bg=self.controller.theme["bg"])
        main.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        right.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        self.controller._build_kpi_section(main)
        self.controller._build_pipeline_section(main)
        self.controller._build_activity_section(main)
        self.controller._build_table_section(main)
        self.controller._build_quick_actions_panel(right)
        self.controller._build_system_status_panel(right)

        footer = tk.Frame(main, bg=self.controller.theme["bg"])
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(1, weight=1)
        tk.Label(footer, text="사용자: master", bg=self.controller.theme["bg"], fg=self.controller.theme["muted"], font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(footer, text="현재 시트: collection", bg=self.controller.theme["bg"], fg=self.controller.theme["muted"], font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w", padx=(36, 0))
        tk.Label(footer, text="자동 감시: 활성", bg=self.controller.theme["bg"], fg=self.controller.theme["green"], font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="e")
