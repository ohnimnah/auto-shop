from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import PANEL_MIN_HEIGHT, SECTION_GAP, TABLE_MIN_HEIGHT, ScrollablePage, SURFACE_BG


class ImageThumbnailPage(ScrollablePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="이미지 / 썸네일", subtitle="상품 이미지 다운로드와 썸네일 제작 현황을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_image_overview()
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(2, weight=1)

        self.build_metric_row(self.body, row=0, metrics=overview["metrics"])

        _shell, left, right = self.build_two_column_section(self.body, row=1)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(1, weight=1)

        progress_card, progress_body = self.build_panel_card(left, "이미지 진행률", min_height=150)
        progress_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        tk.Label(progress_body, text=f"{int(overview['ratio'] * 100)}%", bg=self.controller.theme["panel"], fg=self.controller.theme["blue"], font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w", pady=(8, 6))
        tk.Label(progress_body, text="전체 상품 대비 이미지 저장 완료 비율", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=(0, 8))
        bar = tk.Canvas(progress_body, height=8, bg=self.controller.theme["panel"], highlightthickness=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        bar.create_rectangle(0, 0, 960, 8, fill="#21334d", outline="")
        bar.create_rectangle(0, 0, int(960 * overview["ratio"]), 8, fill=self.controller.theme["blue"], outline="")
        self.build_mini_tiles(
            progress_body,
            [
                ("이미지 워커", self.controller.state.pipeline_status.get("assets", "대기")),
                ("썸네일 워커", self.controller.state.pipeline_status.get("design", "대기")),
                ("실패 건수", str(len(overview["failed_rows"]))),
                ("데이터 소스", self.controller.state.data_source.label),
            ],
            columns=2,
            start_row=3,
        )

        preview_grid_card, preview_grid_body = self.build_panel_card(left, "이미지 미리보기", min_height=TABLE_MIN_HEIGHT)
        preview_grid_card.grid(row=1, column=0, sticky="nsew")
        preview_rows = overview["preview_rows"][:8]
        if preview_rows:
            for idx, row in enumerate(preview_rows):
                preview_grid_body.grid_columnconfigure(idx % 4, weight=1, uniform="preview")
                tile = tk.Frame(preview_grid_body, bg=SURFACE_BG, padx=8, pady=8, highlightbackground=self.controller.theme["line"], highlightthickness=1)
                tile.grid(row=idx // 4, column=idx % 4, sticky="nsew", padx=(0 if idx % 4 == 0 else 4, 0), pady=(0, 6))
                canvas = tk.Canvas(tile, width=72, height=72, bg="#0b1525", highlightthickness=0)
                canvas.pack(fill=tk.X)
                canvas.create_rectangle(8, 8, 64, 64, fill="#16263d", outline="#28456b")
                canvas.create_text(36, 36, text=(row.brand or "?")[:2].upper(), fill="#93c5fd", font=("Segoe UI", 14, "bold"))
                tk.Label(tile, text=row.name[:26], bg=SURFACE_BG, fg=self.controller.theme["text"], font=("Segoe UI", 8, "bold"), wraplength=120, justify=tk.LEFT).pack(anchor="w", pady=(6, 2))
                tk.Label(tile, text=row.state, bg=SURFACE_BG, fg=self.controller.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        else:
            self.build_empty_state(preview_grid_body, "표시할 이미지 미리보기가 없습니다.\n이미지 저장 또는 썸네일 생성 후 이 영역이 채워집니다.")

        actions_card, actions_body = self.build_panel_card(right, "작업 / 실패 현황", min_height=PANEL_MIN_HEIGHT + 24)
        actions_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self.controller._quick_button(
            actions_body,
            "이미지 저장",
            "이미지 다운로드",
            self.controller.theme["blue"],
            lambda: self.controller.dispatch_ui_action("이미지 저장 실행", lambda: self.controller.run_action("save-images"), category="assets"),
            auto_pack=False,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.controller._quick_button(
            actions_body,
            "썸네일 생성",
            "썸네일 일괄 제작",
            self.controller.theme["purple"],
            lambda: self.controller.dispatch_ui_action("썸네일 생성 실행", self.controller.run_thumbnail_action, category="design"),
            auto_pack=False,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.controller._quick_button(
            actions_body,
            "실패 재시도",
            "이미지/썸네일 재처리",
            "#334155",
            lambda: self.controller.dispatch_ui_action("이미지/썸네일 실패 재시도", self.controller.refresh_dashboard_data, category="assets"),
            auto_pack=False,
        ).grid(row=2, column=0, sticky="ew")
        diagnostics = tk.Frame(actions_body, bg=self.controller.theme["panel"])
        diagnostics.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.build_dense_list(
            diagnostics,
            [
                ("실패 이미지", f"{len(overview['failed_rows'])}건"),
                ("누락 이미지", f"{overview['metrics'][2][1]}건"),
                ("썸네일 상태", self.controller.state.pipeline_status.get("design", "대기")),
                ("이미지 상태", self.controller.state.pipeline_status.get("assets", "대기")),
            ],
            accent="#93c5fd",
        )

        failed_card, _ = self.build_simple_table(
            right,
            "실패 이미지 목록",
            [("no", "No.", 56), ("name", "상품명", 220), ("brand", "브랜드", 100), ("state", "상태", 100)],
            [(row.no, row.name, row.brand, row.state) for row in overview["failed_rows"]],
            min_height=TABLE_MIN_HEIGHT,
        )
        failed_card.grid(row=1, column=0, sticky="nsew")

        detail_card, _ = self.build_simple_table(
            self.body,
            "이미지 작업 상세",
            [("brand", "브랜드", 120), ("name", "상품명", 260), ("state", "상태", 110)],
            [(row.brand or "-", row.name, row.state) for row in overview["preview_rows"]],
            min_height=TABLE_MIN_HEIGHT,
        )
        detail_card.grid(row=2, column=0, sticky="nsew")
