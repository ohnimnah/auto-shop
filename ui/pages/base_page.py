from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ConsolePage(tk.Frame):
    def __init__(self, parent: tk.Widget, controller, *, title: str, subtitle: str) -> None:
        super().__init__(parent, bg=controller.theme["bg"])
        self.controller = controller
        self.title_text = title
        self.subtitle_text = subtitle

    def build_header(self) -> None:
        header = tk.Frame(self, bg=self.controller.theme["bg"])
        header.pack(fill=tk.X, pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text=self.title_text,
            bg=self.controller.theme["bg"],
            fg=self.controller.theme["text"],
            font=("Segoe UI", 20, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text=self.subtitle_text,
            bg=self.controller.theme["bg"],
            fg=self.controller.theme["muted"],
            font=("Segoe UI", 9),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(
            header,
            textvariable=self.controller.data_source_var,
            bg="#102033",
            fg="#93c5fd",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
        ).grid(row=0, column=1, sticky="e", padx=(0, 8))
        tk.Label(
            header,
            textvariable=self.controller.last_sync_var,
            bg=self.controller.theme["bg"],
            fg="#c7d2e4",
            font=("Segoe UI", 8),
        ).grid(row=0, column=2, sticky="e", padx=(0, 18))
        tk.Label(
            header,
            textvariable=self.controller.clock_var,
            bg=self.controller.theme["bg"],
            fg="#c7d2e4",
            font=("Segoe UI", 9),
        ).grid(row=0, column=3, sticky="e")

    def build_metric_row(self, parent: tk.Widget, metrics: list[tuple[str, int, str]], accents: list[str] | None = None) -> None:
        row = tk.Frame(parent, bg=self.controller.theme["bg"])
        row.pack(fill=tk.X, pady=(0, 12))
        accents = accents or [
            self.controller.theme["blue"],
            self.controller.theme["green"],
            self.controller.theme["red"],
            self.controller.theme["yellow"],
        ]
        for idx in range(len(metrics)):
            row.grid_columnconfigure(idx, weight=1)
        for idx, (title, value, sub) in enumerate(metrics):
            value_var = tk.StringVar(value=f"{value:,}")
            self.controller._kpi_card(row, idx, title, value_var, sub, accents[idx % len(accents)])

    def build_placeholder(self, parent: tk.Widget, title: str, message: str) -> tk.Frame:
        body = self.controller._panel(parent, padx=16, pady=16)
        tk.Label(body, text=title, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(body, text=message, bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9), justify=tk.LEFT, wraplength=360).pack(anchor="w", pady=(8, 0))
        return body

    def build_simple_table(self, parent: tk.Widget, title: str, columns: list[tuple[str, str, int]], rows: list[tuple]) -> ttk.Treeview:
        card = self.controller._panel(parent, padx=12, pady=10)
        card.pack(fill=tk.BOTH, expand=True)
        tk.Label(card, text=title, bg=self.controller.theme["panel"], fg=self.controller.theme["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        body = tk.Frame(card, bg=self.controller.theme["panel"])
        body.pack(fill=tk.BOTH, expand=True)
        table = ttk.Treeview(body, columns=[col[0] for col in columns], show="headings", style="Ops.Treeview", height=8)
        for key, label, width in columns:
            table.heading(key, text=label)
            table.column(key, width=width, minwidth=width, stretch=True)
        for row in rows:
            table.insert("", tk.END, values=row)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        if not rows:
            tk.Label(body, text="표시할 데이터가 없습니다.", bg=self.controller.theme["panel"], fg=self.controller.theme["muted"], font=("Segoe UI", 9, "bold")).place(relx=0.5, rely=0.5, anchor="center")
        return table
