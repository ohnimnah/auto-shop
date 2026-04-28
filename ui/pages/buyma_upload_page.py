from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import ConsolePage


class BuymaUploadPage(ConsolePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="BUYMA 업로드", subtitle="BUYMA 상품 등록 현황과 실패 원인을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_upload_overview()
        self.build_metric_row(self, overview["metrics"])

        wrap = tk.Frame(self, bg=self.controller.theme["bg"])
        wrap.pack(fill=tk.BOTH, expand=True)
        wrap.grid_columnconfigure(0, weight=3)
        wrap.grid_columnconfigure(1, weight=2)

        ratio_card = self.controller._panel(wrap, padx=12, pady=10)
        ratio_card.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 12))
        tk.Label(ratio_card, text="업로드 성공률", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(ratio_card, text=f"{overview['success_ratio'] * 100:.1f}%", bg=self.controller.theme["panel"], fg=self.controller.theme["green"], font=("Segoe UI", 22, "bold")).pack(anchor="w", pady=(8, 6))
        bar = tk.Canvas(ratio_card, height=8, bg=self.controller.theme["panel"], highlightthickness=0)
        bar.pack(fill=tk.X)
        bar.create_rectangle(0, 0, 720, 8, fill="#21334d", outline="")
        bar.create_rectangle(0, 0, int(720 * overview["success_ratio"]), 8, fill=self.controller.theme["green"], outline="")

        side = self.controller._panel(wrap, padx=12, pady=10)
        side.grid(row=0, column=1, sticky="nsew", pady=(0, 12))
        tk.Label(side, text="업로드 상태", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        tk.Label(side, text=f"카테고리 실패 수  {overview['category_failures']}", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=3)
        tk.Label(side, text=f"기타(その他) 비율  {overview['other_ratio'] * 100:.1f}%", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=3)
        self.controller._quick_button(
            side,
            "업로드 실행",
            "BUYMA 자동 업로드",
            self.controller.theme["orange"],
            lambda: self.controller.dispatch_ui_action("BUYMA 업로드 실행", lambda: self.controller.run_action("upload-auto"), category="buyma"),
        )
        self.controller._quick_button(
            side,
            "실패건 재실행",
            "오류 상품 재처리",
            "#334155",
            lambda: self.controller.dispatch_ui_action("BUYMA 실패건 재실행", lambda: self.controller.run_action("upload-review"), category="buyma"),
        )
        self.controller._quick_button(
            side,
            "로그 보기",
            "실시간 로그 패널 확인",
            self.controller.theme["blue"],
            lambda: self.controller.dispatch_ui_action("BUYMA 업로드 로그 보기", lambda: self.controller.on_menu_click("대시보드"), category="buyma"),
        )

        lower = tk.Frame(wrap, bg=self.controller.theme["bg"])
        lower.grid(row=1, column=0, columnspan=2, sticky="nsew")
        left = tk.Frame(lower, bg=self.controller.theme["bg"])
        right = tk.Frame(lower, bg=self.controller.theme["bg"], width=320)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        right.pack(side=tk.RIGHT, fill=tk.BOTH)

        recent_rows = [
            (row.no, row.name, row.brand, row.price, row.state, row.updated)
            for row in overview["recent_rows"]
        ]
        self.build_simple_table(
            left,
            "최근 업로드 상품",
            [("no", "No.", 56), ("name", "상품명", 250), ("brand", "브랜드", 100), ("price", "가격", 80), ("state", "상태", 100), ("updated", "업데이트", 110)],
            recent_rows,
        )

        reasons = [(reason, count) for reason, count in overview["failure_reasons"]]
        self.build_simple_table(
            right,
            "실패 원인별 집계",
            [("reason", "실패 원인", 240), ("count", "건수", 70)],
            reasons,
        )
