"""Responsive mixed navigation sidebar for accounts and password records."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from functools import partial

from PIL import ImageTk

from presentation.glass_scrollbar import GlassScrollbar
from presentation.icon_registry import IconRegistry
from presentation.styles import (
    ACCENT,
    GLASS_BORDER,
    GLASS_SURFACE,
    GLASS_SURFACE_MUTED,
    SELECTION,
    TEXT_MUTED,
    TEXT_PRIMARY,
    UI_FONT,
)
from presentation.view_models import NavigationItem, NavigationScope


class NavigationSidebar(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        icons: IconRegistry,
        query_var: tk.StringVar,
        on_select: Callable[[NavigationScope], None],
        on_toggle: Callable[[], None],
    ) -> None:
        super().__init__(parent, background=GLASS_SURFACE, highlightthickness=1, highlightbackground=GLASS_BORDER)
        self.icons = icons
        self.query_var = query_var
        self.on_select = on_select
        self.on_toggle = on_toggle
        self.items: list[NavigationItem] = []
        self.active_id = "all"
        self.collapsed = False
        self._images: list[ImageTk.PhotoImage] = []
        self._static_images: list[ImageTk.PhotoImage] = []
        self._buttons: dict[str, tk.Frame] = {}
        self._item_widgets: dict[str, tuple[tk.Label, tk.Label, tk.Label]] = {}
        self._item_images: dict[str, ImageTk.PhotoImage] = {}
        self._section_labels: list[tk.Label] = []
        self._items_signature: tuple[tuple[str, str, int, str, str], ...] = ()
        self._scrollregion_after_id: str | None = None
        self._last_canvas_width = 0
        self.security_var = tk.StringVar(value="本地保险库")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = tk.Frame(self, background=GLASS_SURFACE)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 8))
        top.columnconfigure(0, weight=1)
        self.search_entry = tk.Entry(
            top,
            textvariable=self.query_var,
            relief="flat",
            background=GLASS_SURFACE_MUTED,
            foreground=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            font=(UI_FONT, 9),
            highlightthickness=1,
            highlightbackground="#D9E2EE",
            highlightcolor=ACCENT,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", ipady=7)
        self.toggle_button = tk.Button(
            top,
            command=self.on_toggle,
            relief="flat",
            borderwidth=0,
            background=GLASS_SURFACE,
            activebackground=GLASS_SURFACE_MUTED,
            cursor="hand2",
        )
        self.toggle_button.grid(row=0, column=1, padx=(6, 0))

        self.list_canvas = tk.Canvas(
            self,
            background=GLASS_SURFACE,
            highlightthickness=0,
            borderwidth=0,
            yscrollincrement=24,
        )
        self.list_canvas.grid(row=1, column=0, sticky="nsew")
        self.list_scrollbar = GlassScrollbar(self, command=self.list_canvas.yview, width=10)
        self.list_canvas.configure(yscrollcommand=self._set_scrollbar)
        self.list_frame = tk.Frame(self.list_canvas, background=GLASS_SURFACE)
        self.list_window = self.list_canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", self._sync_scrollregion)
        self.list_canvas.bind("<Configure>", self._sync_list_width)
        self.list_canvas.bind("<MouseWheel>", self._on_mousewheel)

        self.security_panel = tk.Frame(self, background="#F3F7FF", highlightthickness=1, highlightbackground="#D6E2FF")
        self.security_panel.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        self.security_icon = tk.Label(self.security_panel, background="#F3F7FF")
        self.security_icon.grid(row=0, column=0, rowspan=2, padx=(9, 7), pady=9)
        tk.Label(
            self.security_panel,
            text="保险库状态",
            background="#F3F7FF",
            foreground=TEXT_PRIMARY,
            font=(UI_FONT, 9, "bold"),
        ).grid(row=0, column=1, sticky="w", pady=(8, 0))
        self.security_label = tk.Label(
            self.security_panel,
            textvariable=self.security_var,
            background="#F3F7FF",
            foreground=TEXT_MUTED,
            font=(UI_FONT, 8),
        )
        self.security_label.grid(row=1, column=1, sticky="w", pady=(0, 8))
        self._refresh_static_icons()

    def set_query_variable(self, variable: tk.StringVar) -> None:
        self.query_var = variable
        self.search_entry.configure(textvariable=variable)

    def set_items(self, items: Sequence[NavigationItem], active_scope: NavigationScope) -> None:
        self.items = list(items)
        next_active = next((item.id for item in self.items if item.scope == active_scope), "all")
        signature = tuple(
            (item.id, item.label, item.count, item.icon_key, item.section)
            for item in self.items
        )
        if signature != self._items_signature or not self._buttons:
            self.active_id = next_active
            self._items_signature = signature
            self._rebuild_items()
            return
        previous_active = self.active_id
        self.active_id = next_active
        if previous_active != next_active:
            self._restyle_item(previous_active)
            self._restyle_item(next_active)

    def set_security(self, value: str) -> None:
        self.security_var.set(value.replace("本地保险库：", ""))

    def set_collapsed(self, collapsed: bool) -> None:
        if self.collapsed == collapsed and self._buttons:
            return
        self.collapsed = collapsed
        if collapsed:
            self.search_entry.grid_remove()
            self.toggle_button.grid(row=0, column=0)
            self.security_panel.grid_remove()
        else:
            self.search_entry.grid()
            self.toggle_button.grid(row=0, column=1, padx=(6, 0))
            self.security_panel.grid()
        self._refresh_static_icons()
        self._apply_collapsed_state()
        self._schedule_scrollregion_sync()

    def _refresh_static_icons(self) -> None:
        direction = "chevron-right" if self.collapsed else "chevron-left"
        toggle = self.icons.image(direction, 18)
        shield = self.icons.image("shield-check", 24, "#2563EB")
        self._static_images = [toggle, shield]
        self.toggle_button.configure(image=toggle)
        self.security_icon.configure(image=shield)

    def _rebuild_items(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._buttons.clear()
        self._item_widgets.clear()
        self._item_images.clear()
        self._images.clear()
        self._section_labels.clear()
        last_section = ""
        row_index = 0
        section_labels = {"groups": "分组", "providers": "服务商"}
        for item in self.items:
            if item.section != last_section and item.section in section_labels:
                section_label = tk.Label(
                    self.list_frame,
                    text=section_labels[item.section],
                    background=GLASS_SURFACE,
                    foreground=TEXT_MUTED,
                    font=(UI_FONT, 8),
                    anchor="w",
                )
                section_label.grid(row=row_index, column=0, sticky="ew", padx=13, pady=(9, 3))
                section_label.bind("<MouseWheel>", self._on_mousewheel)
                self._section_labels.append(section_label)
                row_index += 1
            last_section = item.section
            selected = item.id == self.active_id
            background = SELECTION if selected else GLASS_SURFACE
            item_frame = tk.Frame(self.list_frame, background=background, cursor="hand2")
            item_frame.grid(row=row_index, column=0, sticky="ew", padx=7, pady=1)
            item_frame.columnconfigure(1, weight=1)
            image = self.icons.image(item.icon_key, 20, ACCENT if selected else None)
            self._images.append(image)
            self._item_images[item.id] = image
            icon = tk.Label(item_frame, image=image, background=background, cursor="hand2")
            icon.grid(row=0, column=0, padx=10, pady=8)
            widgets: list[tk.Widget] = [item_frame, icon]
            label = tk.Label(
                item_frame,
                text=item.label,
                background=background,
                foreground=ACCENT if selected else TEXT_PRIMARY,
                font=(UI_FONT, 9, "bold" if selected else "normal"),
                anchor="w",
                cursor="hand2",
            )
            label.grid(row=0, column=1, sticky="ew")
            count = tk.Label(
                item_frame,
                text=str(item.count),
                background="#D9E9FF" if selected else GLASS_SURFACE_MUTED,
                foreground=ACCENT if selected else TEXT_MUTED,
                font=(UI_FONT, 8, "bold"),
                padx=6,
                pady=2,
                cursor="hand2",
            )
            count.grid(row=0, column=2, padx=(4, 8))
            widgets.extend((label, count))
            for widget in widgets:
                widget.bind("<Button-1>", partial(self._choose_event, item.scope))
                widget.bind("<MouseWheel>", self._on_mousewheel)
            self._buttons[item.id] = item_frame
            self._item_widgets[item.id] = (icon, label, count)
            row_index += 1
        self.list_frame.columnconfigure(0, weight=1)
        self._apply_collapsed_state()
        self._schedule_scrollregion_sync()

    def _apply_collapsed_state(self) -> None:
        """Change sidebar density without recreating every navigation widget."""

        for section_label in self._section_labels:
            if self.collapsed:
                section_label.grid_remove()
            else:
                section_label.grid()
        for icon, label, count in self._item_widgets.values():
            icon.grid_configure(padx=11 if self.collapsed else 10)
            if self.collapsed:
                label.grid_remove()
                count.grid_remove()
            else:
                label.grid()
                count.grid()
        if self.collapsed:
            self.list_scrollbar.grid_remove()

    def _restyle_item(self, item_id: str) -> None:
        frame = self._buttons.get(item_id)
        widgets = self._item_widgets.get(item_id)
        item = next((candidate for candidate in self.items if candidate.id == item_id), None)
        if frame is None or widgets is None or item is None:
            return
        selected = item.id == self.active_id
        background = SELECTION if selected else GLASS_SURFACE
        icon, label, count = widgets
        frame.configure(background=background)
        icon.configure(background=background)
        image = self.icons.image(item.icon_key, 20, ACCENT if selected else None)
        self._item_images[item.id] = image
        icon.configure(image=image)
        if label is not None:
            label.configure(
                background=background,
                foreground=ACCENT if selected else TEXT_PRIMARY,
                font=(UI_FONT, 9, "bold" if selected else "normal"),
            )
        if count is not None:
            count.configure(
                background="#D9E9FF" if selected else GLASS_SURFACE_MUTED,
                foreground=ACCENT if selected else TEXT_MUTED,
            )

    def invalidate_scale(self) -> None:
        self._refresh_static_icons()
        self._rebuild_items()

    def _choose(self, scope: NavigationScope) -> None:
        self.on_select(scope)

    def _choose_event(self, scope: NavigationScope, _event: tk.Event[tk.Widget]) -> None:
        self._choose(scope)

    def _sync_scrollregion(self, _event: tk.Event[tk.Misc]) -> None:
        self._schedule_scrollregion_sync()

    def _schedule_scrollregion_sync(self) -> None:
        if self._scrollregion_after_id is not None:
            return
        self._scrollregion_after_id = self.after_idle(self._apply_scrollregion)

    def _apply_scrollregion(self) -> None:
        self._scrollregion_after_id = None
        bounds = self.list_canvas.bbox("all")
        self.list_canvas.configure(scrollregion=bounds or (0, 0, 0, 0))
        self._update_scrollbar_visibility(bounds)

    def _sync_list_width(self, event: tk.Event[tk.Canvas]) -> None:
        if event.width == self._last_canvas_width:
            return
        self._last_canvas_width = event.width
        self.list_canvas.itemconfigure(self.list_window, width=event.width)
        self._schedule_scrollregion_sync()

    def _set_scrollbar(self, first: float, last: float) -> None:
        self.list_scrollbar.set(first, last)
        self._update_scrollbar_visibility(self.list_canvas.bbox("all"))

    def _update_scrollbar_visibility(self, bounds: tuple[int, int, int, int] | None) -> None:
        content_height = 0 if bounds is None else bounds[3] - bounds[1]
        overflow = content_height > max(self.list_canvas.winfo_height(), 1) + 1
        if overflow and not self.collapsed:
            self.list_scrollbar.grid(row=1, column=1, sticky="ns")
        else:
            self.list_scrollbar.grid_remove()

    def _on_mousewheel(self, event: tk.Event[tk.Widget]) -> str:
        self.list_canvas.yview_scroll(-1 * int(event.delta / 120), "units")
        return "break"
