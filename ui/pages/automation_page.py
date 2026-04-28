from __future__ import annotations

import tkinter as tk

from ui.pages.base_page import PANEL_MIN_HEIGHT, SECTION_GAP, TABLE_MIN_HEIGHT, ScrollablePage


class AutomationPage(ScrollablePage):
    def __init__(self, parent: tk.Widget, controller) -> None:
        super().__init__(parent, controller, title="감시 / 자동화", subtitle="watch, team watch, 자동화 이벤트를 운영 관점에서 확인합니다.")
        self.build()

    def build(self) -> None:
        self.build_header()
        overview = self.controller.dashboard_data.get_automation_overview()
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(2, weight=1)

        self.build_metric_row(self.body, row=0, metrics=overview["metrics"])

        _shell, left, right = self.build_two_column_section(self.body, row=1)
        left.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(1, weight=1)

        cards_card, cards_body = self.build_panel_card(left, "작업별 상태", min_height=160)
        cards_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        for idx, (title, status, active) in enumerate(overview["team_cards"]):
            cards_body.grid_columnconfigure(idx, weight=1, uniform="team")
            box = tk.Frame(cards_body, bg="#122238", padx=12, pady=10, highlightbackground=self.controller.theme["line"], highlightthickness=1)
            box.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 4, 0))
            tk.Label(box, text=title, bg="#122238", fg=self.controller.theme["text"], font=("Segoe UI", 9, "bold")).pack(anchor="w")
            tk.Label(box, text=status, bg="#122238", fg=self.controller.theme["green"] if active else self.controller.theme["muted"], font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 0))
            tk.Label(box, text="활성" if active else "대기", bg="#122238", fg="#93c5fd" if active else self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(4, 0))

        log_card, log_body = self.build_panel_card(left, "최근 자동화 이벤트 로그", min_height=TABLE_MIN_HEIGHT)
        log_card.grid(row=1, column=0, sticky="nsew")
        log_body.grid_rowconfigure(0, weight=1)
        log_view = tk.Text(log_body, height=16, bg="#081322", fg="#dbeafe", relief=tk.FLAT, borderwidth=0, wrap=tk.WORD)
        log_view.grid(row=0, column=0, sticky="nsew")
        log_scroll = tk.Scrollbar(log_body, orient=tk.VERTICAL, command=log_view.yview)
        log_view.configure(yscrollcommand=log_scroll.set)
        log_scroll.grid(row=0, column=1, sticky="ns")
        log_text = "\n".join(overview["recent_logs"]) if overview["recent_logs"] else "아직 수집된 자동화 이벤트가 없습니다."
        log_view.insert("1.0", log_text)
        log_view.configure(state=tk.DISABLED)

        action_card, action_body = self.build_panel_card(right, "감시 제어", min_height=PANEL_MIN_HEIGHT + 36)
        action_card.grid(row=0, column=0, sticky="ew", pady=(0, SECTION_GAP))
        self.controller._quick_button(
            action_body,
            "감시 시작",
            "watch 모드 실행",
            self.controller.theme["green"],
            lambda: self.controller.dispatch_ui_action("감시 시작", lambda: self.controller.run_action("watch"), category="automation"),
            auto_pack=False,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.controller._quick_button(
            action_body,
            "감시 중지",
            "실행 중인 작업 종료",
            self.controller.theme["red"],
            lambda: self.controller.dispatch_ui_action("감시 중지", self.controller.stop_action, category="automation"),
            auto_pack=False,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.controller._quick_button(
            action_body,
            "재시작",
            "상태 새로 고침",
            self.controller.theme["blue"],
            lambda: self.controller.dispatch_ui_action("감시/자동화 새로고침", self.controller.refresh_dashboard_data, category="automation"),
            auto_pack=False,
        ).grid(row=2, column=0, sticky="ew")
        worker_actions = tk.Frame(action_body, bg=self.controller.theme["panel"])
        worker_actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        worker_actions.grid_columnconfigure(0, weight=1)
        worker_actions.grid_columnconfigure(1, weight=1)
        self.controller._mini_button(
            worker_actions,
            "이미지 워커",
            lambda: self.controller.dispatch_ui_action("이미지 워커 감시 토글", lambda: self.controller._toggle_team_watch("assets"), category="automation"),
            "#1e3350",
            "#294565",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.controller._mini_button(
            worker_actions,
            "업로드 워커",
            lambda: self.controller.dispatch_ui_action("업로드 워커 감시 토글", lambda: self.controller._toggle_team_watch("sales"), category="automation"),
            "#1e3350",
            "#294565",
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        failures_card, _ = self.build_simple_table(
            right,
            "실패 누적 / 재시도",
            [("team", "작업", 120), ("count", "실패 누적", 80)],
            [(team, count) for team, count in overview["failures"].items()],
            min_height=TABLE_MIN_HEIGHT,
        )
        failures_card.grid(row=1, column=0, sticky="nsew")

        worker_card, worker_body = self.build_panel_card(self.body, "워커 실행 상태", min_height=TABLE_MIN_HEIGHT)
        worker_card.grid(row=2, column=0, sticky="nsew")
        self.build_mini_tiles(
            worker_body,
            [
                ("정찰", self.controller.state.pipeline_status.get("scout", "대기")),
                ("이미지", self.controller.state.pipeline_status.get("assets", "대기")),
                ("썸네일", self.controller.state.pipeline_status.get("design", "대기")),
                ("업로드", self.controller.state.pipeline_status.get("sales", "대기")),
            ],
            columns=4,
            start_row=0,
        )
