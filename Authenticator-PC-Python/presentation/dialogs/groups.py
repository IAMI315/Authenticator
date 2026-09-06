"""分组名称、批量归属和分组管理三个 Tk 对话框。"""

from __future__ import annotations

import tkinter as tk
from functools import partial
from tkinter import messagebox, ttk
from typing import Any

from domain.entities import DEFAULT_GROUP_ID, AccountGroup, OTPEntry
from domain.validators import format_created_at
from presentation.constants import APP_NAME
from presentation.dpi import dpi_context_for
from presentation.glass_scrollbar import GlassScrollbar
from presentation.styles import GLASS_SURFACE, GLASS_SURFACE_MUTED, UI_FONT, center_dialog, configure_dialog_surface


class GroupNameDialog(tk.Toplevel):
    """收集单个自定义分组名称的轻量模态对话框。"""

    def __init__(self, parent: Any, title: str, initial_name: str = "") -> None:
        """以可选初始名称创建表单；最终唯一性检查由 ``GroupService`` 完成。"""

        super().__init__(parent)
        self.result: str | None = None
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        configure_dialog_surface(self)

        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 22))
        frame.grid(sticky="nsew")
        ttk.Label(frame, text="分组名称", style="Form.TLabel").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar(value=initial_name)
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, width=34)
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=(7, 0))

        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.grid(row=2, column=0, sticky="e", pady=(18, 0))
        ttk.Button(buttons, text="取消", command=self.cancel, style="Secondary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="保存", command=self.submit, style="Primary.TButton").grid(row=0, column=1)

        self.bind("<Return>", lambda _event: self.submit())
        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        center_dialog(self, parent)
        self.grab_set()
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, tk.END)

    def submit(self) -> None:
        """压缩输入空白并返回非空名称；不在 UI 层判断保留名或重复名。"""

        name = " ".join(self.name_var.get().split())
        if not name:
            messagebox.showwarning(APP_NAME, "请输入分组名称。", parent=self)
            return
        self.result = name
        self.destroy()

    def cancel(self) -> None:
        """取消并关闭，不设置结果。"""

        self.destroy()

    @classmethod
    def ask(cls, parent: Any, title: str, initial_name: str = "") -> str | None:
        """显示模态名称对话框并返回用户确认的名称或 ``None``。"""

        dialog = cls(parent, title, initial_name)
        parent.wait_window(dialog)
        return dialog.result


