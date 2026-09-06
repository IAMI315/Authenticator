"""Interaction regression tests for the shared Canvas data table."""

import tkinter as tk
from types import SimpleNamespace

from PIL import Image

from presentation.canvas_table import CanvasDataTable, ColumnSpec, TableRow
from presentation.icon_registry import IconRegistry


def _rows(count: int = 4) -> list[TableRow]:
    return [
        TableRow(str(index), {"service": f"Service {index}", "value": f"Value {index}"})
        for index in range(count)
    ]


def test_canvas_table_hit_regions_and_selection_modes():
    root = tk.Tk()
    root.withdraw()
    try:
        table = CanvasDataTable(
            root,
            (
                ColumnSpec("select", "", 36),
                ColumnSpec("service", "服务", 120),
                ColumnSpec("value", "值", 160, weight=1),
            ),
            primary_column="value",
            service_column="service",
        )
        table.pack(fill="both", expand=True)
        root.geometry("420x260")
        root.update_idletasks()
        table.set_rows(_rows())
        root.update_idletasks()

        assert table.identify_row(10) == "0"
        assert table.identify_row(table.row_height + 5) == "1"
        assert table.identify_column(10) == "select"
        assert table.identify_column(50) == "service"

        table._select_row("1", control=False, shift=False)
        table._select_row("3", control=False, shift=True)
        assert table.selection() == ("1", "2", "3")
        table._select_row("2", control=True, shift=False)
        assert table.selection() == ("1", "3")
        table._select_all_event()
        assert table.selection() == ("0", "1", "2", "3")
        table._move_focus(-1, False)
        assert table.focused() == "0"
    finally:
        root.destroy()


def test_checkbox_clicks_accumulate_and_marker_actions_preserve_selection():
    root = tk.Tk()
    root.withdraw()
    actions: list[tuple[str, str]] = []
    try:
        table = CanvasDataTable(
            root,
            (
                ColumnSpec("select", "", 36),
                ColumnSpec("pin", "", 32),
                ColumnSpec("service", "服务", 120),
                ColumnSpec("value", "值", 160, weight=1),
            ),
            icons=IconRegistry(root),
            primary_column="value",
            service_column="service",
            on_action=lambda row_id, action: actions.append((row_id, action)),
        )
        table.pack(fill="both", expand=True)
        root.geometry("420x260")
        root.update_idletasks()
        table.set_rows(_rows())
        root.update_idletasks()
        bounds = {column.key: (start, end) for column, start, end in table._column_bounds}
        select_x = sum(bounds["select"]) // 2
        pin_x = sum(bounds["pin"]) // 2

        table._on_click(SimpleNamespace(x=select_x, y=table.row_height // 2, state=0))
        table._on_click(SimpleNamespace(x=select_x, y=table.row_height + table.row_height // 2, state=0))
        assert table.selection() == ("0", "1")
        table._on_click(SimpleNamespace(x=pin_x, y=table.row_height // 4, state=0))
        table._on_click(SimpleNamespace(x=pin_x, y=table.row_height * 3 // 4, state=0))
        assert actions == [("0", "toggle_favorite"), ("0", "toggle_pin")]
        assert table.selection() == ("0", "1")
    finally:
        root.destroy()


def test_canvas_table_update_preserves_identity_and_scroll():
    root = tk.Tk()
    root.withdraw()
    try:
        table = CanvasDataTable(
            root,
            (ColumnSpec("service", "服务", 120), ColumnSpec("value", "值", 160, weight=1)),
            primary_column="value",
            service_column="service",
        )
        table.pack(fill="both", expand=True)
        root.geometry("360x180")
        root.update_idletasks()
        rows = _rows(20)
        table.set_rows(rows)
        table.selection_set("8")
        table.restore_scroll(0.5)
        assert table.update_rows(rows) is True
        assert table.selection() == ("8",)
        assert table.scroll_fraction() > 0
        assert table.update_rows(rows[:-1]) is False
    finally:
        root.destroy()


def test_canvas_table_update_keeps_long_text_inside_its_column():
    root = tk.Tk()
    root.withdraw()
    try:
        table = CanvasDataTable(
            root,
            (ColumnSpec("account", "账号", 180), ColumnSpec("code", "验证码", 100, align="center")),
            primary_column="code",
            service_column="service",
        )
        table.pack(fill="both", expand=True)
        root.geometry("300x160")
        root.update_idletasks()
        long_account = "very-long-account-name-639400@outlook.com"
        row = TableRow("one", {"account": long_account, "code": "123456"})
        table.set_rows([row])
        root.update_idletasks()
        account_item = table._cell_items[("one", "account")]
        assert table.body.itemcget(account_item, "text").endswith("…")

        table.update_rows([row])
        updated_text = table.body.itemcget(account_item, "text")
        assert updated_text.endswith("…")
        assert updated_text != long_account
    finally:
        root.destroy()


def test_canvas_table_only_dispatches_sortable_headers_and_tracks_direction():
    root = tk.Tk()
    root.withdraw()
    calls: list[str] = []
    try:
        table = CanvasDataTable(
            root,
            (
                ColumnSpec("select", "", 36),
                ColumnSpec("service", "服务", 120, sortable=True),
                ColumnSpec("code", "验证码", 100),
                ColumnSpec("created", "创建时间", 130, sortable=True),
            ),
            primary_column="code",
            service_column="service",
            on_sort=calls.append,
        )
        table.pack(fill="both", expand=True)
        root.geometry("420x180")
        root.update_idletasks()
        table.set_rows(_rows(2))
        table.set_sort_state("created", "descending")

        bounds = {column.key: (start, end) for column, start, end in table._column_bounds}
        for key in ("service", "code", "created"):
            start, end = bounds[key]
            table._on_header_click(SimpleNamespace(x=(start + end) // 2))
        assert calls == ["service", "created"]
        assert table._sort_key == "created"
        assert table._sort_direction == "descending"
    finally:
        root.destroy()


def test_progress_bitmap_is_antialiased_and_precomposited():
    bitmap = CanvasDataTable._render_progress_bitmap(4, 30, "#F59E0B")
    assert bitmap.size == (38, 38)
    assert bitmap.mode == "RGB"
    colors = set(bitmap.getdata())
    assert (255, 255, 255) in colors
    assert len(colors) > 20
    assert isinstance(bitmap, Image.Image)
