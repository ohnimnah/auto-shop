from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import ConsolePage


class ImageThumbnailPage(ConsolePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="이미지 / 썸네일", subtitle="상품 이미지 다운로드와 썸네일 제작 현황을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_image_overview()
        self.build_metric_row(self, overview["metrics"])

        body = tk.Frame(self, bg=self.controller.theme["bg"])
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)

        progress = self.controller._panel(body, padx=12, pady=10)
        progress.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 12))
        tk.Label(progress, text="이미지 진행률", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(progress, text=f"{int(overview['ratio'] * 100)}%", bg=self.controller.theme["panel"], fg=self.controller.theme["blue"], font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(8, 6))
        bar = tk.Canvas(progress, height=8, bg=self.controller.theme["panel"], highlightthickness=0)
        bar.pack(fill=tk.X)
        bar.create_rectangle(0, 0, 720, 8, fill="#21334d", outline="")
        bar.create_rectangle(0, 0, int(720 * overview["ratio"]), 8, fill=self.controller.theme["blue"], outline="")

        actions = self.controller._panel(body, padx=12, pady=10)
        actions.grid(row=0, column=1, sticky="nsew", pady=(0, 12))
        tk.Label(actions, text="작업", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        self.controller._quick_button(
            actions,
            "이미지 저장",
            "이미지 다운로드",
            self.controller.theme["blue"],
            lambda: self.controller.dispatch_ui_action("이미지 저장 실행", lambda: self.controller.run_action("save-images"), category="assets"),
        )
        self.controller._quick_button(
            actions,
            "썸네일 생성",
            "썸네일 일괄 제작",
            self.controller.theme["purple"],
            lambda: self.controller.dispatch_ui_action("썸네일 생성 실행", self.controller.run_thumbnail_action, category="design"),
        )
        self.controller._quick_button(
            actions,
            "실패 재시도",
            "이미지/썸네일 재처리",
            "#334155",
            lambda: self.controller.dispatch_ui_action("이미지/썸네일 실패 재시도", self.controller.refresh_dashboard_data, category="assets"),
        )

        lower = tk.Frame(body, bg=self.controller.theme["bg"])
        lower.grid(row=1, column=0, columnspan=2, sticky="nsew")
        left = tk.Frame(lower, bg=self.controller.theme["bg"])
        right = tk.Frame(lower, bg=self.controller.theme["bg"], width=320)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        right.pack(side=tk.RIGHT, fill=tk.BOTH)

        preview = self.controller._panel(left, padx=12, pady=10)
        preview.pack(fill=tk.BOTH, expand=True)
        tk.Label(preview, text="이미지 미리보기", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        grid = tk.Frame(preview, bg=self.controller.theme["panel"])
        grid.pack(fill=tk.BOTH, expand=True)
        preview_rows = overview["preview_rows"]
        if not preview_rows:
            tk.Label(grid, text="아직 표시할 이미지가 없습니다.", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="center", expand=True)
        else:
            for idx, row in enumerate(preview_rows):
                box = tk.Frame(grid, bg="#122238", highlightbackground=self.controller.theme["line"], highlightthickness=1)
                box.grid(row=idx // 4, column=idx % 4, sticky="nsew", padx=5, pady=5)
                tk.Label(box, text="IMAGE", bg="#091626", fg="#8da3bd", width=16, height=6, font=("Segoe UI", 8, "bold")).pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
                tk.Label(box, text=row.brand or row.name[:18], bg="#122238", fg=self.controller.theme["text"], font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8)
                tk.Label(box, text=row.name[:28], bg="#122238", fg=self.controller.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 8))

        failed_rows = [(row.no, row.name, row.brand, row.state) for row in overview["failed_rows"]]
        self.build_simple_table(
            right,
            "실패 이미지 목록",
            [("no", "No.", 56), ("name", "상품명", 220), ("brand", "브랜드", 100), ("state", "상태", 100)],
            failed_rows,
        )
