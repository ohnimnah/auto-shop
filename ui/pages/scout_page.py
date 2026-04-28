from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import ConsolePage


class ScoutPage(ConsolePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="수집 / 정찰", subtitle="BUYMA 상품 등록 전 수집 및 정찰 현황을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_scout_overview()
        shell = tk.Frame(self, bg=self.controller.theme["bg"])
        shell.pack(fill=tk.BOTH, expand=True)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_columnconfigure(1, minsize=270)
        shell.grid_rowconfigure(2, weight=1)

        self.build_metric_row(shell, overview["metrics"])

        progress_card = self.controller._panel(shell, padx=12, pady=10)
        progress_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(progress_card, text="수집 진행률", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(progress_card, text=f"{int(overview['ratio'] * 100)}%", bg=self.controller.theme["panel"], fg=self.controller.theme["green"], font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(8, 6))
        bar = tk.Canvas(progress_card, height=8, bg=self.controller.theme["panel"], highlightthickness=0)
        bar.pack(fill=tk.X)
        width = 720
        bar.create_rectangle(0, 0, width, 8, fill="#21334d", outline="")
        bar.create_rectangle(0, 0, int(width * overview["ratio"]), 8, fill=self.controller.theme["green"], outline="")

        content = tk.Frame(shell, bg=self.controller.theme["bg"])
        content.pack(fill=tk.BOTH, expand=True)
        left = tk.Frame(content, bg=self.controller.theme["bg"])
        right = tk.Frame(content, bg=self.controller.theme["bg"], width=280)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        right.pack(side=tk.RIGHT, fill=tk.BOTH)

        recent_rows = [
            (row.no, row.name, row.brand, row.category, row.updated, row.state)
            for row in overview["recent_rows"]
        ]
        self.build_simple_table(
            left,
            "최근 수집 상품",
            [("no", "No.", 56), ("name", "상품명", 250), ("brand", "브랜드", 110), ("category", "카테고리", 100), ("updated", "업데이트", 100), ("state", "상태", 90)],
            recent_rows,
        )

        filter_card = self.controller._panel(right, padx=12, pady=10)
        filter_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(filter_card, text="필터", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        for label in ("작업 일자", "상태", "브랜드", "카테고리"):
            tk.Label(filter_card, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(6, 2))
            entry = tk.Entry(filter_card, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT)
            entry.pack(fill=tk.X, ipady=5)
        self.controller._mini_button(
            filter_card,
            "조회",
            lambda: self.controller.dispatch_ui_action("수집/정찰 필터 조회", self.controller.refresh_dashboard_data, category="scout"),
            "#1e3350",
            "#294565",
        ).pack(fill=tk.X, pady=(10, 6))
        self.controller._mini_button(
            filter_card,
            "수집 중지",
            lambda: self.controller.dispatch_ui_action("수집/정찰 중지 요청", self.controller.stop_action, category="scout"),
            "#334155",
            "#475569",
        ).pack(fill=tk.X)

        category_rows = [(name, count) for name, count in overview["category_rows"]]
        self.build_simple_table(
            right,
            "카테고리별 수집 현황",
            [("category", "카테고리", 170), ("count", "건수", 70)],
            category_rows,
        )
