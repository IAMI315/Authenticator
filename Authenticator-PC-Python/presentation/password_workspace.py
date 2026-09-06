"""Password-book workspace using the shared Canvas data table."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Protocol

from domain.passwords import PasswordEntry
from presentation.canvas_table import CanvasDataTable, ColumnSpec, RowAction, TableRow
from presentation.icon_registry import IconRegistry
from presentation.styles import GLASS_BORDER, GLASS_SHADOW


class PasswordActions(Protocol):
    view_model: Any

    def refresh(self) -> None: ...
    def add(self) -> None: ...
    def edit(self) -> None: ...
    def copy_username(self) -> None: ...
    def copy_password(self) -> None: ...
    def toggle_reveal(self) -> None: ...
    def open_website(self) -> None: ...
    def assign_groups(self) -> None: ...
    def toggle_pinned(self) -> None: ...
    def set_pinned(self, pinned: bool) -> None: ...
    def toggle_pinned_for(self, entry_id: str) -> None: ...
    def toggle_favorite(self) -> None: ...
    def set_favorite(self, favorite: bool) -> None: ...
    def toggle_favorite_for(self, entry_id: str) -> None: ...
    def toggle_show_pinned(self) -> None: ...
    def delete(self) -> None: ...
    def create_group(self, name: str | None = None) -> bool: ...
    def manage_groups(self) -> None: ...
    def sort_by(self, column_key: str) -> None: ...


class PasswordWorkspace(ttk.Frame):
    def __init__(self, parent: tk.Misc, actions: PasswordActions, icons: IconRegistry) -> None:
        super().__init__(parent, style="App.TFrame")
        self.actions = actions
        self.icons = icons
        self.query_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="0 条密码")
        self.detail_var = tk.StringVar(value="选择一条密码记录以复制、显示或编辑。")
        self.action_widgets: list[ttk.Button] = []
        self.selection_widgets: list[ttk.Button] = []
        self.footer_buttons: dict[str, ttk.Button] = {}
        self.footer_frame: ttk.Frame | None = None
        self.locked = False
        self._header_images: list[Any] = []
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build()
        self.query_var.trace_add("write", lambda *_args: self.actions.refresh())

    @staticmethod
    def _surface(parent: tk.Misc, padding: Any) -> tuple[tk.Frame, ttk.Frame]:
        shadow = tk.Frame(parent, background=GLASS_SHADOW, borderwidth=0, highlightthickness=0)
        border = tk.Frame(shadow, background=GLASS_BORDER, borderwidth=0, highlightthickness=0)
        border.pack(fill="both", expand=True, padx=1, pady=1)
        surface = ttk.Frame(border, style="Glass.TFrame", padding=padding)
        surface.pack(fill="both", expand=True, padx=1, pady=1)
        return shadow, surface

    def _button(self, parent: tk.Misc, text: str, command: Any, style: str = "Secondary.TButton") -> ttk.Button:
        width = max(4, sum(2 if ord(character) > 127 else 1 for character in text) + 2)
        button = ttk.Button(parent, text=text, command=command, style=style, width=width)
        self.action_widgets.append(button)
        return button

    def _build(self) -> None:
        header_border, header = self._surface(self, (14, 10))
        header_border.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="密码列表", style="ListTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.search_entry = ttk.Entry(header, textvariable=self.query_var, style="Search.TEntry")
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(18, 8))
        self.search_entry.bind("<Escape>", self.clear_search)
        ttk.Label(header, textvariable=self.summary_var, style="SearchSummary.TLabel").grid(row=0, column=2, padx=(0, 8))
        pin_image = self.icons.image("pin", 15)
        self._header_images.append(pin_image)
        self.show_pinned_button = ttk.Button(
            header,
            text="置顶可见",
            image=pin_image,
            compound="left",
            command=self.actions.toggle_show_pinned,
            style="ModuleActive.TButton",
            width=10,
        )
        self.show_pinned_button.grid(row=0, column=3, padx=3)
        self._button(header, "新建分组", self.actions.create_group, "Quiet.TButton").grid(row=0, column=4, padx=3)
        self._button(header, "管理分组", self.actions.manage_groups, "Quiet.TButton").grid(row=0, column=5, padx=(3, 0))

        columns = (
            ColumnSpec("select", "", 34, 34, align="center"),
            ColumnSpec("pin", "", 32, 30, align="center"),
            ColumnSpec("name", "名称/服务", 155, 105, 2, sortable=True),
            ColumnSpec("username", "用户名", 205, 125, 3, sortable=True),
            ColumnSpec("password", "密码", 145, 115, 2, "center"),
            ColumnSpec("url", "网址", 180, 100, 2, sortable=True),
            ColumnSpec(
                "created", "创建时间", 132, 105, 1,
                sortable=True, initial_sort_direction="descending",
            ),
            ColumnSpec("actions", "操作", 46, 42, align="center"),
        )
        self.table = CanvasDataTable(
            self,
            columns,
            icons=self.icons,
            primary_column="password",
            service_column="name",
            on_selection=self.update_action_states,
            on_action=self._on_table_action,
            on_context=self.show_context_menu,
            on_sort=self.actions.sort_by,
        )
        sort_spec = self.actions.view_model.sort_spec
        self.table.set_sort_state(sort_spec.field.value, sort_spec.direction.value)
        self.table.grid(row=1, column=0, sticky="nsew")
        self.tree = self.table

        self.context_menu = tk.Menu(self, tearoff=False)
        for label, command in (
            ("复制用户名", self.actions.copy_username),
            ("复制密码", self.actions.copy_password),
            ("显示/隐藏", self.actions.toggle_reveal),
            ("打开网站", self.actions.open_website),
            ("编辑", self.actions.edit),
            ("分组...", self.actions.assign_groups),
            ("收藏", lambda: self.actions.set_favorite(True)),
            ("取消收藏", lambda: self.actions.set_favorite(False)),
            ("置顶", lambda: self.actions.set_pinned(True)),
            ("取消置顶", lambda: self.actions.set_pinned(False)),
            ("删除", self.actions.delete),
        ):
            self.context_menu.add_command(label=label, command=command)

    def create_footer(self, parent: tk.Misc) -> ttk.Frame:
        footer = ttk.Frame(parent, style="Footer.TFrame")
        actions = (
            ("copy_username", "复制用户名", self.actions.copy_username, "Secondary.TButton"),
            ("copy_password", "复制密码", self.actions.copy_password, "Primary.TButton"),
            ("reveal", "显示/隐藏", self.actions.toggle_reveal, "Secondary.TButton"),
            ("open", "打开网站", self.actions.open_website, "Secondary.TButton"),
            ("edit", "编辑", self.actions.edit, "Secondary.TButton"),
            ("group", "分组", self.actions.assign_groups, "Secondary.TButton"),
            ("favorite", "收藏/取消", self.actions.toggle_favorite, "Secondary.TButton"),
            ("pin", "置顶/取消", self.actions.toggle_pinned, "Secondary.TButton"),
            ("delete", "删除", self.actions.delete, "Danger.TButton"),
        )
        for column, (key, text, command, style) in enumerate(actions):
            width = max(4, sum(2 if ord(character) > 127 else 1 for character in text) + 2)
            button = ttk.Button(footer, text=text, command=command, style=style, width=width)
            button.grid(row=0, column=column, padx=3)
            self.selection_widgets.append(button)
            self.footer_buttons[key] = button
        more = ttk.Button(
            footer,
            text="更多操作",
            command=self._popup_more_actions,
            style="Secondary.TButton",
            width=10,
        )
        self.footer_buttons["more"] = more
        self.footer_frame = footer
        self.update_action_states()
        return footer

    def set_compact_actions(self, compact: bool) -> None:
        if not self.footer_buttons:
            return
        secondary = ("reveal", "open", "favorite", "pin", "delete")
        if compact:
            for key in secondary:
                self.footer_buttons[key].grid_remove()
            self.footer_buttons["more"].grid(row=0, column=8, padx=3)
        else:
            self.footer_buttons["more"].grid_remove()
            positions = {"reveal": 2, "open": 3, "favorite": 6, "pin": 7, "delete": 8}
            for key in secondary:
                self.footer_buttons[key].grid(row=0, column=positions[key], padx=3)

    def _popup_more_actions(self) -> None:
        button = self.footer_buttons["more"]
        self.context_menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() - self.context_menu.winfo_reqheight())

    def selection_ids(self) -> tuple[str, ...]:
        return tuple(item for item in self.table.selection() if not item.startswith("__"))

    def render(self, entries: list[PasswordEntry], rows: list[Any], summary: str, locked: bool) -> None:
        scroll_fraction = self.table.scroll_fraction()
        self.locked = locked
        self.summary_var.set(summary)
        table_rows = [
            TableRow(
                id=entry.id,
                values={
                    "name": row.name,
                    "username": row.username,
                    "password": row.password,
                    "url": row.url,
                    "created": row.created_at,
                },
                favorite=entry.favorite,
                pinned=entry.pinned,
                icon_key=row.icon_key or row.name,
                tags=row.tags,
            )
            for entry, row in zip(entries, rows, strict=True)
        ]
        if locked:
            message = "保险库已锁定，解锁后查看密码。"
            self.detail_var.set("解锁保险库后即可查看密码本。")
        elif not entries:
            message = "没有符合条件的密码记录。" if self.query_var.get().strip() else "暂无密码记录。"
            self.detail_var.set("点击“新增密码”创建第一条密码记录。")
        else:
            message = ""
        if table_rows and [row.id for row in table_rows] == list(self.table.get_children()):
            self.table.update_rows(table_rows)
        else:
            self.table.set_rows(table_rows, empty_message=message)
        self.table.restore_scroll(scroll_fraction)
        self.table.set_locked(locked)
        self.update_action_states()

    def update_action_states(self) -> None:
        state = "disabled" if self.locked else "normal"
        for widget in self.action_widgets:
            widget.configure(state=state)
        count = len(self.selection_ids())
        for index, widget in enumerate(self.selection_widgets):
            single_only = index in {0, 1, 2, 3, 4}
            enabled = not self.locked and (count == 1 if single_only else count > 0)
            widget.configure(state="normal" if enabled else "disabled")
        if count > 1:
            self.detail_var.set(f"已选择 {count} 条密码记录，可批量收藏、分组、置顶或删除。")
        elif count == 1:
            self.detail_var.set("已选择 1 条密码记录。")
        if hasattr(self.actions, "app"):
            self.actions.app.detail_var.set(self.detail_var.get())

    def clear_search(self, _event: tk.Event[Any] | None = None) -> str:
        self.query_var.set("")
        self.search_entry.focus_set()
        return "break"

    def focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")

    def _on_table_action(self, row_id: str, action: RowAction) -> None:
        if action in {"copy_primary", "activate"}:
            self.actions.copy_password()
        elif action == "toggle_favorite":
            self.actions.toggle_favorite_for(row_id)
        elif action == "toggle_pin":
            self.actions.toggle_pinned_for(row_id)
        elif action == "more":
            self.context_menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def show_context_menu(self, _row_id: str, x_root: int, y_root: int) -> None:
        if self.selection_ids():
            self.context_menu.tk_popup(x_root, y_root)

    def update_show_pinned_button(self, visible: bool) -> None:
        self.show_pinned_button.configure(
            style="ModuleActive.TButton" if visible else "ModuleInactive.TButton"
        )
