"""Dashboard statistic cards shared by OTP and password modules."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

from PIL import ImageTk

from presentation.dpi import dpi_context_for
from presentation.icon_registry import IconRegistry
from presentation.scheduling import TrailingDebouncer
from presentation.styles import TEXT_MUTED, TEXT_PRIMARY, UI_FONT, WINDOW_BG
from presentation.view_models import OtpDashboardStats, PasswordDashboardStats


@dataclass(frozen=True)
class CardContent:
    icon: str
    value: str
    label: str
    detail: str


CARD_TONES = (
    ("#F4F7FF", "#C9D7FF", "#2563EB"),
    ("#F1FAF5", "#CBE9D6", "#15803D"),
    ("#FFF8F1", "#F2D8BE", "#EA580C"),
    ("#F7F5FF", "#DCD3FF", "#6D4DF2"),
)


class StatCard(tk.Canvas):
    def __init__(self, parent: tk.Misc, icons: IconRegistry, tone_index: int) -> None:
        self.dpi_context = dpi_context_for(parent)
        super().__init__(
            parent,
            width=self.dpi_context.dp(120),
            height=self.dpi_context.dp(88),
            background=WINDOW_BG,
            highlightthickness=0,
            borderwidth=0,
        )
        self.icons = icons
        self.surface, self.border, self.accent = CARD_TONES[tone_index]
        self.content = CardContent("circle-check", "0", "", "")
        self._icon_image: ImageTk.PhotoImage | None = None
        self._items: dict[str, int] = {}
        self._layout_debouncer = TrailingDebouncer(self, 240, self._layout)
        self.bind("<Configure>", self._schedule_layout)
        self.after_idle(self._layout)

    def set_content(self, content: CardContent) -> None:
        if content == self.content and self._items:
            return
        self.content = content
        if self._items:
            self.itemconfigure(self._items["value"], text=content.value)
            self.itemconfigure(self._items["label"], text=content.label)
            self.itemconfigure(self._items["detail"], text=content.detail)
            self._icon_image = self.icons.image(content.icon, 30, self.accent)
            self.itemconfigure(self._items["icon"], image=self._icon_image)
        else:
            self.after_idle(self._layout)

    @staticmethod
    def _rounded_points(x1: int, y1: int, x2: int, y2: int, radius: int) -> tuple[int, ...]:
        return (
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        )

    def _schedule_layout(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        self._layout_debouncer.trigger()

    def _layout(self) -> None:
        if not self.winfo_exists():
            return
        width = max(self.dpi_context.dp(120), self.winfo_width())
        height = max(self.dpi_context.dp(70), self.winfo_height())
        midpoint = height // 2
        points = self._rounded_points(1, 1, width - 2, height - 2, self.dpi_context.dp(9))
        icon_bounds = (
            self.dpi_context.dp(14), midpoint - self.dpi_context.dp(20),
            self.dpi_context.dp(54), midpoint + self.dpi_context.dp(20),
        )
        text_x = self.dpi_context.dp(66)
        if not self._items:
            self._items["surface"] = self.create_polygon(
                points, smooth=True, splinesteps=16, fill=self.surface, outline=self.border
            )
            self._items["halo"] = self.create_oval(*icon_bounds, fill="#FFFFFF", outline="")
            self._icon_image = self.icons.image(self.content.icon, 30, self.accent)
            self._items["icon"] = self.create_image(self.dpi_context.dp(34), midpoint, image=self._icon_image)
            self._items["value"] = self.create_text(
                text_x, self.dpi_context.dp(25), text=self.content.value, anchor="w",
                fill=TEXT_PRIMARY, font=(UI_FONT, 17, "bold")
            )
            self._items["label"] = self.create_text(
                text_x, self.dpi_context.dp(49), text=self.content.label, anchor="w",
                fill=TEXT_PRIMARY, font=(UI_FONT, 9)
            )
            self._items["detail"] = self.create_text(
                text_x, self.dpi_context.dp(68), text=self.content.detail, anchor="w",
                fill=TEXT_MUTED, font=(UI_FONT, 8)
            )
            return
        self.coords(self._items["surface"], *points)
        self.coords(self._items["halo"], *icon_bounds)
        self.coords(self._items["icon"], self.dpi_context.dp(34), midpoint)
        for key, logical_y in (("value", 25), ("label", 49), ("detail", 68)):
            self.coords(self._items[key], text_x, self.dpi_context.dp(logical_y))

    def invalidate_scale(self) -> None:
        self._icon_image = self.icons.image(self.content.icon, 30, self.accent)
        if self._items:
            self.itemconfigure(self._items["icon"], image=self._icon_image)
        self._schedule_layout()

    def destroy(self) -> None:
        self._layout_debouncer.cancel()
        super().destroy()


class DashboardStatsView(tk.Frame):
    def __init__(self, parent: tk.Misc, icons: IconRegistry) -> None:
        super().__init__(parent, background=WINDOW_BG)
        self.cards = [StatCard(self, icons, index) for index in range(4)]
        for index, card in enumerate(self.cards):
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 0 if index == 3 else 5))
            self.columnconfigure(index, weight=1, uniform="stats")
        self.rowconfigure(0, weight=1)

    def set_otp(self, stats: OtpDashboardStats) -> None:
        values = (
            CardContent("users", "--" if stats.locked else str(stats.total), "总账号数", "当前保险库"),
            CardContent("shield-check", "--" if stats.locked else str(stats.valid), "正常", "验证码可用"),
            CardContent("clock-3", "--" if stats.locked else str(stats.expiring), "即将刷新", "10 秒内刷新"),
            CardContent("refresh-cw", stats.mode_title, "验证码类型", stats.mode_detail),
        )
        for card, content in zip(self.cards, values, strict=True):
            card.set_content(content)

    def set_passwords(self, stats: PasswordDashboardStats) -> None:
        values = (
            CardContent("key-round", "--" if stats.locked else str(stats.total), "密码记录", "当前保险库"),
            CardContent("star", "--" if stats.locked else str(stats.pinned), "已置顶", "快速访问"),
            CardContent("link", "--" if stats.locked else str(stats.with_url), "包含网址", "可直接打开"),
            CardContent("folders", "--" if stats.locked else str(stats.custom_groups), "自定义分组", "独立于验证码"),
        )
        for card, content in zip(self.cards, values, strict=True):
            card.set_content(content)

    def invalidate_scale(self) -> None:
        for card in self.cards:
            card.invalidate_scale()
