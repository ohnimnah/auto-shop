from __future__ import annotations

import tkinter as tk
from tkinter import ttk


PAGE_PADX = 4
PAGE_PADY = 2
SECTION_GAP = 12
CARD_PADX = 12
CARD_PADY = 10
RIGHT_PANEL_WIDTH = 300
SIDE_PANEL_WIDTH = 320
TABLE_MIN_HEIGHT = 280
PANEL_MIN_HEIGHT = 180
HEADER_BADGE_BG = "#102033"
SURFACE_BG = "#122238"


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

    def build_panel_card(self, parent: tk.Widget, title: str, *, min_height: int = PANEL_MIN_HEIGHT) -> tuple[tk.Frame, tk.Frame]:
        card = self.controller._panel(parent, padx=CARD_PADX, pady=CARD_PADY)
        card.grid_propagate(False)
        card.configure(height=min_height)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        tk.Label(card, text=title, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        body = tk.Frame(card, bg=self.controller.theme["panel"])
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        return card, body

    def build_simple_table(self, parent: tk.Widget, title: str, columns: list[tuple[str, str, int]], rows: list[tuple], *, min_height: int = TABLE_MIN_HEIGHT) -> tuple[tk.Frame, ttk.Treeview]:
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
            tk.Label(body, text="표시할 데이터가 없습니다.", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9, "bold")).place(relx=0.5, rely=0.5, anchor="center")
        return card, table

    def build_two_column_section(
        self,
        parent: tk.Widget,
        *,
        row: int,
        right_width: int = SIDE_PANEL_WIDTH,
        pady: tuple[int, int] = (0, SECTION_GAP),
    ) -> tuple[tk.Frame, tk.Frame, tk.Frame]:
        shell = tk.Frame(parent, bg=self.controller.theme["bg"])
        shell.grid(row=row, column=0, sticky="nsew", pady=pady)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_columnconfigure(1, minsize=right_width)
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

    def build_empty_state(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=self.controller.theme["panel"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 9, "bold"),
            justify=tk.LEFT,
            wraplength=320,
        ).grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

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
