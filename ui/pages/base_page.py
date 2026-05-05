from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.theme import (
    ACTION_PANEL_HEIGHT,
    BUTTON_PRIMARY_ACTIVE,
    BUTTON_PRIMARY_BG,
    BUTTON_SECONDARY_ACTIVE,
    BUTTON_SECONDARY_BG,
    BUTTON_SUCCESS_ACTIVE,
    BUTTON_SUCCESS_BG,
    BUTTON_WARNING_ACTIVE,
    BUTTON_WARNING_BG,
    CARD_PADX,
    CARD_PADY,
    CHART_PANEL_HEIGHT,
    DETAIL_PAGE_RIGHT_WIDTH,
    BOTTOM_PANEL_HEIGHT,
    BOTTOM_TABLE_HEIGHT,
    HEADER_BADGE_BG,
    KPI_CARD_HEIGHT,
    LARGE_CARD,
    MEDIUM_CARD,
    PAGE_PADX,
    PAGE_PADY,
    PANEL_MIN_HEIGHT,
    PROGRESS_PANEL_HEIGHT,
    RIGHT_PANEL_WIDTH,
    SECTION_GAP,
    SMALL_CARD,
    SURFACE_BG,
    TABLE_MIN_HEIGHT,
)


class BasePage(tk.Frame):
    def __init__(self, parent: tk.Widget, controller, *, title: str, subtitle: str) -> None:
        super().__init__(parent, bg=controller.theme["bg"])
        self.controller = controller
        self.title_text = title
        self.subtitle_text = subtitle
        self.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.header = tk.Frame(self, bg=self.controller.theme["bg"])
        self.header.grid(row=0, column=0, sticky="ew", padx=PAGE_PADX, pady=(PAGE_PADY, SECTION_GAP))
        self.header.grid_columnconfigure(0, weight=1)

        self.body = tk.Frame(self, bg=self.controller.theme["bg"])
        self.body.grid(row=1, column=0, sticky="nsew", padx=PAGE_PADX, pady=(0, PAGE_PADY))
        self.body.grid_columnconfigure(0, weight=1)

    def configure_standard_page_grid(self) -> None:
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=0)
        self.body.grid_rowconfigure(1, weight=1)

    def build_header(self) -> None:
        self.header.grid_columnconfigure(0, weight=1)
        tk.Label(
            self.header,
            text=self.title_text,
            bg=self.controller.theme["bg"],
            fg=self.controller.theme["text"],
            font=("Segoe UI", 20, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            self.header,
            text=self.subtitle_text,
            bg=self.controller.theme["bg"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 9),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            self.header,
            textvariable=self.controller.data_source_var,
            bg=HEADER_BADGE_BG,
            fg="#93c5fd",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
        ).grid(row=0, column=1, sticky="e", padx=(0, 8))
        tk.Label(
            self.header,
            textvariable=self.controller.last_sync_var,
            bg=self.controller.theme["bg"],
            fg="#c7d2e4",
            font=("Segoe UI", 8),
        ).grid(row=0, column=2, sticky="e", padx=(0, 18))
        self.controller._mini_button(
            self.header,
            "새로고침",
            self.controller.refresh_dashboard_data,
            "#1e3350",
            "#294565",
        ).grid(row=0, column=3, sticky="e", padx=(0, 12))
        tk.Label(
            self.header,
            textvariable=self.controller.clock_var,
            bg=self.controller.theme["bg"],
            fg="#c7d2e4",
            font=("Segoe UI", 9),
        ).grid(row=0, column=4, sticky="e")
        tk.Label(
            self.header,
            textvariable=self.controller.data_source_detail_var,
            bg=self.controller.theme["bg"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 8),
        ).grid(row=1, column=1, columnspan=4, sticky="e", pady=(2, 0))

    def refresh_view(self) -> None:
        for child in self.header.winfo_children():
            child.destroy()
        for child in self.body.winfo_children():
            child.destroy()
        self.build()

    def build_metric_row(self, parent: tk.Widget, *, row: int, metrics: list[tuple[str, int, str]], accents: list[str] | None = None) -> tk.Frame:
        wrap = tk.Frame(parent, bg=self.controller.theme["bg"])
        wrap.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_GAP))
        accents = accents or [
            self.controller.theme["blue"],
            self.controller.theme["green"],
            self.controller.theme["red"],
            self.controller.theme["yellow"],
        ]
        for idx in range(len(metrics)):
            wrap.grid_columnconfigure(idx, weight=1, uniform="metric")
        for idx, (title, value, sub) in enumerate(metrics):
            value_var = tk.StringVar(value=f"{value:,}")
            self.controller._kpi_card(wrap, idx, title, value_var, sub, accents[idx % len(accents)])
        return wrap

    def resolve_card_height(self, level: str) -> int:
        return {
            "small": SMALL_CARD,
            "mid": MEDIUM_CARD,
            "medium": MEDIUM_CARD,
            "bottom": LARGE_CARD,
            "large": LARGE_CARD,
        }.get(level, MEDIUM_CARD)

    def build_dashboard_layout(self, metrics: list[tuple[str, int, str]]) -> tuple[tk.Frame, tk.Frame, tk.Frame]:
        self.configure_standard_page_grid()
        self.build_metric_row(self.body, row=0, metrics=metrics)
        shell = tk.Frame(self.body, bg=self.controller.theme["bg"])
        shell.grid(row=1, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=3, uniform="page_columns")
        shell.grid_columnconfigure(1, weight=2, uniform="page_columns")
        shell.grid_rowconfigure(0, weight=1)

        left = tk.Frame(shell, bg=self.controller.theme["bg"])
        right = tk.Frame(shell, bg=self.controller.theme["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SECTION_GAP))
        right.grid(row=0, column=1, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        return shell, left, right

    def build_panel_card(self, parent: tk.Widget, title: str, *, min_height: int | None = None, level: str = "mid", title_suffix: str = "") -> tuple[tk.Frame, tk.Frame]:
        min_height = self.resolve_card_height(level) if min_height is None else min_height
        card = self.controller._panel(parent, padx=CARD_PADX, pady=CARD_PADY)
        card.grid_propagate(False)
        card.configure(height=min_height)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        header = tk.Frame(card, bg=self.controller.theme["panel"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(header, text=title, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        if title_suffix:
            tk.Label(header, text=title_suffix, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e")
        body = tk.Frame(card, bg=self.controller.theme["panel"])
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        return card, body

    def build_chart_panel(
        self,
        parent: tk.Widget,
        title: str,
        *,
        values: list[int | float],
        labels: list[str] | None = None,
        accent: str | None = None,
        secondary: str | None = None,
        min_height: int = CHART_PANEL_HEIGHT,
        mode: str = "line",
        subtitle: str = "",
    ) -> tuple[tk.Frame, tk.Frame]:
        card, body = self.build_panel_card(parent, title, min_height=min_height, level="mid")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        accent = accent or self.controller.theme["blue"]
        secondary = secondary or self.controller.theme["green"]
        chart = tk.Canvas(body, bg=self.controller.theme["panel"], highlightthickness=0, height=max(120, min_height - 78))
        chart.grid(row=0, column=0, sticky="nsew")
        self._draw_chart(chart, values=values, labels=labels or [], accent=accent, secondary=secondary, mode=mode)
        if subtitle:
            tk.Label(
                body,
                text=subtitle,
                bg=self.controller.theme["panel"],
                fg=self.controller.theme["muted"],
                font=("Segoe UI", 8),
                wraplength=360,
                justify=tk.LEFT,
            ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        return card, body

    def build_progress_panel(
        self,
        parent: tk.Widget,
        title: str,
        *,
        percent: int,
        subtitle: str,
        accent: str,
        metrics: list[tuple[str, str]],
        min_height: int = PROGRESS_PANEL_HEIGHT,
    ) -> tuple[tk.Frame, tk.Frame]:
        card, body = self.build_panel_card(parent, title, min_height=min_height, level="mid")
        body.grid_columnconfigure(0, weight=1)
        tk.Label(body, text=f"{percent}%", bg=self.controller.theme["panel"], fg=accent, font=("Segoe UI", 22, "bold")).grid(row=0, column=0, sticky="w", pady=(4, 6))
        tk.Label(
            body,
            text=subtitle,
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 8),
            wraplength=360,
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))
        bar = tk.Canvas(body, height=10, bg=self.controller.theme["panel"], highlightthickness=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        width = 960
        bar.create_rectangle(0, 0, width, 10, fill="#21334d", outline="")
        bar.create_rectangle(0, 0, int(width * max(0, min(100, percent)) / 100), 10, fill=accent, outline="")
        self.build_mini_tiles(body, metrics, columns=2, start_row=3)
        return card, body

    def build_action_panel(
        self,
        parent: tk.Widget,
        title: str,
        *,
        actions: list[tuple[str, str, str, str, object]],
        details: list[tuple[str, str]] | None = None,
        min_height: int = ACTION_PANEL_HEIGHT,
    ) -> tuple[tk.Frame, tk.Frame]:
        card, body = self.build_panel_card(parent, title, min_height=min_height, level="mid")
        body.grid_columnconfigure(0, weight=1)
        row = 0
        for button_title, subtitle, bg, active_bg, command in actions:
            self.controller._mini_button(
                body,
                button_title,
                command,
                bg,
                active_bg,
            ).grid(row=row, column=0, sticky="ew", pady=(0, 4 if row < len(actions) - 1 else 0))
            row += 1
        if details:
            diagnostics = tk.Frame(body, bg=self.controller.theme["panel"])
            diagnostics.grid(row=row, column=0, sticky="nsew", pady=(8, 0))
            diagnostics.grid_columnconfigure(0, weight=1)
            self.build_dense_list(diagnostics, details)
        return card, body

    def build_action_tile(
        self,
        parent: tk.Widget,
        *,
        title: str,
        subtitle_var: tk.StringVar,
        bg: str,
        active: str,
        command,
    ) -> tk.Frame:
        frame = tk.Frame(parent, bg=bg, cursor="hand2", padx=12, pady=10, highlightthickness=1, highlightbackground="#334155")
        title_lbl = tk.Label(frame, text=title, bg=bg, fg="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w")
        sub_lbl = tk.Label(frame, textvariable=subtitle_var, bg=bg, fg="#dbeafe", font=("Segoe UI", 10), anchor="w")
        title_lbl.pack(anchor="w")
        sub_lbl.pack(anchor="w", pady=(6, 0))
        for widget in (frame, title_lbl, sub_lbl):
            widget.bind("<Enter>", lambda _e: (frame.configure(bg=active), title_lbl.configure(bg=active), sub_lbl.configure(bg=active)))
            widget.bind("<Leave>", lambda _e: (frame.configure(bg=bg), title_lbl.configure(bg=bg), sub_lbl.configure(bg=bg)))
            widget.bind("<Button-1>", lambda _e: command())
        return frame

    def build_recommended_action_tiles(
        self,
        parent: tk.Widget,
        title: str,
        actions: list[tuple[str, object, str, str, object]],
        *,
        columns: int = 4,
        min_height: int = 132,
        details: list[tuple[str, str]] | None = None,
    ) -> tuple[tk.Frame, tk.Frame, list[tk.StringVar]]:
        card, body = self.build_panel_card(parent, title, level="mid", min_height=min_height)
        column_count = max(1, min(columns, max(1, len(actions))))
        for col in range(column_count):
            body.grid_columnconfigure(col, weight=1, uniform="rec_actions")

        subtitle_vars: list[tk.StringVar] = []
        for idx, (button_title, subtitle, bg, active, command) in enumerate(actions):
            value = subtitle() if callable(subtitle) else subtitle
            sub_var = subtitle if isinstance(subtitle, tk.StringVar) else tk.StringVar(value=str(value or ""))
            subtitle_vars.append(sub_var)
            row = idx // column_count
            col = idx % column_count
            tile = self.build_action_tile(body, title=button_title, subtitle_var=sub_var, bg=bg, active=active, command=command)
            tile.grid(
                row=row,
                column=col,
                sticky="nsew",
                padx=(0 if col == 0 else 6, 0 if col == column_count - 1 else 6),
                pady=(0 if row == 0 else 6, 0),
            )

        if details:
            detail_row = (len(actions) + column_count - 1) // column_count
            diagnostics = tk.Frame(body, bg=self.controller.theme["panel"])
            diagnostics.grid(row=detail_row, column=0, columnspan=column_count, sticky="ew", pady=(10, 0))
            diagnostics.grid_columnconfigure(0, weight=1)
            self.build_dense_list(diagnostics, details)
        return card, body, subtitle_vars

    def build_simple_table(
        self,
        parent: tk.Widget,
        title: str,
        columns: list[tuple[str, str, int]],
        rows: list[tuple],
        *,
        min_height: int | None = None,
        level: str = "mid",
        empty_message: str = "",
        empty_action: tuple[str, object, str] | None = None,
    ) -> tuple[tk.Frame, ttk.Treeview]:
        min_height = self.resolve_card_height("bottom" if level == "bottom" else "mid") if min_height is None else min_height
        if min_height == LARGE_CARD and level == "bottom":
            min_height = BOTTOM_TABLE_HEIGHT
        card = self.controller._panel(parent, padx=CARD_PADX, pady=CARD_PADY)
        card.grid_propagate(False)
        card.configure(height=min_height)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        tk.Label(card, text=title, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        body = tk.Frame(card, bg=self.controller.theme["panel"])
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        table = ttk.Treeview(body, columns=[col[0] for col in columns], show="headings", style="Ops.Treeview", height=8)
        for key, label, width in columns:
            table.heading(key, text=label)
            table.column(key, width=width, minwidth=width, stretch=True)
        for data_row in rows:
            table.insert("", tk.END, values=data_row)
        table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        if not rows:
            table.grid_remove()
            scrollbar.grid_remove()
            self.build_empty_state(
                body,
                empty_message or "아직 연결된 데이터가 없습니다.\n먼저 데이터를 동기화하거나 해당 작업을 시작해 주세요.",
                action=empty_action,
            )
        return card, table

    def _draw_chart(
        self,
        canvas: tk.Canvas,
        *,
        values: list[int | float],
        labels: list[str],
        accent: str,
        secondary: str,
        mode: str,
    ) -> None:
        def redraw(_event=None) -> None:
            width = max(canvas.winfo_width(), 240)
            height = max(canvas.winfo_height(), 120)
            canvas.delete("all")
            if not values:
                canvas.create_text(width / 2, height / 2, text="표시할 지표가 없습니다", fill=self.controller.theme["muted"], font=("Segoe UI", 10, "bold"))
                return
            if mode == "donut":
                total = sum(max(float(v), 0.0) for v in values) or 1.0
                start = 90
                colors = [accent, self.controller.theme["yellow"], self.controller.theme["red"], secondary]
                size = min(width, height) - 24
                left = (width - size) / 2
                top = (height - size) / 2
                for idx, value in enumerate(values):
                    extent = -360 * max(float(value), 0.0) / total
                    color = colors[idx % len(colors)]
                    canvas.create_arc(left, top, left + size, top + size, start=start, extent=extent, fill=color, outline=color)
                    start += extent
                inner = size * 0.48
                canvas.create_oval(
                    left + (size - inner) / 2,
                    top + (size - inner) / 2,
                    left + (size + inner) / 2,
                    top + (size + inner) / 2,
                    fill=self.controller.theme["panel"],
                    outline=self.controller.theme["panel"],
                )
                percent = int(round((max(float(values[0]), 0.0) / total) * 100))
                canvas.create_text(width / 2, height / 2 - 6, text=f"{percent}%", fill=self.controller.theme["text"], font=("Segoe UI", 16, "bold"))
                canvas.create_text(width / 2, height / 2 + 14, text="성공률", fill=self.controller.theme["muted"], font=("Segoe UI", 8))
                return

            pad_x = 28
            pad_y = 18
            chart_w = max(80, width - pad_x * 2)
            chart_h = max(50, height - pad_y * 2 - 18)
            max_value = max(max(float(v), 0.0) for v in values) or 1.0
            points: list[tuple[float, float]] = []
            for idx, value in enumerate(values):
                x = pad_x + (chart_w * idx / max(1, len(values) - 1))
                y = pad_y + chart_h - (chart_h * max(float(value), 0.0) / max_value)
                points.append((x, y))
            for step in range(5):
                y = pad_y + chart_h * step / 4
                canvas.create_line(pad_x, y, pad_x + chart_w, y, fill="#1b2a40")
            flat_points = [coord for point in points for coord in point]
            if len(flat_points) >= 4:
                canvas.create_line(*flat_points, fill=accent, width=3, smooth=True)
            for idx, (x, y) in enumerate(points):
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=accent, outline=accent)
                if idx < len(labels):
                    canvas.create_text(x, height - 8, text=labels[idx], fill=self.controller.theme["muted"], font=("Segoe UI", 7))

        canvas.bind("<Configure>", redraw)
        canvas.after(30, redraw)

    def build_two_column_section(
        self,
        parent: tk.Widget,
        *,
        row: int,
        right_width: int = DETAIL_PAGE_RIGHT_WIDTH,
        pady: tuple[int, int] = (0, SECTION_GAP),
    ) -> tuple[tk.Frame, tk.Frame, tk.Frame]:
        shell = tk.Frame(parent, bg=self.controller.theme["bg"])
        shell.grid(row=row, column=0, sticky="nsew", pady=pady)
        shell.grid_columnconfigure(0, weight=3, uniform="page_columns")
        shell.grid_columnconfigure(1, weight=2, uniform="page_columns", minsize=right_width)
        shell.grid_rowconfigure(0, weight=1)

        left = tk.Frame(shell, bg=self.controller.theme["bg"])
        right = tk.Frame(shell, bg=self.controller.theme["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SECTION_GAP))
        right.grid(row=0, column=1, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        return shell, left, right

    def build_dense_list(self, parent: tk.Widget, rows: list[tuple[str, str]], *, accent: str | None = None) -> None:
        accent = accent or "#93c5fd"
        for idx, (label, value) in enumerate(rows):
            row = tk.Frame(parent, bg=self.controller.theme["panel"])
            row.grid(row=idx, column=0, sticky="ew", pady=(0, 6))
            row.grid_columnconfigure(1, weight=1)
            tk.Label(
                row,
                text=label,
                bg=self.controller.theme["panel"],
                fg=self.controller.theme["muted"],
                font=("Segoe UI", 8, "bold"),
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                row,
                text=value,
                bg=self.controller.theme["panel"],
                fg=accent,
                font=("Segoe UI", 9, "bold"),
                justify=tk.RIGHT,
                anchor="e",
            ).grid(row=0, column=1, sticky="e")

    def build_mini_tiles(self, parent: tk.Widget, tiles: list[tuple[str, str]], *, columns: int = 2, start_row: int = 0) -> None:
        for idx, (title, value) in enumerate(tiles):
            col = idx % columns
            row = start_row + idx // columns
            parent.grid_columnconfigure(col, weight=1, uniform="mini_tiles")
            tile = tk.Frame(parent, bg=SURFACE_BG, padx=10, pady=8, highlightbackground=self.controller.theme["line"], highlightthickness=1)
            tile.grid(row=row, column=col, sticky="nsew", padx=(0 if col == 0 else 4, 0), pady=(0, 4))
            tk.Label(tile, text=title, bg=SURFACE_BG, fg=self.controller.theme["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(tile, text=value, bg=SURFACE_BG, fg=self.controller.theme["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(6, 0))

    def build_empty_state(self, parent: tk.Widget, text: str, *, action: tuple[str, object, str] | None = None) -> None:
        wrap = tk.Frame(parent, bg=self.controller.theme["panel"])
        wrap.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        wrap.grid_columnconfigure(0, weight=1)
        tk.Label(
            wrap,
            text=text,
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 9, "bold"),
            justify=tk.LEFT,
            wraplength=360,
        ).grid(row=0, column=0, sticky="w")
        if action:
            label, command, tone = action
            self.build_action_button(wrap, label, command, tone=tone).grid(row=1, column=0, sticky="w", pady=(10, 0))

    def build_action_button(self, parent: tk.Widget, label: str, command, *, tone: str = "secondary"):
        palette = {
            "primary": (BUTTON_PRIMARY_BG, BUTTON_PRIMARY_ACTIVE),
            "secondary": (BUTTON_SECONDARY_BG, BUTTON_SECONDARY_ACTIVE),
            "success": (BUTTON_SUCCESS_BG, BUTTON_SUCCESS_ACTIVE),
            "warning": (BUTTON_WARNING_BG, BUTTON_WARNING_ACTIVE),
        }
        bg, active = palette.get(tone, palette["secondary"])
        return self.controller._mini_button(parent, label, command, bg, active)

    def get_empty_table_action(self, kind: str) -> tuple[str, object, str]:
        mapping = {
            "scout": ("데이터 수집 시작", lambda: self.controller.dispatch_ui_action("수집/정찰 시작", lambda: self.controller.run_action("run"), category="scout"), "success"),
            "image": ("이미지 저장 시작", lambda: self.controller.dispatch_ui_action("이미지 저장 실행", lambda: self.controller.run_action("save-images"), category="assets"), "secondary"),
            "upload": ("업로드 실행", lambda: self.controller.dispatch_ui_action("BUYMA 업로드 실행", lambda: self.controller.run_action("upload-auto"), category="buyma"), "warning"),
            "refresh": ("새로고침", self.controller.refresh_dashboard_data, "secondary"),
        }
        return mapping.get(kind, mapping["refresh"])

    def build_right_panel(self, parent: tk.Widget) -> None:
        parent.grid_columnconfigure(0, weight=1)
        self.controller._build_system_status_panel(parent)


class ScrollablePage(BasePage):
    def __init__(self, parent: tk.Widget, controller, *, title: str, subtitle: str) -> None:
        tk.Frame.__init__(self, parent, bg=controller.theme["bg"])
        self.controller = controller
        self.title_text = title
        self.subtitle_text = subtitle
        self.grid(row=0, column=0, sticky="nsew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg=controller.theme["bg"], highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.viewport = tk.Frame(self.canvas, bg=controller.theme["bg"])
        self.viewport.grid_columnconfigure(0, weight=1)
        self.window_id = self.canvas.create_window((0, 0), window=self.viewport, anchor="nw")
        self.viewport.bind("<Configure>", self._on_viewport_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        self.header = tk.Frame(self.viewport, bg=self.controller.theme["bg"])
        self.header.grid(row=0, column=0, sticky="ew", padx=PAGE_PADX, pady=(PAGE_PADY, SECTION_GAP))
        self.header.grid_columnconfigure(0, weight=1)

        self.body = tk.Frame(self.viewport, bg=self.controller.theme["bg"])
        self.body.grid(row=1, column=0, sticky="nsew", padx=PAGE_PADX, pady=(0, PAGE_PADY))
        self.body.grid_columnconfigure(0, weight=1)

    def _on_viewport_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if self.canvas.winfo_ismapped():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
