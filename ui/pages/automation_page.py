from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import ConsolePage


class AutomationPage(ConsolePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="감시 / 자동화", subtitle="watch, team watch, 자동화 이벤트를 운영 관점에서 확인합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_automation_overview()
        self.build_metric_row(self, overview["metrics"])

        wrap = tk.Frame(self, bg=self.controller.theme["bg"])
        wrap.pack(fill=tk.BOTH, expand=True)
        wrap.grid_columnconfigure(0, weight=3)
        wrap.grid_columnconfigure(1, weight=2)

        left = tk.Frame(wrap, bg=self.controller.theme["bg"])
        right = tk.Frame(wrap, bg=self.controller.theme["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew")

        cards = self.controller._panel(left, padx=12, pady=10)
        cards.pack(fill=tk.X, pady=(0, 12))
        tk.Label(cards, text="작업별 상태", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        row = tk.Frame(cards, bg=self.controller.theme["panel"])
        row.pack(fill=tk.X)
        for idx, (title, status, active) in enumerate(overview["team_cards"]):
            box = tk.Frame(row, bg="#122238", padx=12, pady=10, highlightbackground=self.controller.theme["line"], highlightthickness=1)
            box.grid(row=0, column=idx, sticky="nsew", padx=4)
            row.grid_columnconfigure(idx, weight=1)
            tk.Label(box, text=title, bg="#122238", fg=self.controller.theme["text"], font=("Segoe UI", 9, "bold")).pack(anchor="w")
            tk.Label(box, text=status, bg="#122238", fg=self.controller.theme["green"] if active else self.controller.theme["muted"], font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 0))

        log_card = self.controller._panel(left, padx=12, pady=10)
        log_card.pack(fill=tk.BOTH, expand=True)
        tk.Label(log_card, text="최근 자동화 이벤트 로그", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        log_view = tk.Text(log_card, height=16, bg="#081322", fg="#dbeafe", relief=tk.FLAT, borderwidth=0, wrap=tk.WORD)
        log_view.pack(fill=tk.BOTH, expand=True)
        log_text = "\n".join(self.controller.log_history[-30:]) if getattr(self.controller, "log_history", None) else "아직 수집된 자동화 이벤트가 없습니다."
        log_view.insert("1.0", log_text)
        log_view.configure(state=tk.DISABLED)

        action_card = self.controller._panel(right, padx=12, pady=10)
        action_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(action_card, text="제어", bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        self.controller._quick_button(
            action_card,
            "감시 시작",
            "watch 모드 실행",
            self.controller.theme["green"],
            lambda: self.controller.dispatch_ui_action("감시 시작", lambda: self.controller.run_action("watch"), category="automation"),
        )
        self.controller._quick_button(
            action_card,
            "감시 중지",
            "실행 중인 작업 종료",
            self.controller.theme["red"],
            lambda: self.controller.dispatch_ui_action("감시 중지", self.controller.stop_action, category="automation"),
        )
        self.controller._quick_button(
            action_card,
            "재시작",
            "상태 새로 고침",
            self.controller.theme["blue"],
            lambda: self.controller.dispatch_ui_action("감시/자동화 새로고침", self.controller.refresh_dashboard_data, category="automation"),
        )

        failure_rows = [(team, count) for team, count in overview["failures"].items()]
        self.build_simple_table(
            right,
            "실패 누적 / 재시도",
            [("team", "작업", 120), ("count", "실패 누적", 80)],
            failure_rows,
        )
