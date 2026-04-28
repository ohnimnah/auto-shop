from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import PANEL_MIN_HEIGHT, SECTION_GAP, TABLE_MIN_HEIGHT, ScrollablePage


class BuymaUploadPage(ScrollablePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="BUYMA 업로드", subtitle="BUYMA 상품 등록 현황과 실패 원인을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_upload_overview()
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(2, weight=1)

        self.build_metric_row(self.body, row=0, metrics=overview["metrics"])

        _shell, left, right = self.build_two_column_section(self.body, row=1)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(1, weight=1)

        ratio_card, ratio_body = self.build_panel_card(left, "업로드 성공률", min_height=160)
        ratio_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        tk.Label(ratio_body, text=f"{overview['success_ratio'] * 100:.1f}%", bg=self.controller.theme["panel"], fg=self.controller.theme["green"], font=("Segoe UI", 22, "bold")).grid(row=0, column=0, sticky="w", pady=(8, 6))
        tk.Label(ratio_body, text="오늘 업로드 완료 / 업로드 시도 기준", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=(0, 8))
        bar = tk.Canvas(ratio_body, height=8, bg=self.controller.theme["panel"], highlightthickness=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        bar.create_rectangle(0, 0, 960, 8, fill="#21334d", outline="")
        bar.create_rectangle(0, 0, int(960 * overview["success_ratio"]), 8, fill=self.controller.theme["green"], outline="")
        self.build_mini_tiles(
            ratio_body,
            [
                ("카테고리 실패", f"{overview['category_failures']}건"),
                ("기타 비율", f"{overview['other_ratio'] * 100:.1f}%"),
                ("recovery 성공률", f"{overview['recovery_success_ratio'] * 100:.1f}%"),
                ("업로드 상태", self.controller.state.pipeline_status.get("sales", "대기")),
            ],
            columns=2,
            start_row=3,
        )

        recent_card, _ = self.build_simple_table(
            left,
            "최근 업로드 상품",
            [("no", "No.", 56), ("name", "상품명", 250), ("brand", "브랜드", 100), ("price", "가격", 80), ("state", "상태", 100), ("updated", "업데이트", 110)],
            [(row.no, row.name, row.brand, row.price, row.state, row.updated) for row in overview["recent_rows"]],
            min_height=TABLE_MIN_HEIGHT,
        )
        recent_card.grid(row=1, column=0, sticky="nsew")

        side_card, side_body = self.build_panel_card(right, "업로드 제어", min_height=PANEL_MIN_HEIGHT + 32)
        side_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self.controller._quick_button(
            side_body,
            "업로드 실행",
            "BUYMA 자동 업로드",
            self.controller.theme["orange"],
            lambda: self.controller.dispatch_ui_action("BUYMA 업로드 실행", lambda: self.controller.run_action("upload-auto"), category="buyma"),
            auto_pack=False,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.controller._quick_button(
            side_body,
            "실패건 재실행",
            "오류 상품 재처리",
            "#334155",
            lambda: self.controller.dispatch_ui_action("BUYMA 실패건 재실행", lambda: self.controller.run_action("upload-review"), category="buyma"),
            auto_pack=False,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 6))
        self.controller._quick_button(
            side_body,
            "로그 보기",
            "실시간 로그 패널 확인",
            self.controller.theme["blue"],
            lambda: self.controller.dispatch_ui_action("BUYMA 업로드 로그 보기", lambda: self.controller.on_menu_click("대시보드"), category="buyma"),
            auto_pack=False,
        ).grid(row=4, column=0, sticky="ew")
        diagnostics = tk.Frame(side_body, bg=self.controller.theme["panel"])
        diagnostics.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.build_dense_list(
            diagnostics,
            [
                ("카테고리 실패", f"{overview['category_failures']}건"),
                ("기타(その他)", f"{overview['other_ratio'] * 100:.1f}%"),
                ("recovery 성공률", f"{overview['recovery_success_ratio'] * 100:.1f}%"),
                ("대기 상태", f"{overview['metrics'][3][1]}건"),
            ],
        )

        reasons_card, _ = self.build_simple_table(
            right,
            "실패 원인 / recovery 사용",
            [("reason", "실패 원인", 240), ("count", "건수", 70)],
            [(reason, count) for reason, count in overview["failure_reasons"]],
            min_height=TABLE_MIN_HEIGHT,
        )
        reasons_card.grid(row=1, column=0, sticky="nsew")

        recovery_card, recovery_body = self.build_panel_card(self.body, "Category Recovery Layer 진단", min_height=TABLE_MIN_HEIGHT)
        recovery_card.grid(row=2, column=0, sticky="nsew")
        self.build_mini_tiles(
            recovery_body,
            [
                ("alias 사용", f"{overview['recovery_counts'].get('alias', 0)}건"),
                ("fuzzy 사용", f"{overview['recovery_counts'].get('fuzzy', 0)}건"),
                ("same_parent 사용", f"{overview['recovery_counts'].get('same_parent_fallback', 0)}건"),
                ("기타 이동", f"{overview['recovery_counts'].get('other', 0)}건"),
            ],
            columns=4,
            start_row=0,
        )
