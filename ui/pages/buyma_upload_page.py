from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import BasePage, SECTION_GAP
from ui.theme import ACTION_PANEL_HEIGHT, BOTTOM_TABLE_HEIGHT, CHART_PANEL_HEIGHT


class BuymaUploadPage(BasePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="BUYMA 업로드", subtitle="BUYMA 상품 등록 현황과 실패 원인을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_upload_overview()
        self.configure_standard_page_grid()
        self.body.grid_rowconfigure(1, weight=0)
        self.body.grid_rowconfigure(2, weight=1)
        self.build_metric_row(self.body, row=0, metrics=overview["metrics"])

        action_card, _action_body, _ = self.build_recommended_action_tiles(
            self.body,
            "권장 작업",
            [
                ("검토 후 업로드", "브라우저에서 확인 후 제출", self.controller.theme["orange"], self.controller.theme["orange"], lambda: self.controller.dispatch_ui_action("BUYMA 검토 후 업로드", lambda: self.controller.run_action("upload-review"), category="buyma")),
                ("자동 업로드", "오류 없으면 자동 제출", "#334155", "#475569", lambda: self.controller.dispatch_ui_action("BUYMA 자동 업로드", lambda: self.controller.run_action("upload-auto"), category="buyma")),
                ("로그 보기", "실시간 로그 패널 확인", self.controller.theme["blue"], self.controller.theme["blue_2"], lambda: self.controller.dispatch_ui_action("BUYMA 업로드 로그 보기", lambda: self.controller.on_menu_click("대시보드"), category="buyma")),
                ("현재 작업 중지", "실행 중인 업로드 종료", self.controller.theme["red"], "#991b1b", lambda: self.controller.dispatch_ui_action("BUYMA 작업 중지", self.controller.stop_action, category="buyma")),
            ],
            columns=4,
            min_height=132,
        )
        action_card.grid(row=1, column=0, sticky="ew", pady=(0, SECTION_GAP))

        shell = tk.Frame(self.body, bg=self.controller.theme["bg"])
        shell.grid(row=2, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=3, uniform="page_columns")
        shell.grid_columnconfigure(1, weight=2, uniform="page_columns")
        shell.grid_rowconfigure(0, weight=1)

        left = tk.Frame(shell, bg=self.controller.theme["bg"])
        right = tk.Frame(shell, bg=self.controller.theme["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SECTION_GAP))
        right.grid(row=0, column=1, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=0)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)

        ratio_card, ratio_body = self.build_chart_panel(
            left,
            "업로드 성공률",
            values=[
                overview["metrics"][1][1],
                overview["metrics"][2][1],
                overview["category_failures"],
                max(1, int(round(overview["other_ratio"] * max(overview["metrics"][0][1], 1)))),
            ],
            labels=["성공", "실패", "카테고리", "기타"],
            accent=self.controller.theme["green"],
            secondary=self.controller.theme["yellow"],
            min_height=CHART_PANEL_HEIGHT,
            mode="donut",
            subtitle="오늘 업로드 결과와 category recovery 후속 상태를 요약합니다.",
        )
        ratio_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        summary = tk.Frame(ratio_body, bg=self.controller.theme["panel"])
        summary.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        summary.grid_columnconfigure(0, weight=1)
        summary.grid_columnconfigure(1, weight=1)
        tk.Label(summary, text=f"성공률 {overview['success_ratio'] * 100:.1f}%", bg=self.controller.theme["panel"], fg=self.controller.theme["green"], font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(summary, text=f"카테고리 실패 {overview['category_failures']}건", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e")

        recent_card, _ = self.build_simple_table(
            left,
            "최근 업로드 상품",
            [("no", "No.", 56), ("name", "상품명", 250), ("brand", "브랜드", 100), ("price", "가격", 80), ("state", "상태", 100), ("updated", "업데이트", 110)],
            [(row.no, row.name, row.brand, row.price, row.state, row.updated) for row in overview["recent_rows"]],
            level="bottom",
            min_height=BOTTOM_TABLE_HEIGHT,
            empty_message="최근 업로드 상품이 없습니다.\n업로드를 실행하면 최근 처리한 상품이 여기에 표시됩니다.",
            empty_action=self.get_empty_table_action("upload"),
        )
        recent_card.grid(row=1, column=0, sticky="nsew")

        side_card, side_body = self.build_panel_card(right, "업로드 상태", level="mid", min_height=ACTION_PANEL_HEIGHT)
        side_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        side_body.grid_columnconfigure(0, weight=1)
        self.build_dense_list(
            side_body,
            [
                ("카테고리 실패", f"{overview['category_failures']}건"),
                ("기타(その他)", f"{overview['other_ratio'] * 100:.1f}%"),
                ("업로드 상태", self.controller.state.pipeline_status.get("sales", "대기")),
            ],
        )

        reasons_card, _ = self.build_simple_table(
            right,
            "Recovery / 실패 원인",
            [("reason", "실패 원인", 240), ("count", "건수", 70)],
            [(reason, count) for reason, count in overview["failure_reasons"]],
            level="bottom",
            min_height=BOTTOM_TABLE_HEIGHT,
            empty_message="현재 집계된 업로드 실패 원인이 없습니다.\n실패가 발생하면 recovery 진단과 함께 이 영역이 채워집니다.",
            empty_action=self.get_empty_table_action("upload"),
        )
        reasons_card.grid(row=1, column=0, sticky="nsew")
