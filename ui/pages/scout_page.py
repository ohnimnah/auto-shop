from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import PANEL_MIN_HEIGHT, SECTION_GAP, TABLE_MIN_HEIGHT, ScrollablePage, SURFACE_BG


class ScoutPage(ScrollablePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="수집 / 정찰", subtitle="BUYMA 상품 등록 전 수집 및 정찰 현황을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_scout_overview()
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(2, weight=1)

        self.build_metric_row(self.body, row=0, metrics=overview["metrics"])

        shell, left, right = self.build_two_column_section(self.body, row=1)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(1, weight=1)

        progress_card, progress_body = self.build_panel_card(left, "수집 진행 현황", min_height=170)
        progress_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        tk.Label(progress_body, text=f"{int(overview['ratio'] * 100)}%", bg=self.controller.theme["panel"], fg=self.controller.theme["green"], font=("Segoe UI", 22, "bold")).grid(row=0, column=0, sticky="w", pady=(2, 6))
        tk.Label(progress_body, text="전체 상품 기준 수집 완료 비율", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=(0, 8))
        bar = tk.Canvas(progress_body, height=8, bg=self.controller.theme["panel"], highlightthickness=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        bar.create_rectangle(0, 0, 960, 8, fill="#21334d", outline="")
        bar.create_rectangle(0, 0, int(960 * overview["ratio"]), 8, fill=self.controller.theme["green"], outline="")
        self.build_mini_tiles(
            progress_body,
            [
                ("정찰 워커", self.controller.state.pipeline_status.get("scout", "대기")),
                ("현재 실행", self.controller.state.current_action or "idle"),
                ("상품 소스", self.controller.state.data_source.label),
                ("카테고리 수", str(len(overview["category_rows"]))),
            ],
            columns=2,
            start_row=3,
        )

        category_card, _ = self.build_simple_table(
            left,
            "카테고리별 수집 현황",
            [("category", "카테고리", 180), ("count", "건수", 80)],
            [(name, count) for name, count in overview["category_rows"]],
            min_height=TABLE_MIN_HEIGHT,
        )
        category_card.grid(row=1, column=0, sticky="nsew")

        filter_card, filter_body = self.build_panel_card(right, "필터 / 실행", min_height=PANEL_MIN_HEIGHT + 70)
        filter_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        for idx, label in enumerate(("작업 일자", "상태", "브랜드", "카테고리")):
            tk.Label(filter_body, text=label, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).grid(row=idx * 2, column=0, sticky="w", pady=(6 if idx else 0, 2))
            entry = tk.Entry(filter_body, bg="#091626", fg="#dbeafe", insertbackground="#dbeafe", relief=tk.FLAT)
            entry.grid(row=idx * 2 + 1, column=0, sticky="ew", ipady=5)

        button_row = tk.Frame(filter_body, bg=self.controller.theme["panel"])
        button_row.grid(row=8, column=0, sticky="ew", pady=(10, 6))
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)
        self.controller._mini_button(
            button_row,
            "수집 시작",
            lambda: self.controller.dispatch_ui_action("수집/정찰 시작", lambda: self.controller.run_action("run"), category="scout"),
            self.controller.theme["green"],
            "#16a34a",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.controller._mini_button(
            button_row,
            "새로고침",
            lambda: self.controller.dispatch_ui_action("수집/정찰 데이터 새로고침", self.controller.refresh_dashboard_data, category="scout"),
            "#1e3350",
            "#294565",
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.controller._mini_button(
            filter_body,
            "수집 중지",
            lambda: self.controller.dispatch_ui_action("수집/정찰 중지 요청", self.controller.stop_action, category="scout"),
            "#334155",
            "#475569",
        ).grid(row=9, column=0, sticky="ew")

        summary_card, summary_body = self.build_panel_card(right, "수집 메모", min_height=TABLE_MIN_HEIGHT)
        summary_card.grid(row=1, column=0, sticky="nsew")
        if overview["recent_rows"]:
            top_rows = overview["recent_rows"][:4]
            for idx, row in enumerate(top_rows):
                item = tk.Frame(summary_body, bg=SURFACE_BG, padx=10, pady=8, highlightbackground=self.controller.theme["line"], highlightthickness=1)
                item.grid(row=idx, column=0, sticky="ew", pady=(0, 6))
                tk.Label(item, text=f"{row.brand or '-'}", bg=SURFACE_BG, fg="#93c5fd", font=("Segoe UI", 8, "bold")).pack(anchor="w")
                tk.Label(item, text=row.name, bg=SURFACE_BG, fg=self.controller.theme["text"], font=("Segoe UI", 9, "bold"), wraplength=240, justify=tk.LEFT).pack(anchor="w", pady=(4, 2))
                tk.Label(item, text=f"{row.category or '미분류'}  |  {row.state}", bg=SURFACE_BG, fg=self.controller.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        else:
            self.build_empty_state(summary_body, "최근 수집 상품이 없습니다.\n시트 연결 또는 정찰 실행 후 여기에 최근 수집 상품이 표시됩니다.")

        recent_rows = [(row.no, row.name, row.brand, row.category, row.updated, row.state) for row in overview["recent_rows"]]
        recent_card, _ = self.build_simple_table(
            self.body,
            "최근 수집 상품",
            [("no", "No.", 56), ("name", "상품명", 280), ("brand", "브랜드", 120), ("category", "카테고리", 110), ("updated", "업데이트", 100), ("state", "상태", 90)],
            recent_rows,
            min_height=TABLE_MIN_HEIGHT,
        )
        recent_card.grid(row=2, column=0, sticky="nsew")