class GroupAssignmentDialog(tk.Toplevel):
    """选择批量分组归属，直到点击应用前都不改变混合选中账号。"""

    def __init__(self, parent: Any, groups: list[AccountGroup], entries: list[OTPEntry]) -> None:
        """根据选中账号的共同/部分归属初始化复选框和延迟变更字典。"""

        super().__init__(parent)
        self.result: dict[str, bool] | None = None
        self._changes: dict[str, bool | None] = {}
        self._variables: dict[str, tk.BooleanVar] = {}
        self._buttons: dict[str, ttk.Checkbutton] = {}
        self._names: dict[str, str] = {}
        self.title("账号分组")
        dpi = dpi_context_for(parent)
        self.minsize(dpi.dp(420), dpi.dp(320))
        self.resizable(True, True)
        self.transient(parent)
        configure_dialog_surface(self)

        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 22))
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=f"已选择 {len(entries)} 个账号", style="Form.TLabel", font=(UI_FONT, 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )

        list_host = tk.Frame(frame, background=GLASS_SURFACE, highlightthickness=0)
        list_host.grid(row=1, column=0, sticky="nsew")
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(0, weight=1)
        canvas = tk.Canvas(list_host, background=GLASS_SURFACE, highlightthickness=0, borderwidth=0)
        scrollbar = GlassScrollbar(list_host, command=canvas.yview, width=10)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        inner = ttk.Frame(canvas, style="Dialog.TFrame")
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(canvas_window, width=event.width))

        # “部分”状态不直接写回实体；只有用户切换某项才记录到 ``_changes``。
        for row, group in enumerate(groups):
            memberships = [group.id in entry.group_ids for entry in entries]
            everyone_has_group = all(memberships)
            some_have_group = any(memberships)
            label = group.name + ("（部分）" if some_have_group and not everyone_has_group else "")
            variable = tk.BooleanVar(value=everyone_has_group)
            self._variables[group.id] = variable
            self._names[group.id] = group.name
            button = ttk.Checkbutton(
                inner,
                text=label,
                variable=variable,
                command=partial(self._record_change, group.id),
            )
            if group.id == DEFAULT_GROUP_ID:
                button.configure(state="disabled")
            self._buttons[group.id] = button
            button.grid(row=row, column=0, sticky="w", pady=4)

        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.grid(row=2, column=0, sticky="e", pady=(18, 0))
        ttk.Button(buttons, text="取消", command=self.cancel, style="Secondary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="应用", command=self.submit, style="Primary.TButton").grid(row=0, column=1)

        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        center_dialog(self, parent)
        self.grab_set()

    def _record_change(self, group_id: str) -> None:
        """记录用户实际切换的分组布尔值，并移除“部分”显示后缀。"""

        self._changes[group_id] = self._variables[group_id].get()
        self._buttons[group_id].configure(text=self._names[group_id])

    def submit(self) -> None:
        """返回仅包含用户改动的非默认分组映射。"""

        self.result = {
            group_id: value
            for group_id, value in self._changes.items()
            if value is not None and group_id != DEFAULT_GROUP_ID
        }
        self.destroy()

    def cancel(self) -> None:
        """取消批量归属修改。"""

        self.destroy()

    @classmethod
    def ask(
        cls, parent: Any, groups: list[AccountGroup], entries: list[OTPEntry]
    ) -> dict[str, bool] | None:
        """显示模态归属对话框并返回改动映射或 ``None``。"""

        dialog = cls(parent, groups, entries)
        parent.wait_window(dialog)
        return dialog.result


class GroupManagerDialog(tk.Toplevel):
    """展示当前分组表格，并通过注入的主窗口回调管理分组。"""

    def __init__(
        self,
        parent: Any,
        vault: Any,
        count_entries: Any,
        create_group: Any,
        rename_group: Any,
        delete_group: Any,
    ) -> None:
        """创建分组列表及操作按钮；``vault`` 仅供只读展示和刷新。"""

        super().__init__(parent)
        self.vault = vault
        self.count_entries = count_entries
        self.create_group = create_group
        self.rename_group = rename_group
        self.delete_group = delete_group
        self.title("管理分组")
        dpi = dpi_context_for(parent)
        self.minsize(dpi.dp(520), dpi.dp(360))
        self.resizable(True, True)
        self.transient(parent)
        configure_dialog_surface(self)

        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 22))
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        table_host = ttk.Frame(frame, style="Dialog.TFrame")
        table_host.grid(row=0, column=0, sticky="nsew")
        table_host.columnconfigure(0, weight=1)
        table_host.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_host, columns=("name", "count", "created"), show="headings", selectmode="browse", height=8)
        self.tree.heading("name", text="分组")
        self.tree.heading("count", text="账号数")
        self.tree.heading("created", text="创建时间")
        self.tree.column("name", width=250, minwidth=140, anchor="w")
        self.tree.column("count", width=80, minwidth=70, anchor="center")
        self.tree.column("created", width=145, minwidth=120, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = GlassScrollbar(table_host, command=self.tree.yview, width=10)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("default_group", background=GLASS_SURFACE_MUTED)
        self.tree.bind("<<TreeviewSelect>>", self._update_buttons)

        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.grid(row=1, column=0, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="新建", command=self._create, style="Primary.TButton").grid(row=0, column=0, padx=(0, 8))
        self.rename_button = ttk.Button(buttons, text="重命名", command=self._rename, style="Secondary.TButton")
        self.rename_button.grid(row=0, column=1, padx=3)
        self.delete_button = ttk.Button(buttons, text="删除", command=self._delete, style="Danger.TButton")
        self.delete_button.grid(row=0, column=2, padx=3)
        ttk.Button(buttons, text="关闭", command=self.destroy, style="Secondary.TButton").grid(row=0, column=3, padx=(8, 0))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_dialog(self, parent)
        self.grab_set()
        self.refresh()

    def _selected_group(self) -> AccountGroup | None:
        """返回表格中唯一选择的分组实体。"""

        selection = self.tree.selection()
        if len(selection) != 1:
            return None
        return self.vault.group_by_id(selection[0])

    def _update_buttons(self, _event: tk.Event[Any] | None = None) -> None:
        """默认分组或空选择时禁用重命名和删除按钮。"""

        group = self._selected_group()
        state = "normal" if group is not None and group.id != DEFAULT_GROUP_ID else "disabled"
        self.rename_button.configure(state=state)
        self.delete_button.configure(state=state)

    def refresh(self) -> None:
        """从当前保险库重建分组表格，并尽量保留原来的选中行。"""

        selected = self.tree.selection()
        selected_id = selected[0] if len(selected) == 1 else None
        for item in self.tree.get_children():
            self.tree.delete(item)
        for group in self.vault.groups:
            tags = ("default_group",) if group.id == DEFAULT_GROUP_ID else ()
            self.tree.insert(
                "",
                "end",
                iid=group.id,
                values=(group.name, self.count_entries(group.id), format_created_at(group.created_at)),
                tags=tags,
            )
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)
        self._update_buttons()

    def _create(self) -> None:
        """收集名称并调用主窗口的新建分组回调，成功后刷新表格。"""

        name = GroupNameDialog.ask(self, "新建分组")
        if name and self.create_group(name):
            self.refresh()

    def _rename(self) -> None:
        """收集新名称并调用主窗口重命名回调。"""

        group = self._selected_group()
        if group is None or group.id == DEFAULT_GROUP_ID:
            return
        name = GroupNameDialog.ask(self, "重命名分组", group.name)
        if name and self.rename_group(group.id, name):
            self.refresh()

    def _delete(self) -> None:
        """确认后调用主窗口删除回调；账号保留规则由服务层执行。"""

        group = self._selected_group()
        if group is None or group.id == DEFAULT_GROUP_ID:
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"确定删除分组“{group.name}”吗？账号不会被删除。",
            parent=self,
        ):
            return
        if self.delete_group(group.id):
            self.refresh()

    @classmethod
    def show(
        cls,
        parent: Any,
        vault: Any,
        count_entries: Any,
        create_group: Any,
        rename_group: Any,
        delete_group: Any,
    ) -> None:
        """显示模态分组管理窗口，关闭前阻塞其父窗口操作。"""

        dialog = cls(parent, vault, count_entries, create_group, rename_group, delete_group)
        parent.wait_window(dialog)
