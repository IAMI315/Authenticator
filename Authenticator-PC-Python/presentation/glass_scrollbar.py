"""DPI-aware, arrowless Canvas scrollbar for the light glass UI."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any

from presentation.dpi import dpi_context_for
from presentation.styles import GLASS_SURFACE

SCROLL_TRACK = "#EDF4FC"
SCROLL_THUMB = "#A9C4E8"
SCROLL_THUMB_HOVER = "#86ACDD"
SCROLL_THUMB_ACTIVE = "#6496D6"


class GlassScrollbar(tk.Canvas):
    """A quiet iOS-style scrollbar with a pill thumb and no arrow buttons."""

    def __init__(
        self,
        parent: tk.Misc,
        command: Callable[..., Any],
        *,
        width: int = 11,
        background: str = GLASS_SURFACE,
    ) -> None:
        self.dpi_context = dpi_context_for(parent)
        self.logical_width = width
        super().__init__(
            parent,
            width=self.dpi_context.dp(width),
            height=self.dpi_context.dp(40),
            background=background,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
            takefocus=False,
        )
        self.command = command
        self._first = 0.0
        self._last = 1.0
        self._hovered = False
        self._dragging = False
        self._drag_offset = 0.0
        self._thumb_outer_top = 0.0
        self._thumb_outer_bottom = 0.0
        self._track_top = 0.0
        self._track_bottom = 0.0
        self._track_item = self.create_line(0, 0, 0, 0, capstyle=tk.ROUND)
        self._thumb_item = self.create_line(0, 0, 0, 0, capstyle=tk.ROUND)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.after_idle(self._redraw)

    def set(self, first: float | str, last: float | str) -> None:
        next_first = max(0.0, min(1.0, float(first)))
        next_last = max(next_first, min(1.0, float(last)))
        if abs(next_first - self._first) < 0.0001 and abs(next_last - self._last) < 0.0001:
            return
        self._first = next_first
        self._last = next_last
        self._redraw()

    def invalidate_scale(self) -> None:
        self.configure(width=self.dpi_context.dp(self.logical_width))
        self._redraw()

    def _on_configure(self, _event: tk.Event[tk.Canvas]) -> None:
        self._redraw()

    def _redraw(self) -> None:
        if not self.winfo_exists():
            return
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        center_x = width / 2
        margin = self.dpi_context.dp(5)
        track_width = self.dpi_context.dp(3)
        thumb_width = self.dpi_context.dp(6)
        self._track_top = margin + track_width / 2
        self._track_bottom = max(self._track_top + 1, height - margin - track_width / 2)
        track_length = self._track_bottom - self._track_top
        viewport = max(0.0, min(1.0, self._last - self._first))
        visible = viewport < 0.999 and track_length > 1
        state = "normal" if visible else "hidden"
        self.itemconfigure(
            self._track_item,
            state=state,
            fill=SCROLL_TRACK,
            width=track_width,
        )
        self.coords(self._track_item, center_x, self._track_top, center_x, self._track_bottom)
        if not visible:
            self.itemconfigure(self._thumb_item, state="hidden")
            return

        thumb_length = min(track_length, max(float(self.dpi_context.dp(34)), track_length * viewport))
        travel = max(0.0, track_length - thumb_length)
        max_first = max(0.0001, 1.0 - viewport)
        outer_top = self._track_top + travel * min(1.0, self._first / max_first)
        outer_bottom = outer_top + thumb_length
        self._thumb_outer_top = outer_top
        self._thumb_outer_bottom = outer_bottom
        line_top = outer_top + thumb_width / 2
        line_bottom = max(line_top, outer_bottom - thumb_width / 2)
        color = SCROLL_THUMB_ACTIVE if self._dragging else SCROLL_THUMB_HOVER if self._hovered else SCROLL_THUMB
        self.itemconfigure(self._thumb_item, state="normal", fill=color, width=thumb_width)
        self.coords(self._thumb_item, center_x, line_top, center_x, line_bottom)

    def _on_enter(self, _event: tk.Event[tk.Canvas]) -> None:
        self._hovered = True
        self._redraw()

    def _on_leave(self, _event: tk.Event[tk.Canvas]) -> None:
        self._hovered = False
        if not self._dragging:
            self._redraw()

    def _on_press(self, event: tk.Event[tk.Canvas]) -> str:
        if self._thumb_outer_top <= event.y <= self._thumb_outer_bottom:
            self._dragging = True
            self._drag_offset = event.y - self._thumb_outer_top
            self._redraw()
            return "break"
        direction = -1 if event.y < self._thumb_outer_top else 1
        self.command("scroll", direction, "pages")
        return "break"

    def _on_drag(self, event: tk.Event[tk.Canvas]) -> str:
        if not self._dragging:
            return "break"
        viewport = max(0.0, min(1.0, self._last - self._first))
        thumb_length = self._thumb_outer_bottom - self._thumb_outer_top
        travel = max(1.0, (self._track_bottom - self._track_top) - thumb_length)
        outer_top = max(self._track_top, min(self._track_top + travel, event.y - self._drag_offset))
        fraction = ((outer_top - self._track_top) / travel) * max(0.0, 1.0 - viewport)
        self.command("moveto", fraction)
        return "break"

    def _on_release(self, _event: tk.Event[tk.Canvas]) -> str:
        self._dragging = False
        self._redraw()
        return "break"

    def _on_mousewheel(self, event: tk.Event[tk.Canvas]) -> str:
        self.command("scroll", -1 * int(event.delta / 120), "units")
        return "break"
