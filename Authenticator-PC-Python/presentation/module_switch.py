"""经典回退界面的验证码与密码本分段滑块控件。"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Literal

from presentation.dpi import DpiContext
from presentation.styles import HEADER_BG, TEXT_MUTED, UI_FONT

ModuleName = Literal["otp", "passwords"]

TRACK_FILL = "#F1F5F8"
TRACK_BORDER = "#D9E3EA"
OTP_FILL = "#DDF6E8"
OTP_BORDER = "#91D7B0"
OTP_TEXT = "#137A4B"
PASSWORD_FILL = "#DDF3FF"
PASSWORD_BORDER = "#8FD4F7"
PASSWORD_TEXT = "#0879B8"
FOCUS_BORDER = "#72A7E8"
MODULES: tuple[ModuleName, ...] = ("otp", "passwords")


class ModuleSegmentedSwitch(tk.Canvas):
    """单一控件内的三段模块开关，支持鼠标和键盘操作。"""

    def __init__(
        self,
        parent: tk.Misc,
        command: Callable[[ModuleName], None],
        dpi_context: DpiContext,
    ) -> None:
        self.command = command
        self.dpi_context = dpi_context
        self.active: ModuleName = "otp"
        self._hovered: ModuleName | None = None
        super().__init__(
            parent,
            background=HEADER_BG,
            borderwidth=0,
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
        )
        self.bind("<Button-1>", self._on_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", lambda _event: self._draw())
        self.bind("<FocusOut>", lambda _event: self._draw())
        self.bind("<Left>", lambda _event: self._move(-1))
        self.bind("<Right>", lambda _event: self._move(1))
        self.bind("<Home>", lambda _event: self._activate("otp"))
        self.bind("<End>", lambda _event: self._activate("passwords"))
        self.bind("<space>", self._toggle_from_keyboard)
        self.bind("<Return>", self._toggle_from_keyboard)
        self.invalidate_scale()

    def set_active(self, module: ModuleName) -> None:
        """由模块协调器同步选中段；不会反向触发切换命令。"""

        if module == self.active and self.find_all():
            return
        self.active = module
        self._draw()

    def invalidate_scale(self) -> None:
        """DPI 变化时重新计算固定逻辑尺寸并重绘。"""

        self._width = self.dpi_context.dp(178)
        self._height = self.dpi_context.dp(38)
        self.configure(width=self._width, height=self._height)
        self._draw()

    def _on_click(self, event: tk.Event[tk.Misc]) -> str:
        self.focus_set()
        index = min(len(MODULES) - 1, max(0, int(event.x / (self._width / len(MODULES)))))
        return self._activate(MODULES[index])

    def _on_motion(self, event: tk.Event[tk.Misc]) -> None:
        index = min(len(MODULES) - 1, max(0, int(event.x / (self._width / len(MODULES)))))
        hovered = MODULES[index]
        if hovered != self._hovered:
            self._hovered = hovered
            self._draw()

    def _on_leave(self, _event: tk.Event[tk.Misc]) -> None:
        if self._hovered is not None:
            self._hovered = None
            self._draw()

    def _toggle_from_keyboard(self, _event: tk.Event[tk.Misc]) -> str:
        return self._move(1)

    def _move(self, direction: int) -> str:
        index = MODULES.index(self.active)
        return self._activate(MODULES[(index + direction) % len(MODULES)])

    def _activate(self, module: ModuleName) -> str:
        if module != self.active:
            self.command(module)
        return "break"

    def _draw(self) -> None:
        self.delete("all")
        inset = self.dpi_context.dp(1)
        radius = self.dpi_context.dp(10)
        focus = self.focus_get() is self
        track_border = FOCUS_BORDER if focus else TRACK_BORDER
        self._rounded_rectangle(
            inset,
            inset,
            self._width - inset,
            self._height - inset,
            radius,
            fill=TRACK_FILL,
            outline=track_border,
            width=max(1, self.dpi_context.dp(1)),
            tags=("track",),
        )

        gap = self.dpi_context.dp(3)
        segment = self._width / len(MODULES)
        active_index = MODULES.index(self.active)
        selected_left = active_index * segment + gap
        selected_right = (active_index + 1) * segment - gap
        fills = {"otp": OTP_FILL, "passwords": PASSWORD_FILL}
        borders = {"otp": OTP_BORDER, "passwords": PASSWORD_BORDER}
        texts = {"otp": OTP_TEXT, "passwords": PASSWORD_TEXT}
        selected_fill = fills[self.active]
        selected_border = borders[self.active]
        self._rounded_rectangle(
            selected_left,
            gap,
            selected_right,
            self._height - gap,
            self.dpi_context.dp(8),
            fill=selected_fill,
            outline=selected_border,
            width=max(1, self.dpi_context.dp(1)),
            tags=("selection",),
        )

        colors = {module: texts[module] if self.active == module else TEXT_MUTED for module in MODULES}
        if self._hovered is not None and self.active != self._hovered:
            colors[self._hovered] = "#365A67"
        font = (UI_FONT, 9, "bold")
        labels = {"otp": "验证码", "passwords": "密码本"}
        for index, module in enumerate(MODULES):
            self.create_text(
                index * segment + segment / 2,
                self._height / 2,
                text=labels[module],
                fill=colors[module],
                font=font,
            )

    def _rounded_rectangle(
        self,
        left: float,
        top: float,
        right: float,
        bottom: float,
        radius: float,
        *,
        fill: str,
        outline: str,
        width: int,
        tags: tuple[str, ...],
    ) -> int:
        points = (
            left + radius, top,
            right - radius, top,
            right, top,
            right, top + radius,
            right, bottom - radius,
            right, bottom,
            right - radius, bottom,
            left + radius, bottom,
            left, bottom,
            left, bottom - radius,
            left, top + radius,
            left, top,
        )
        return self.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=outline,
            width=width,
            tags=tags,
        )
