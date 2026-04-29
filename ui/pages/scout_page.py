from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.pages.base_page import BasePage, SECTION_GAP
from ui.theme import BOTTOM_TABLE_HEIGHT, CHART_PANEL_HEIGHT, ACTION_PANEL_HEIGHT


class ScoutPage(BasePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="수집 / 정찰", subtitle="BUYMA 상품 등록 전 수집 및 정찰 현황을 관리합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_scout_overview()
        _shell, left, right = self.build_dashboard_layout(overview["metrics"])
        left.grid_rowconfigure(0, weight=0)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)

        chart_values = [count for _name, count in overview["category_rows"][:6]]
        chart_labels = [name[:6] for name, _count in overview["category_rows"][:6]]
        if not chart_values:
            chart_values = [overview["metrics"][1][1], overview["metrics"][2][1], overview["metrics"][3][1], max(overview["metrics"][0][1], 1)]
            chart_labels = ["수집", "실패", "진행", "전체"]

        progress_card, progress_body = self.build_chart_panel(
            left,
            "수집 추이 / 분포",
            values=chart_values,
            labels=chart_labels,
            accent=self.controller.theme["green"],
            min_height=CHART_PANEL_HEIGHT,
            subtitle="최근 수집 결과를 기준으로 카테고리별 분포를 요약합니다.",
        )
        progress_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))

        summary = tk.Frame(progress_body, bg=self.controller.theme["panel"])
        summary.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        summary.grid_columnconfigure(0, weight=1)
        summary.grid_columnconfigure(1, weight=1)

        tk.Label(
            summary,
            text=f"수집 비율 {int(overview['ratio'] * 100)}%",
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["green"],
            font=("Segoe UI", 8, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            summary,
            text=f"정찰 단계 {self.controller.state.pipeline_status.get('scout', '대기')}",
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 8),
        ).grid(row=0, column=1, sticky="e")

        unresolved_ratio_text = f"미분류 비율: {overview.get('unresolved_ratio', 0.0) * 100:.1f}%"
        unresolved_color = self.controller.theme["red"] if overview.get("category_tuning_required", False) else self.controller.theme["muted"]
        tk.Label(
            summary,
            text=unresolved_ratio_text,
            bg=self.controller.theme["panel"],
            fg=unresolved_color,
            font=("Segoe UI", 8, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        status = overview.get("unresolved_status", "OK")
        if status == "OK":
            status_color = self.controller.theme["green"]
        elif status == "WARNING":
            status_color = self.controller.theme["yellow"]
        else:
            status_color = self.controller.theme["red"]
        tk.Label(
            summary,
            text=f"상태: {status}",
            bg=self.controller.theme["panel"],
            fg=status_color,
            font=("Segoe UI", 8, "bold"),
        ).grid(row=1, column=1, sticky="e", pady=(4, 0))
        if overview.get("category_tuning_required", False):
            tk.Label(
                summary,
                text="카테고리 튜닝 필요",
                bg=self.controller.theme["panel"],
                fg=self.controller.theme["red"],
                font=("Segoe UI", 8, "bold"),
            ).grid(row=2, column=1, sticky="e", pady=(2, 0))

        recent_rows = [(row.no, row.name, row.brand, row.category, row.updated, row.state) for row in overview["recent_rows"]]
        recent_card, _ = self.build_simple_table(
            left,
            "최근 수집 상품",
            [("no", "No.", 56), ("name", "상품명", 280), ("brand", "브랜드", 120), ("category", "카테고리", 110), ("updated", "업데이트", 100), ("state", "상태", 90)],
            recent_rows,
            level="bottom",
            min_height=BOTTOM_TABLE_HEIGHT,
            empty_message="최근 수집 상품이 없습니다.\n수집을 시작하면 최신 결과가 여기에 표시됩니다.",
            empty_action=self.get_empty_table_action("scout"),
        )
        recent_card.grid(row=1, column=0, sticky="nsew")

        filter_card, filter_body = self.build_panel_card(right, "필터 / 실행", level="mid", min_height=ACTION_PANEL_HEIGHT)
        filter_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        filter_body.grid_columnconfigure(0, weight=1)

        diagnostics = tk.Frame(filter_body, bg=self.controller.theme["panel"])
        diagnostics.grid(row=0, column=0, sticky="ew", pady=(8, 0))
        self.build_dense_list(
            diagnostics,
            [
                ("정찰 상태", self.controller.state.pipeline_status.get("scout", "대기")),
                ("완료 건수", f"{overview['metrics'][1][1]}건"),
                ("실패/대기", f"{overview['metrics'][2][1]} / {overview['metrics'][3][1]}"),
                ("미분류", f"{overview.get('unresolved_count', 0)}건"),
            ],
        )

        category_card, _ = self.build_simple_table(
            right,
            "카테고리 수집 현황",
            [("category", "카테고리", 180), ("count", "건수", 80)],
            [(name, count) for name, count in overview["category_rows"]],
            level="bottom",
            min_height=BOTTOM_TABLE_HEIGHT,
            empty_message="아직 카테고리별 수집 결과가 없습니다.\n정찰을 실행하면 카테고리 분포가 여기에 표시됩니다.",
            empty_action=self.get_empty_table_action("scout"),
        )
        category_card.grid(row=1, column=0, sticky="nsew")
        all_rows = list(overview.get("category_rows_all", overview.get("category_rows", [])))
        if len(all_rows) > len(overview.get("category_rows", [])):
            more_wrap = tk.Frame(category_card, bg=self.controller.theme["panel"])
            more_wrap.grid(row=2, column=0, sticky="e", pady=(6, 0))
            self.build_action_button(
                more_wrap,
                "더보기",
                lambda rows=all_rows: self._open_all_categories_dialog(rows),
                tone="secondary",
            ).grid(row=0, column=0, sticky="e")

    def _open_all_categories_dialog(self, category_rows: list[tuple[str, int]]) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("카테고리 수집현황 - 전체")
        dlg.configure(bg=self.controller.theme["bg"])
        dlg.geometry("520x620")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        outer = tk.Frame(dlg, bg=self.controller.theme["bg"], padx=12, pady=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        tk.Label(
            outer,
            text=f"전체 카테고리 ({len(category_rows)}개)",
            bg=self.controller.theme["bg"],
            fg=self.controller.theme["text"],
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        table_wrap = tk.Frame(outer, bg=self.controller.theme["panel"])
        table_wrap.grid(row=1, column=0, sticky="nsew")
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(0, weight=1)

        table = ttk.Treeview(
            table_wrap,
            columns=("category", "count"),
            show="headings",
            style="Ops.Treeview",
        )
        table.heading("category", text="카테고리")
        table.heading("count", text="건수")
        table.column("category", width=360, minwidth=260, stretch=True)
        table.column("count", width=100, minwidth=80, stretch=False, anchor="center")
        for name, count in category_rows:
            table.insert("", tk.END, values=(name, count))
        table.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        btn_wrap = tk.Frame(outer, bg=self.controller.theme["bg"])
        btn_wrap.grid(row=2, column=0, sticky="e", pady=(10, 0))
        self.build_action_button(btn_wrap, "닫기", dlg.destroy, tone="secondary").grid(row=0, column=0, sticky="e")
