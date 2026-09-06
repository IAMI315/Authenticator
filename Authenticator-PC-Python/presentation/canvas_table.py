"""Lightweight Canvas data table shared by OTP and password workspaces."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from math import cos, radians, sin
from typing import Any, Literal, Protocol

from PIL import Image, ImageDraw, ImageTk

from presentation.dpi import DpiContext, dpi_context_for
from presentation.glass_scrollbar import GlassScrollbar
from presentation.scheduling import TrailingDebouncer
from presentation.styles import (
    ACCENT,
    GLASS_BORDER,
    GLASS_SURFACE,
    GLASS_SURFACE_MUTED,
    INVALID_TEXT,
    PINNED_SURFACE,
    SELECTION,
    TEXT_MUTED,
    TEXT_PRIMARY,
    UI_FONT,
)

Align = Literal["w", "center", "e"]
CanvasAnchor = Literal["w", "center", "e"]
RowAction = Literal["toggle_favorite", "toggle_pin", "copy_primary", "more", "activate"]
TableSortDirection = Literal["ascending", "descending"]


class IconProvider(Protocol):
    def image(self, key: str, size: int = 20, tint: str | None = None) -> Any: ...


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    label: str
    width: int
    min_width: int = 42
    weight: int = 0
    align: Align = "w"
    sortable: bool = False
    initial_sort_direction: TableSortDirection = "ascending"


@dataclass(frozen=True)
class TableRow:
    id: str
    values: Mapping[str, str]
    favorite: bool = False
    pinned: bool = False
    invalid: bool = False
    remaining_seconds: int | None = None
    period: int = 30
    icon_key: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


class CanvasDataTable(tk.Frame):
    """Canvas-based table with stable row items and Treeview-like selection methods."""

    def __init__(
        self,
        parent: tk.Misc,
        columns: Sequence[ColumnSpec],
        *,
        icons: IconProvider | None = None,
        primary_column: str,
        service_column: str,
        row_height: int = 52,
        on_selection: Callable[[], None] | None = None,
        on_action: Callable[[str, RowAction], None] | None = None,
        on_context: Callable[[str, int, int], None] | None = None,
        on_sort: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, background=GLASS_SURFACE, highlightthickness=1, highlightbackground=GLASS_BORDER)
        self.columns = tuple(columns)
        self.dpi_context: DpiContext = dpi_context_for(parent)
        self.icons = icons
        self.primary_column = primary_column
        self.service_column = service_column
        self._logical_row_height = row_height
        self.row_height = self.dpi_context.dp(row_height)
        self.on_selection = on_selection
        self.on_action = on_action
        self.on_context = on_context
        self.on_sort = on_sort
        self._sort_key = ""
        self._sort_direction: TableSortDirection = "ascending"
        self._rows: list[TableRow] = []
        self._row_by_id: dict[str, TableRow] = {}
        self._selected: set[str] = set()
        self._focused_id = ""
        self._anchor_id = ""
        self._hovered_id = ""
        self._column_bounds: list[tuple[ColumnSpec, int, int]] = []
        self._row_rects: dict[str, int] = {}
        self._checkboxes: dict[str, tuple[int, int]] = {}
        self._favorites: dict[str, int] = {}
        self._pins: dict[str, int] = {}
        self._cell_items: dict[tuple[str, str], int] = {}
        self._progress_items: dict[str, tuple[int, int]] = {}
        self._progress_images: dict[str, ImageTk.PhotoImage] = {}
        self._progress_image_cache: dict[tuple[int, int, str, str], ImageTk.PhotoImage] = {}
        self._images: dict[str, Any] = {}
        self._rendered_ids: set[str] = set()
        self._row_fills: dict[str, str] = {}
        self._layout_active = True
        self._resize_dirty = False
        self._visible_after_id: str | None = None
        self._empty_message = ""
        self._font = tkfont.Font(family=UI_FONT, size=10)
        self._bold_font = tkfont.Font(family=UI_FONT, size=10, weight="bold")
        self._small_font = tkfont.Font(family=UI_FONT, size=9)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.header = tk.Canvas(
            self,
            width=120,
            height=self.dpi_context.dp(42),
            background=GLASS_SURFACE_MUTED,
            highlightthickness=0,
            borderwidth=0,
        )
        self.header.grid(row=0, column=0, sticky="ew", columnspan=2)
        self.header.bind("<Button-1>", self._on_header_click)
        self.header.bind("<Motion>", self._on_header_motion)
        self.header.bind("<Leave>", lambda _event: self.header.configure(cursor=""))
        self.body = tk.Canvas(
            self,
            width=120,
            height=80,
            background=GLASS_SURFACE,
            highlightthickness=0,
            borderwidth=0,
            takefocus=True,
        )
        self.body.grid(row=1, column=0, sticky="nsew")
        self.scrollbar = GlassScrollbar(self, command=self._scroll_to, width=11)
        self.scrollbar.grid(row=1, column=1, sticky="ns")
        self.body.configure(yscrollcommand=self._on_yview)
        self.bind("<Configure>", self._on_resize, add="+")
        self.body.bind("<Button-1>", self._on_click)
        self.body.bind("<Double-1>", self._on_double_click)
        self.body.bind("<Button-3>", self._on_right_click)
        self.body.bind("<Motion>", self._on_motion)
        self.body.bind("<Leave>", lambda _event: self._set_hover(""))
        self.body.bind("<MouseWheel>", self._on_mousewheel)
        self.body.bind("<Control-a>", self._select_all_event)
        self.body.bind("<Up>", lambda event: self._move_focus(-1, bool(int(event.state) & 0x0001)))
        self.body.bind("<Down>", lambda event: self._move_focus(1, bool(int(event.state) & 0x0001)))
        self.body.bind("<Control-space>", self._toggle_focus_event)
        self._resize_debouncer = TrailingDebouncer(self, 240, self._finish_resize)

    def set_rows(self, rows: Sequence[TableRow], *, empty_message: str = "") -> None:
        selected = {row_id for row_id in self._selected if any(row.id == row_id for row in rows)}
        focused = self._focused_id if any(row.id == self._focused_id for row in rows) else ""
        self._rows = list(rows)
        self._row_by_id = {row.id: row for row in self._rows}
        self._selected = selected
        self._focused_id = focused
        self._empty_message = empty_message
        if self._layout_active:
            self._draw()
        else:
            self._resize_dirty = True

    def set_sort_state(self, key: str, direction: str) -> None:
        normalised_direction: TableSortDirection = (
            "descending" if direction == "descending" else "ascending"
        )
        if key == self._sort_key and normalised_direction == self._sort_direction:
            return
        self._sort_key = key
        self._sort_direction = normalised_direction
        if self._column_bounds:
            self._draw_header()

    def update_rows(self, rows: Sequence[TableRow]) -> bool:
        """Update existing Canvas items without rebuilding when row identity is stable."""

        if [row.id for row in rows] != [row.id for row in self._rows]:
            self.set_rows(rows, empty_message=self._empty_message)
            return False
        previous = self._row_by_id
        self._rows = list(rows)
        self._row_by_id = {row.id: row for row in self._rows}
        if not self._layout_active:
            self._resize_dirty = True
            return True
        bounds_by_key = {
            column.key: (column, start, end)
            for column, start, end in self._column_bounds
        }
        for row in self._rows:
            if row.id not in self._rendered_ids:
                continue
            old_row = previous.get(row.id)
            for column in self.columns:
                item = self._cell_items.get((row.id, column.key))
                old_value = str(old_row.values.get(column.key, "")) if old_row is not None else None
                new_value = str(row.values.get(column.key, ""))
                if item is not None and old_value != new_value:
                    bounds = bounds_by_key.get(column.key)
                    text = self._display_value(row, column.key)
                    if bounds is not None and column.key != "actions":
                        text = self._cell_text(row, *bounds)
                    self.body.itemconfigure(
                        item,
                        text=text,
                        fill=self._text_color(row, column.key),
                    )
            favorite_item = self._favorites.get(row.id)
            if favorite_item is not None and (old_row is None or old_row.favorite != row.favorite):
                image = self._marker_image("star", row.favorite, "#F59E0B")
                self._images[f"{row.id}:favorite"] = image
                self.body.itemconfigure(favorite_item, image=image)
            pin_item = self._pins.get(row.id)
            if pin_item is not None and (old_row is None or old_row.pinned != row.pinned):
                image = self._marker_image("pin", row.pinned, ACCENT)
                self._images[f"{row.id}:pin"] = image
                self.body.itemconfigure(pin_item, image=image)
            progress = self._progress_items.get(row.id)
            progress_changed = old_row is None or (
                old_row.remaining_seconds != row.remaining_seconds or old_row.period != row.period
            )
            if progress is not None and row.remaining_seconds is not None and progress_changed:
                color = "#F59E0B" if row.remaining_seconds <= 10 else ACCENT
                progress_image = self._progress_photo(
                    row.remaining_seconds,
                    row.period,
                    color,
                    self._row_fill(row.id, row),
                )
                self._progress_images[row.id] = progress_image
                self.body.itemconfigure(progress[0], image=progress_image)
                self.body.itemconfigure(progress[1], text=str(row.remaining_seconds), fill=color)
        return True

    def update_dynamic_rows(self, rows: Sequence[TableRow]) -> bool:
        """Update time-sensitive visible cells without rebuilding static row items."""

        return self.update_rows(rows)

    def _on_resize(self, _event: tk.Event[tk.Misc]) -> None:
        self._resize_dirty = True
        if self._layout_active:
            self._resize_debouncer.trigger()

    def _finish_resize(self) -> None:
        if not self._layout_active:
            return
        self._resize_dirty = False
        self._draw()

    def set_layout_active(self, active: bool) -> None:
        """Suspend hidden-table layout while keeping its row model current."""

        if self._layout_active == active:
            return
        self._layout_active = active
        if not active:
            self._resize_debouncer.cancel()
            return
        if self._resize_dirty:
            self._finish_resize()

    def _on_yview(self, first: float, last: float) -> None:
        self.scrollbar.set(first, last)
        self._schedule_visible_draw()

    def _scroll_to(self, *args: Any) -> None:
        self.body.yview(*args)
        self._schedule_visible_draw()

    def _schedule_visible_draw(self) -> None:
        if self._visible_after_id is None:
            self._visible_after_id = self.after_idle(self._draw_visible_rows)

    def _column_layout(self) -> list[tuple[ColumnSpec, int, int]]:
        available = max(1, self.winfo_width() - self.scrollbar.winfo_reqwidth() - 2)
        base = sum(self.dpi_context.dp(column.width) for column in self.columns)
        widths = [self.dpi_context.dp(column.width) for column in self.columns]
        if available > base:
            total_weight = sum(column.weight for column in self.columns)
            if total_weight:
                extra = available - base
                widths = [
                    width + int(extra * column.weight / total_weight)
                    for width, column in zip(widths, self.columns, strict=True)
                ]
        elif available < base:
            shortage = base - available
            minimums = [self.dpi_context.dp(column.min_width) for column in self.columns]
            shrinkable = sum(
                max(0, width - minimum)
                for width, minimum in zip(widths, minimums, strict=True)
            )
            if shrinkable:
                widths = [
                    max(minimum, width - int(shortage * max(0, width - minimum) / shrinkable))
                    for width, minimum in zip(widths, minimums, strict=True)
                ]
        bounds: list[tuple[ColumnSpec, int, int]] = []
        x = 0
        for column, width in zip(self.columns, widths, strict=True):
            bounds.append((column, x, x + width))
            x += width
        if bounds and x < available:
            column, start, end = bounds[-1]
            bounds[-1] = (column, start, end + available - x)
        return bounds

    def _draw(self) -> None:
        if not self.winfo_exists():
            return
        self._column_bounds = self._column_layout()
        self._draw_header()
        self._clear_body_items()
        width = self._column_bounds[-1][2] if self._column_bounds else max(1, self.winfo_width())
        if not self._rows:
            self.body.create_text(
                self.dpi_context.dp(22),
                self.dpi_context.dp(30),
                text=self._empty_message,
                anchor="nw",
                fill=TEXT_MUTED,
                font=self._font,
            )
            self.body.configure(scrollregion=(0, 0, width, max(1, self.body.winfo_height())))
            self._draw_header_checkbox()
            return
        self.body.configure(scrollregion=(0, 0, width, len(self._rows) * self.row_height))
        self._draw_visible_rows()

    def _draw_header(self) -> None:
        self.header.delete("all")
        header_midpoint = self.dpi_context.dp(21)
        header_height = self.dpi_context.dp(42)
        for column, start, end in self._column_bounds:
            if column.key != "select":
                anchor, x = self._text_anchor(column, start, end)
                suffix = ""
                if column.key == self._sort_key:
                    suffix = " ↑" if self._sort_direction == "ascending" else " ↓"
                self.header.create_text(
                    x,
                    header_midpoint,
                    text=f"{column.label}{suffix}",
                    anchor=anchor,
                    fill=ACCENT if column.key == self._sort_key else TEXT_MUTED,
                    font=self._small_font,
                )
            self.header.create_line(end, 0, end, header_height, fill="#EDF1F7")
        self._draw_header_checkbox()

    def _clear_body_items(self) -> None:
        self.body.delete("all")
        self._row_rects.clear()
        self._checkboxes.clear()
        self._favorites.clear()
        self._pins.clear()
        self._cell_items.clear()
        self._progress_items.clear()
        self._progress_images.clear()
        self._images.clear()
        self._rendered_ids.clear()
        self._row_fills.clear()

    def _visible_range(self) -> range:
        if not self._rows:
            return range(0)
        top = max(0, int(self.body.canvasy(0) // self.row_height) - 1)
        bottom_y = self.body.canvasy(max(1, self.body.winfo_height()))
        bottom = min(len(self._rows), int(bottom_y // self.row_height) + 2)
        return range(top, bottom)

    def _draw_visible_rows(self) -> None:
        self._visible_after_id = None
        if not self.winfo_exists() or not self._rows:
            return
        visible_range = self._visible_range()
        desired = {self._rows[index].id for index in visible_range}
        if desired == self._rendered_ids and self._row_rects:
            return
        width = self._column_bounds[-1][2] if self._column_bounds else max(1, self.winfo_width())
        self._clear_body_items()
        for index in visible_range:
            row = self._rows[index]
            self._draw_row(index, row, width)
            self._rendered_ids.add(row.id)
        self._render_selection()

    def _draw_row(self, index: int, row: TableRow, width: int) -> None:
        top = index * self.row_height
        bottom = top + self.row_height
        fill = PINNED_SURFACE if row.pinned else GLASS_SURFACE
        rect = self.body.create_rectangle(0, top, width, bottom, fill=fill, outline="")
        self.body.tag_lower(rect)
        self._row_rects[row.id] = rect
        self._row_fills[row.id] = fill
        self.body.create_line(0, bottom - 1, width, bottom - 1, fill="#E8EDF3")
        for column, start, end in self._column_bounds:
            center_y = top + self.row_height // 2
            if column.key == "select":
                self._checkboxes[row.id] = self._draw_checkbox(self.body, (start + end) // 2, center_y, row.id in self._selected)
                continue
            if column.key == "pin":
                marker_x = (start + end) // 2
                favorite_image = self._marker_image("star", row.favorite, "#F59E0B")
                pin_image = self._marker_image("pin", row.pinned, ACCENT)
                self._images[f"{row.id}:favorite"] = favorite_image
                self._images[f"{row.id}:pin"] = pin_image
                self._favorites[row.id] = self.body.create_image(
                    marker_x, center_y - self.dpi_context.dp(10), image=favorite_image
                )
                self._pins[row.id] = self.body.create_image(
                    marker_x, center_y + self.dpi_context.dp(10), image=pin_image
                )
                continue
            if column.key == "remaining" and row.remaining_seconds is not None:
                cx = (start + end) // 2
                color = "#F59E0B" if row.remaining_seconds <= 10 else ACCENT
                progress_image = self._progress_photo(row.remaining_seconds, row.period, color, fill)
                self._progress_images[row.id] = progress_image
                arc = self.body.create_image(cx, center_y, image=progress_image)
                text = self.body.create_text(cx, center_y, text=str(row.remaining_seconds), fill=color, font=(UI_FONT, 8, "bold"))
                self._progress_items[row.id] = (arc, text)
                continue
            if column.key == "actions":
                item = self.body.create_text((start + end) // 2, center_y, text="•••", fill=TEXT_MUTED, font=self._bold_font)
                self._cell_items[(row.id, column.key)] = item
                continue
            anchor, x = self._text_anchor(column, start, end)
            if column.key == self.service_column:
                icon_image = self.icons.image(row.icon_key, 22) if self.icons is not None else None
                if icon_image is not None:
                    self._images[f"{row.id}:{column.key}"] = icon_image
                    self.body.create_image(
                        start + self.dpi_context.dp(13), center_y, image=icon_image, anchor="w"
                    )
                    x = start + self.dpi_context.dp(43)
            value = self._cell_text(row, column, start, end)
            item = self.body.create_text(
                x,
                center_y,
                text=value,
                anchor=anchor,
                fill=self._text_color(row, column.key),
                font=self._bold_font if column.key == self.primary_column else self._font,
            )
            self._cell_items[(row.id, column.key)] = item

    def _cell_text(self, row: TableRow, column: ColumnSpec, start: int, end: int) -> str:
        """Format a cell inside its current column, including update-only redraws."""

        _anchor, x = self._text_anchor(column, start, end)
        if column.key == self.service_column and self.icons is not None:
            x = start + self.dpi_context.dp(43)
        if column.align == "center":
            available = end - start - self.dpi_context.dp(16)
        elif column.align == "e":
            available = x - start - self.dpi_context.dp(8)
        else:
            available = end - x - self.dpi_context.dp(8)
        return self._ellipsize(self._display_value(row, column.key), max(12, available))

    def _progress_photo(self, remaining: int, period: int, color: str, background: str) -> ImageTk.PhotoImage:
        size = self.dpi_context.dp(38)
        key = (remaining, period, color, f"{background}:{size}")
        cached = self._progress_image_cache.get(key)
        if cached is not None:
            return cached
        photo = ImageTk.PhotoImage(
            self._render_progress_bitmap(remaining, period, color, background=background, size=size),
            master=self,
        )
        if len(self._progress_image_cache) >= 128:
            self._progress_image_cache.pop(next(iter(self._progress_image_cache)))
        self._progress_image_cache[key] = photo
        return photo

    @staticmethod
    def _render_progress_bitmap(
        remaining: int,
        period: int,
        color: str,
        *,
        background: str = GLASS_SURFACE,
        size: int = 38,
        scale: int = 8,
    ) -> Image.Image:
        """Render an SVG-equivalent rounded ring with DPI-safe supersampling."""

        high_size = size * scale
        stroke = round(2.5 * scale)
        inset = (stroke + 2 * scale) // 2
        bounds = (inset, inset, high_size - inset - 1, high_size - inset - 1)
        # Precompositing avoids Tk's partial-alpha quantisation on Windows.
        bitmap = Image.new("RGB", (high_size, high_size), background)
        draw = ImageDraw.Draw(bitmap)
        draw.ellipse(bounds, outline="#E2E8F0", width=stroke)
        fraction = max(0.0, min(float(remaining), float(max(1, period))) / max(1, period))
        if fraction > 0:
            start_angle = -90.0
            end_angle = start_angle + 359.5 * fraction
            draw.arc(bounds, start=start_angle, end=end_angle, fill=color, width=stroke)
            if fraction < 0.999:
                center = high_size / 2
                radius = (bounds[2] - bounds[0]) / 2
                cap_radius = stroke / 2
                for angle in (start_angle, end_angle):
                    angle_radians = radians(angle)
                    x = center + radius * cos(angle_radians)
                    y = center + radius * sin(angle_radians)
                    draw.ellipse(
                        (x - cap_radius, y - cap_radius, x + cap_radius, y + cap_radius),
                        fill=color,
                    )
        return bitmap.resize((size, size), Image.Resampling.LANCZOS)

    def _draw_checkbox(self, canvas: tk.Canvas, x: int, y: int, selected: bool) -> tuple[int, int]:
        radius = self.dpi_context.dp(7)
        box = canvas.create_rectangle(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=ACCENT if selected else GLASS_SURFACE,
            outline=ACCENT if selected else "#CBD5E1",
            width=1,
        )
        mark = canvas.create_text(x, y - 1, text="✓" if selected else "", fill="#FFFFFF", font=(UI_FONT, 8, "bold"))
        return box, mark

    def _text_anchor(self, column: ColumnSpec, start: int, end: int) -> tuple[CanvasAnchor, int]:
        if column.align == "center":
            return "center", (start + end) // 2
        if column.align == "e":
            return "e", end - self.dpi_context.dp(10)
        return "w", start + self.dpi_context.dp(10)

    def _ellipsize(self, value: str, width: int) -> str:
        if self._font.measure(value) <= width:
            return value
        suffix = "…"
        candidate = value
        while candidate and self._font.measure(candidate + suffix) > width:
            candidate = candidate[:-1]
        return candidate + suffix

    def _display_value(self, row: TableRow, key: str) -> str:
        return str(row.values.get(key, ""))

    def _marker_image(self, key: str, active: bool, active_color: str) -> Any:
        if self.icons is None:
            return None
        return self.icons.image(key, 13, active_color if active else "#A7B3C4")

    def _text_color(self, row: TableRow, key: str) -> str:
        if row.invalid and key == self.primary_column:
            return INVALID_TEXT
        if key == self.primary_column:
            return ACCENT
        if key == "actions":
            return TEXT_MUTED
        return TEXT_PRIMARY

    def _row_at(self, y: int) -> str:
        index = int(self.body.canvasy(y) // self.row_height)
        return self._rows[index].id if 0 <= index < len(self._rows) else ""

    def _column_at(self, x: int) -> str:
        canvas_x = int(self.body.canvasx(x))
        return next((column.key for column, start, end in self._column_bounds if start <= canvas_x < end), "")

    def identify_row(self, y: int) -> str:
        return self._row_at(y)

    def identify_column(self, x: int) -> str:
        return self._column_at(x)

    def _on_click(self, event: tk.Event[tk.Canvas]) -> str:
        self.body.focus_set()
        row_id = self._row_at(event.y)
        if not row_id:
            return "break"
        column = self._column_at(event.x)
        if column == "select":
            self._select_row(row_id, control=True, shift=False)
            return "break"
        if column in {"pin", self.primary_column, "actions"}:
            if column != "pin" and row_id not in self._selected:
                self.selection_set(row_id)
            if column == "pin":
                row_top = (int(self.body.canvasy(event.y)) // self.row_height) * self.row_height
                action: RowAction = (
                    "toggle_favorite"
                    if int(self.body.canvasy(event.y)) - row_top < self.row_height // 2
                    else "toggle_pin"
                )
            elif column == self.primary_column:
                action = "copy_primary"
            else:
                action = "more"
            if self.on_action is not None:
                self.on_action(row_id, action)
            return "break"
        control = bool(int(event.state) & 0x0004)
        shift = bool(int(event.state) & 0x0001)
        self._select_row(row_id, control=control, shift=shift)
        return "break"

    def _on_double_click(self, event: tk.Event[tk.Canvas]) -> str:
        row_id = self._row_at(event.y)
        if row_id:
            self.selection_set(row_id)
            if self.on_action is not None:
                self.on_action(row_id, "activate")
        return "break"

    def _on_header_click(self, event: tk.Event[tk.Canvas]) -> str:
        column_key = self._column_at(event.x)
        if column_key == "select":
            if self._rows and len(self._selected) == len(self._rows):
                self.selection_set(())
            else:
                self.selection_set([row.id for row in self._rows])
        else:
            column = next((item for item in self.columns if item.key == column_key), None)
            if column is not None and column.sortable and self.on_sort is not None:
                self.on_sort(column.key)
        return "break"

    def _on_header_motion(self, event: tk.Event[tk.Canvas]) -> None:
        column_key = self._column_at(event.x)
        column = next((item for item in self.columns if item.key == column_key), None)
        self.header.configure(cursor="hand2" if column is not None and column.sortable else "")

    def _on_right_click(self, event: tk.Event[tk.Canvas]) -> str:
        row_id = self._row_at(event.y)
        if row_id:
            if row_id not in self._selected:
                self.selection_set(row_id)
            if self.on_context is not None:
                self.on_context(row_id, event.x_root, event.y_root)
        return "break"

    def _on_motion(self, event: tk.Event[tk.Canvas]) -> None:
        self._set_hover(self._row_at(event.y))

    def _set_hover(self, row_id: str) -> None:
        if row_id == self._hovered_id:
            return
        previous = self._hovered_id
        self._hovered_id = row_id
        for candidate in (previous, row_id):
            self._update_row_fill(candidate)

    def _update_row_fill(self, row_id: str) -> None:
        rect = self._row_rects.get(row_id)
        row = self._row_by_id.get(row_id)
        if rect is None or row is None:
            return
        fill = self._row_fill(row_id, row)
        if self._row_fills.get(row_id) == fill:
            return
        self._row_fills[row_id] = fill
        self.body.itemconfigure(rect, fill=fill)
        progress = self._progress_items.get(row_id)
        if progress is not None and row.remaining_seconds is not None:
            color = "#F59E0B" if row.remaining_seconds <= 10 else ACCENT
            progress_image = self._progress_photo(row.remaining_seconds, row.period, color, fill)
            self._progress_images[row_id] = progress_image
            self.body.itemconfigure(progress[0], image=progress_image)

    def _row_fill(self, row_id: str, row: TableRow) -> str:
        if row_id in self._selected:
            return SELECTION
        if row_id == self._hovered_id:
            return "#F3F7FC"
        if row.pinned:
            return PINNED_SURFACE
        return GLASS_SURFACE

    def _select_row(self, row_id: str, *, control: bool, shift: bool) -> None:
        ids = [row.id for row in self._rows]
        if shift:
            anchor = self._anchor_id if self._anchor_id in ids else row_id
            start, end = sorted((ids.index(anchor), ids.index(row_id)))
            self._selected = set(ids[start : end + 1])
        elif control:
            if row_id in self._selected:
                self._selected.remove(row_id)
            else:
                self._selected.add(row_id)
            self._anchor_id = row_id
        else:
            self._selected = {row_id}
            self._anchor_id = row_id
        self._focused_id = row_id
        self._render_selection()
        self._notify_selection()

    def _render_selection(self) -> None:
        for row in self._rows:
            if row.id not in self._rendered_ids:
                continue
            self._update_row_fill(row.id)
            checkbox = self._checkboxes.get(row.id)
            if checkbox:
                selected = row.id in self._selected
                self.body.itemconfigure(checkbox[0], fill=ACCENT if selected else GLASS_SURFACE, outline=ACCENT if selected else "#CBD5E1")
                self.body.itemconfigure(checkbox[1], text="✓" if selected else "")
        self._draw_header_checkbox()

    def _draw_header_checkbox(self) -> None:
        self.header.delete("header_check")
        selected = bool(self._rows) and len(self._selected) == len(self._rows)
        for column, start, end in self._column_bounds:
            if column.key == "select":
                items = self._draw_checkbox(
                    self.header,
                    (start + end) // 2,
                    self.dpi_context.dp(21),
                    selected,
                )
                for item in items:
                    self.header.addtag_withtag("header_check", item)
                break

    def _notify_selection(self) -> None:
        if self.on_selection is not None:
            self.on_selection()

    def _on_mousewheel(self, event: tk.Event[tk.Canvas]) -> str:
        self.body.yview_scroll(-1 * int(event.delta / 120), "units")
        self._schedule_visible_draw()
        return "break"

    def _select_all_event(self, _event: tk.Event[tk.Canvas] | None = None) -> str:
        self.selection_set([row.id for row in self._rows])
        return "break"

    def _toggle_focus_event(self, _event: tk.Event[tk.Canvas] | None = None) -> str:
        if self._focused_id:
            if self._focused_id in self._selected:
                self.selection_remove(self._focused_id)
            else:
                self.selection_add(self._focused_id)
        return "break"

    def _move_focus(self, direction: int, extend: bool) -> str:
        ids = [row.id for row in self._rows]
        if not ids:
            return "break"
        current = self._focused_id if self._focused_id in ids else ids[0]
        target = ids[max(0, min(len(ids) - 1, ids.index(current) + direction))]
        self._select_row(target, control=False, shift=extend)
        self.see(target)
        return "break"

    def selection(self) -> tuple[str, ...]:
        return tuple(row.id for row in self._rows if row.id in self._selected)

    def selection_set(self, items: str | Sequence[str]) -> None:
        values = (items,) if isinstance(items, str) else tuple(items)
        self._selected = {item for item in values if item in self._row_by_id}
        if values and values[0] in self._row_by_id:
            self._focused_id = values[0]
            self._anchor_id = values[0]
        self._render_selection()
        self._notify_selection()

    def selection_add(self, item: str) -> None:
        if item in self._row_by_id:
            self._selected.add(item)
            self._focused_id = item
            self._render_selection()
            self._notify_selection()

    def selection_remove(self, item: str) -> None:
        self._selected.discard(item)
        self._render_selection()
        self._notify_selection()

    def focused(self) -> str:
        return self._focused_id

    def set_focus(self, item: str) -> None:
        if item in self._row_by_id:
            self._focused_id = item

    def focus_set(self) -> None:
        self.body.focus_set()

    def exists(self, item: str) -> bool:
        return item in self._row_by_id

    def get_children(self) -> tuple[str, ...]:
        return tuple(row.id for row in self._rows)

    def see(self, item: str) -> None:
        ids = [row.id for row in self._rows]
        if item not in ids:
            return
        top = ids.index(item) * self.row_height
        bottom = top + self.row_height
        visible_top = self.body.canvasy(0)
        visible_bottom = visible_top + self.body.winfo_height()
        total = max(1, len(ids) * self.row_height)
        if top < visible_top:
            self.body.yview_moveto(top / total)
        elif bottom > visible_bottom:
            self.body.yview_moveto(max(0, (bottom - self.body.winfo_height()) / total))
        self._schedule_visible_draw()

    def scroll_fraction(self) -> float:
        return float(self.body.yview()[0]) if self._rows else 0.0

    def restore_scroll(self, fraction: float) -> None:
        self.body.yview_moveto(max(0.0, min(1.0, fraction)))
        self._schedule_visible_draw()

    def invalidate_scale(self) -> None:
        """Rebuild pixel-sized assets after moving to a monitor with another DPI."""

        self.row_height = self.dpi_context.dp(self._logical_row_height)
        self.header.configure(height=self.dpi_context.dp(42))
        self.scrollbar.invalidate_scale()
        self._progress_image_cache.clear()
        if self._layout_active:
            self._draw()
        else:
            self._resize_dirty = True

    def destroy(self) -> None:
        self._resize_debouncer.cancel()
        if self._visible_after_id is not None:
            try:
                self.after_cancel(self._visible_after_id)
            except tk.TclError:
                pass
        self._visible_after_id = None
        super().destroy()

    def set_locked(self, locked: bool) -> None:
        self.body.configure(takefocus=not locked)
        if locked:
            self._selected.clear()
            self._focused_id = ""
            self._render_selection()
