"""Reusable Tkinter dashboard components."""

from __future__ import annotations

import tkinter as tk


class ColorButton(tk.Frame):
    """Tk button replacement whose colors render consistently on macOS."""

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command=None,
        *,
        bg: str,
        fg: str = "#ffffff",
        activebackground: str | None = None,
        disabledbackground: str = "#26364c",
        anchor: str = "center",
        justify: str = tk.CENTER,
        padx: int = 10,
        pady: int = 7,
        font=None,
    ) -> None:
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.normal_bg = bg
        self.normal_fg = fg
        self.active_bg = activebackground or bg
        self.disabled_bg = disabledbackground
        self.disabled_fg = "#7f93aa"
        self.state = tk.NORMAL
        self.label = tk.Label(
            self,
            text=text,
            bg=bg,
            fg=fg,
            anchor=anchor,
            justify=justify,
            padx=padx,
            pady=pady,
            font=font or ("Segoe UI", 10),
            cursor="hand2",
        )
        self.label.pack(fill=tk.BOTH, expand=True)
        for widget in (self, self.label):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _set_colors(self, bg: str, fg: str) -> None:
        tk.Frame.configure(self, bg=bg)
        self.label.configure(bg=bg, fg=fg)

    def _on_click(self, _event=None) -> str:
        if self.state == tk.DISABLED:
            return "break"
        if self.command:
            self.command()
        return "break"

    def _on_enter(self, _event=None) -> None:
        if self.state != tk.DISABLED:
            self._set_colors(self.active_bg, self.normal_fg)

    def _on_leave(self, _event=None) -> None:
        if self.state != tk.DISABLED:
            self._set_colors(self.normal_bg, self.normal_fg)

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        text = kwargs.pop("text", None)
        state = kwargs.pop("state", None)
        command = kwargs.pop("command", None)
        bg = kwargs.pop("bg", None)
        fg = kwargs.pop("fg", None)
        activebackground = kwargs.pop("activebackground", None)
        if text is not None:
            self.label.configure(text=text)
        if command is not None:
            self.command = command
        if bg is not None:
            self.normal_bg = bg
        if fg is not None:
            self.normal_fg = fg
        if activebackground is not None:
            self.active_bg = activebackground
        if state is not None:
            self.state = state
        target_bg = self.disabled_bg if self.state == tk.DISABLED else self.normal_bg
        target_fg = self.disabled_fg if self.state == tk.DISABLED else self.normal_fg
        self._set_colors(target_bg, target_fg)
        if kwargs:
            tk.Frame.configure(self, cnf, **kwargs)

    config = configure

