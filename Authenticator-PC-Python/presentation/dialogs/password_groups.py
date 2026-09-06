"""Password-book group assignment and management dialogs."""

from __future__ import annotations

import tkinter as tk
from functools import partial
from tkinter import messagebox, ttk
from typing import Any

from domain.passwords import PASSWORD_DEFAULT_GROUP_ID, PasswordEntry, PasswordGroup
from domain.validators import format_created_at
from presentation.constants import APP_NAME
from presentation.dialogs.groups import GroupNameDialog
from presentation.dpi import dpi_context_for
from presentation.styles import GLASS_SURFACE_MUTED, UI_FONT, center_dialog, configure_dialog_surface


class PasswordGroupAssignmentDialog(tk.Toplevel):
    def __init__(self, parent: Any, groups: list[PasswordGroup], entries: list[PasswordEntry]) -> None:
        super().__init__(parent)
        self.result: dict[str, bool] | None = None
        self.changes: dict[str, bool] = {}
        self.title("密码分组")
        self.resizable(False, True)
        self.transient(parent)
        configure_dialog_surface(self)
        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 20))
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=f"为 {len(entries)} 条密码设置分组",
            style="Form.TLabel",
            font=(UI_FONT, 10, "bold"),
        ).pack(anchor="w", pady=(0, 10))
        self.variables: dict[str, tk.BooleanVar] = {}
        self.buttons: dict[str, ttk.Checkbutton] = {}
        self.names: dict[str, str] = {}
        for group in groups:
            memberships = [group.id in entry.group_ids for entry in entries]
            everyone_has_group = all(memberships)
            some_have_group = any(memberships)
            label = group.name + ("（部分）" if some_have_group and not everyone_has_group else "")
            variable = tk.BooleanVar(value=everyone_has_group)
            self.variables[group.id] = variable
            self.names[group.id] = group.name
            button = ttk.Checkbutton(
                frame,
                text=label,
                variable=variable,
                command=partial(self.record_change, group.id),
            )
            if group.id == PASSWORD_DEFAULT_GROUP_ID:
                variable.set(True)
                button.configure(state="disabled")
            self.buttons[group.id] = button
            button.pack(anchor="w", pady=3)
        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.pack(anchor="e", pady=(16, 0))
        ttk.Button(buttons, text="取消", command=self.destroy, style="Secondary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="应用", command=self.submit, style="Primary.TButton").grid(row=0, column=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_dialog(self, parent)
        self.grab_set()

    def record_change(self, group_id: str) -> None:
        self.changes[group_id] = self.variables[group_id].get()
        self.buttons[group_id].configure(text=self.names[group_id])

    def submit(self) -> None:
        self.result = {
            group_id: value
            for group_id, value in self.changes.items()
            if group_id != PASSWORD_DEFAULT_GROUP_ID
        }
        self.destroy()

    @classmethod
    def ask(
        cls, parent: Any, groups: list[PasswordGroup], entries: list[PasswordEntry]
    ) -> dict[str, bool] | None:
        dialog = cls(parent, groups, entries)
        parent.wait_window(dialog)
        return dialog.result


class PasswordGroupManagerDialog(tk.Toplevel):
    def __init__(self, parent: Any, controller: Any) -> None:
        super().__init__(parent)
        self.controller = controller
        self.title("管理密码分组")
        self.geometry(dpi_context_for(parent).physical_geometry("540x390"))
        self.transient(parent)
        configure_dialog_surface(self)
        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 20))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=("name", "count", "created"), show="headings", selectmode="browse")
        for column, text, width in (
            ("name", "分组", 240),
            ("count", "密码数", 80),
            ("created", "创建时间", 145),
        ):
            self.tree.heading(column, text=text)
            self.tree.column(column, width=width, anchor="w" if column != "count" else "center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("default_group", background=GLASS_SURFACE_MUTED)
        self.tree.bind("<<TreeviewSelect>>", self.update_buttons)
        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.grid(row=1, column=0, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="新建", command=self.create, style="Primary.TButton").grid(row=0, column=0, padx=3)
        self.rename_button = ttk.Button(buttons, text="重命名", command=self.rename, style="Secondary.TButton")
        self.rename_button.grid(row=0, column=1, padx=3)
        self.delete_button = ttk.Button(buttons, text="删除", command=self.delete, style="Danger.TButton")
        self.delete_button.grid(row=0, column=2, padx=3)
        ttk.Button(buttons, text="关闭", command=self.destroy, style="Secondary.TButton").grid(row=0, column=3, padx=(8, 0))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_dialog(self, parent)
        self.grab_set()
        self.refresh()

    def selected_id(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if len(selection) == 1 else None

    def update_buttons(self, _event: tk.Event[Any] | None = None) -> None:
        selected_id = self.selected_id()
        state = "normal" if selected_id and selected_id != PASSWORD_DEFAULT_GROUP_ID else "disabled"
        self.rename_button.configure(state=state)
        self.delete_button.configure(state=state)

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for group in self.controller.groups():
            count = self.controller.group_entry_count(group.id)
            tags = ("default_group",) if group.id == PASSWORD_DEFAULT_GROUP_ID else ()
            self.tree.insert("", "end", iid=group.id, values=(group.name, count, format_created_at(group.created_at)), tags=tags)
        self.update_buttons()

    def create(self) -> None:
        name = GroupNameDialog.ask(self, "新建密码分组")
        if name and self.controller.create_group(name):
            self.refresh()

    def rename(self) -> None:
        group_id = self.selected_id()
        group = self.controller.group_by_id(group_id) if group_id else None
        if group is None:
            return
        name = GroupNameDialog.ask(self, "重命名密码分组", group.name)
        if name and self.controller.rename_group(group.id, name):
            self.refresh()

    def delete(self) -> None:
        group_id = self.selected_id()
        group = self.controller.group_by_id(group_id) if group_id else None
        if group is None:
            return
        if messagebox.askyesno(APP_NAME, f"确定删除分组“{group.name}”吗？密码记录不会被删除。", parent=self):
            if self.controller.delete_group(group.id):
                self.refresh()

    @classmethod
    def show(cls, parent: Any, controller: Any) -> None:
        dialog = cls(parent, controller)
        parent.wait_window(dialog)
