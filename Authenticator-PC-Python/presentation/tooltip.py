"""Small accessible hover tooltip for compact icon buttons."""

from __future__ import annotations

import tkinter as tk

from presentation.styles import TEXT_PRIMARY, UI_FONT


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event: tk.Event[tk.Widget]) -> None:
        if self.window is not None or not self.text:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.window.geometry(f"+{x}+{y}")
        tk.Label(
            self.window,
            text=self.text,
            background="#FFFFFF",
            foreground=TEXT_PRIMARY,
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            font=(UI_FONT, 8),
        ).pack()

    def _hide(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None
