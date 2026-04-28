from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import BasePage, SECTION_GAP, SURFACE_BG
from ui.theme import ACTION_PANEL_HEIGHT, BOTTOM_TABLE_HEIGHT, BOTTOM_PANEL_HEIGHT, PROGRESS_PANEL_HEIGHT


class ImageThumbnailPage(BasePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="이미지 / 썸네일", subtitle="상품 이미지 다운로드와 썸네일 제작 현황을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_image_overview()
        _shell, left, right = self.build_dashboard_layout(overview["metrics"])
        left.grid_rowconfigure(0, weight=0)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)

        progress_card, progress_body = self.build_panel_card(left, "이미지 진행률", level="mid", min_height=PROGRESS_PANEL_HEIGHT)
        progress_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        progress_body.grid_columnconfigure(0, weight=1)
        tk.Label(progress_body, text=f"{int(overview['ratio'] * 100)}%", bg=self.controller.theme["panel"], fg=self.controller.theme["blue"], font=("Segoe UI", 22, "bold")).grid(row=0, column=0, sticky="w", pady=(4, 6))
        tk.Label(progress_body, text="이미지 저장 완료 비율", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=(0, 8))
        bar = tk.Canvas(progress_body, height=10, bg=self.controller.theme["panel"], highlightthickness=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        width = 960
        bar.create_rectangle(0, 0, width, 10, fill="#21334d", outline="")
        bar.create_rectangle(0, 0, int(width * max(0, min(100, int(overview["ratio"] * 100))) / 100), 10, fill=self.controller.theme["blue"], outline="")
        summary = tk.Frame(progress_body, bg=self.controller.theme["panel"])
        summary.grid(row=3, column=0, sticky="ew")
        summary.grid_columnconfigure(0, weight=1)
        summary.grid_columnconfigure(1, weight=1)
        tk.Label(summary, text=f"이미지 {self.controller.state.pipeline_status.get('assets', '대기')}", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(summary, text=f"실패 {len(overview['failed_rows'])}건", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e")

        preview_grid_card, preview_grid_body = self.build_panel_card(left, "이미지 미리보기", level="bottom", min_height=BOTTOM_PANEL_HEIGHT)
        preview_grid_card.grid(row=1, column=0, sticky="nsew")
        preview_grid_body.grid_rowconfigure(0, weight=1)
        preview_grid_body.grid_columnconfigure(0, weight=1)
        preview_wrap = tk.Frame(preview_grid_body, bg=self.controller.theme["panel"])
        preview_wrap.grid(row=0, column=0, sticky="nsew")
        preview_rows = overview["preview_rows"][:4]
        if preview_rows:
            for idx, row in enumerate(preview_rows):
                preview_wrap.grid_columnconfigure(idx % 4, weight=1, uniform="preview")
                tile = tk.Frame(preview_wrap, bg=SURFACE_BG, padx=8, pady=8, highlightbackground=self.controller.theme["line"], highlightthickness=1)
                tile.grid(row=idx // 4, column=idx % 4, sticky="nsew", padx=(0 if idx % 4 == 0 else 4, 0), pady=(0, 6))
                canvas = tk.Canvas(tile, width=56, height=56, bg="#0b1525", highlightthickness=0)
                canvas.pack(fill=tk.X)
                canvas.create_rectangle(6, 6, 50, 50, fill="#16263d", outline="#28456b")
                canvas.create_text(28, 28, text=(row.brand or "?")[:2].upper(), fill="#93c5fd", font=("Segoe UI", 12, "bold"))
                tk.Label(tile, text=row.name[:22], bg=SURFACE_BG, fg=self.controller.theme["text"], font=("Segoe UI", 8, "bold"), wraplength=100, justify=tk.LEFT).pack(anchor="w", pady=(6, 2))
                tk.Label(tile, text=row.state, bg=SURFACE_BG, fg=self.controller.theme["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        else:
            self.build_empty_state(preview_wrap, "표시할 이미지 미리보기가 없습니다.\n이미지 저장 또는 썸네일 생성 후 이 영역이 채워집니다.")

        actions_card, actions_body = self.build_action_panel(
            right,
            "작업 / 실패 현황",
            min_height=ACTION_PANEL_HEIGHT,
            actions=[
                ("이미지 저장", "이미지 다운로드", self.controller.theme["blue"], self.controller.theme["blue_2"], lambda: self.controller.dispatch_ui_action("이미지 저장 실행", lambda: self.controller.run_action("save-images"), category="assets")),
                ("썸네일 생성", "썸네일 일괄 제작", self.controller.theme["purple"], self.controller.theme["purple"], lambda: self.controller.dispatch_ui_action("썸네일 생성 실행", self.controller.run_thumbnail_action, category="design")),
                ("실패 재시도", "이미지/썸네일 재처리", "#334155", "#475569", lambda: self.controller.dispatch_ui_action("이미지/썸네일 실패 재시도", self.controller.refresh_dashboard_data, category="assets")),
            ],
            details=[
                ("실패 이미지", f"{len(overview['failed_rows'])}건"),
                ("썸네일 상태", self.controller.state.pipeline_status.get("design", "대기")),
                ("이미지 상태", self.controller.state.pipeline_status.get("assets", "대기")),
            ],
        )
        actions_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))

        failed_card, _ = self.build_simple_table(
            right,
            "실패 이미지 목록",
            [("no", "No.", 56), ("name", "상품명", 220), ("brand", "브랜드", 100), ("state", "상태", 100)],
            [(row.no, row.name, row.brand, row.state) for row in overview["failed_rows"]],
            level="bottom",
            min_height=BOTTOM_TABLE_HEIGHT,
            empty_message="현재 실패 이미지가 없습니다.\n이미지 저장 또는 썸네일 작업 실패 건이 생기면 이곳에 표시됩니다.",
            empty_action=self.get_empty_table_action("image"),
        )
        failed_card.grid(row=1, column=0, sticky="nsew")
