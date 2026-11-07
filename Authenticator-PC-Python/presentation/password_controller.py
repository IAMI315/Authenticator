"""Password workspace event controller and application-service adapter."""

from __future__ import annotations

import webbrowser
from tkinter import messagebox
from typing import Any

from application.password_commands import CreatePasswordCommand, UpdatePasswordCommand
from application.password_group_service import PasswordGroupService
from application.password_service import PasswordService
from application.sorting import PasswordSortField, PasswordSortSpec, SortDirection
from domain.passwords import PasswordEntry, PasswordGroup
from infrastructure.errors import VaultError
from presentation.constants import APP_NAME
from presentation.dialogs.groups import GroupNameDialog
from presentation.dialogs.password_entry import PasswordDialog
from presentation.dialogs.password_groups import (
    PasswordGroupAssignmentDialog,
    PasswordGroupManagerDialog,
)
from presentation.password_workspace import PasswordWorkspace
from presentation.view_models import AllScope, GroupScope, NavigationScope, PasswordViewModel


class PasswordController:
    def __init__(
        self,
        app: Any,
        service: PasswordService,
        group_service: PasswordGroupService,
        view_model: PasswordViewModel,
    ) -> None:
        self.app = app
        self.service = service
        self.group_service = group_service
        self.view_model = view_model
        self.workspace: PasswordWorkspace | None = None
        self.active_group_id: str | None = None

    def attach(self, workspace: PasswordWorkspace) -> None:
        self.workspace = workspace
        workspace.update_show_pinned_button(self.app.settings.password_show_pinned)
        self.refresh()

    def _guard(self) -> bool:
        return self.app._guard_unlocked()

    def _selected_entries(self) -> list[PasswordEntry]:
        if self.workspace is None:
            return []
        selected = set(self.workspace.selection_ids())
        return [entry for entry in self.app.vault.password_entries if entry.id in selected]

    def _single_entry(self) -> PasswordEntry | None:
        entries = self._selected_entries()
        if len(entries) != 1:
            self.app._show_status("请只选择一条密码记录。")
            return None
        return entries[0]

    def refresh(self) -> None:
        if self.workspace is None:
            return
        if self.view_model.passwords_visible != self.app.settings.passwords_visible:
            self.view_model.set_passwords_visible(self.app.settings.passwords_visible)
        scope = self.view_model.scope
        if isinstance(scope, GroupScope) and self.app.vault.password_group_by_id(scope.group_id) is None:
            scope = AllScope("全部密码")
        self.active_group_id = scope.group_id if isinstance(scope, GroupScope) else None
        self.view_model.update_state(
            query=self.workspace.query_var.get(),
            active_group_id=self.active_group_id,
            locked=self.app.locked,
            scope=scope,
        )
        entries = self.view_model.visible_entries()
        self.workspace.render(
            entries,
            [self.view_model.row(entry) for entry in entries],
            self.view_model.result_summary(len(entries)),
            self.app.locked,
        )

    def select_scope(self, scope: NavigationScope) -> None:
        self.view_model.set_scope(scope)
        self.active_group_id = scope.group_id if isinstance(scope, GroupScope) else None
        self.refresh()

    def sort_by(self, column_key: str) -> None:
        if self.workspace is None:
            return
        try:
            field = PasswordSortField(column_key)
        except ValueError:
            return
        current = self.view_model.sort_spec
        if current.field is field:
            direction = (
                SortDirection.DESCENDING
                if current.direction is SortDirection.ASCENDING
                else SortDirection.ASCENDING
            )
        else:
            direction = (
                SortDirection.DESCENDING
                if field is PasswordSortField.CREATED
                else SortDirection.ASCENDING
            )
        spec = PasswordSortSpec(field, direction)
        self.view_model.set_sort(spec)
        self.app.settings.password_sort_field = field.value
        self.app.settings.password_sort_direction = direction.value
        self.workspace.table.set_sort_state(field.value, direction.value)
        try:
            self.app.settings_repository.save(self.app.settings)
        except VaultError:
            self.app._show_status("排序已应用，但无法保存排序设置。")
        self.refresh()
        self.workspace.table.restore_scroll(0.0)

    def add(self) -> None:
        if not self._guard():
            return
        command = PasswordDialog.ask(self.app, initial_group_id=self.active_group_id)
        if not isinstance(command, CreatePasswordCommand):
            return
        try:
            entry = self.service.create(command)
        except (ValueError, VaultError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status(f"已新增密码记录：{entry.title}。")

    def edit(self) -> None:
        if not self._guard():
            return
        entry = self._single_entry()
        if entry is None:
            return
        self.conceal()
        command = PasswordDialog.ask(self.app, entry)
        if not isinstance(command, UpdatePasswordCommand):
            return
        try:
            updated = self.service.update(entry.id, command)
        except (ValueError, VaultError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status(f"已更新密码记录：{updated.title}。")

    def _copy(self, value: str, message: str) -> None:
        self.app.clipboard_clear()
        self.app.clipboard_append(value)
        self.app._show_status(message)

    def copy_username(self) -> None:
        entry = self._single_entry()
        if entry:
            self._copy(entry.username, f"已复制 {entry.title} 的用户名。")

    def copy_password(self) -> None:
        entry = self._single_entry()
        if entry:
            self._copy(entry.password, f"已复制 {entry.title} 的密码。")

    def toggle_reveal(self) -> None:
        entry = self._single_entry()
        if entry:
            self.view_model.toggle_reveal(entry.id)
            self.refresh()

    def conceal(self) -> None:
        self.view_model.conceal()
        self.refresh()

    def open_website(self) -> None:
        entry = self._single_entry()
        if entry is None:
            return
        if not entry.url:
            self.app._show_status("该密码记录没有网址。")
            return
        webbrowser.open(entry.url)
        self.app._show_status(f"正在打开 {entry.title} 的网站。")

    def assign_groups(self) -> None:
        if not self._guard():
            return
        entries = self._selected_entries()
        if not entries:
            return
        changes = PasswordGroupAssignmentDialog.ask(
            self.app, list(self.app.vault.password_groups), entries
        )
        if changes is None:
            return
        assignments: dict[str, list[str]] = {}
        for entry in entries:
            group_ids = list(entry.group_ids)
            for group_id, enabled in changes.items():
                if enabled:
                    if group_id not in group_ids:
                        group_ids.append(group_id)
                else:
                    group_ids = [candidate for candidate in group_ids if candidate != group_id]
            assignments[entry.id] = group_ids
        try:
            changed = self.group_service.assign_many(assignments)
        except (ValueError, VaultError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status(f"已更新 {changed} 条密码记录的分组。")

    def toggle_pinned(self) -> None:
        if not self._guard():
            return
        entries = self._selected_entries()
        if not entries:
            return
        pinned = not all(entry.pinned for entry in entries)
        try:
            self.service.set_pinned([entry.id for entry in entries], pinned)
        except VaultError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status("已置顶所选密码。" if pinned else "已取消置顶所选密码。")

    def set_pinned(self, pinned: bool) -> None:
        if not self._guard():
            return
        entries = self._selected_entries()
        if not entries:
            return
        try:
            self.service.set_pinned([entry.id for entry in entries], pinned)
        except VaultError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status("已置顶所选密码。" if pinned else "已取消置顶所选密码。")

    def toggle_pinned_for(self, entry_id: str) -> None:
        entry = next((item for item in self.app.vault.password_entries if item.id == entry_id), None)
        if entry is None or not self._guard():
            return
        try:
            self.service.set_pinned([entry.id], not entry.pinned)
        except VaultError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status("置顶状态已更新。")

    def toggle_favorite(self) -> None:
        entries = self._selected_entries()
        if entries:
            self.set_favorite(not all(entry.favorite for entry in entries))

    def set_favorite(self, favorite: bool) -> None:
        if not self._guard():
            return
        entries = self._selected_entries()
        if not entries:
            return
        try:
            self.service.set_favorite([entry.id for entry in entries], favorite)
        except VaultError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status("已收藏所选密码。" if favorite else "已取消收藏所选密码。")

    def toggle_favorite_for(self, entry_id: str) -> None:
        entry = next((item for item in self.app.vault.password_entries if item.id == entry_id), None)
        if entry is None or not self._guard():
            return
        try:
            self.service.set_favorite([entry.id], not entry.favorite)
        except VaultError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status("收藏状态已更新。")

    def toggle_show_pinned(self) -> None:
        self.app.settings.password_show_pinned = not self.app.settings.password_show_pinned
        self.view_model.set_show_pinned(self.app.settings.password_show_pinned)
        if self.workspace is not None:
            self.workspace.update_show_pinned_button(self.app.settings.password_show_pinned)
        try:
            self.app.settings_repository.save(self.app.settings)
        except VaultError:
            self.app._show_status("显示设置已应用，但无法保存。")
        self.refresh()

    def delete(self) -> None:
        if not self._guard():
            return
        entries = self._selected_entries()
        if not entries:
            return
        if not messagebox.askyesno(APP_NAME, f"确定删除所选 {len(entries)} 条密码记录吗？", parent=self.app):
            return
        self.conceal()
        try:
            deleted = self.service.delete([entry.id for entry in entries])
        except VaultError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return
        self.refresh()
        self.app._show_status(f"已删除 {deleted} 条密码记录。")

    def groups(self) -> list[PasswordGroup]:
        return list(self.app.vault.password_groups)

    def group_by_id(self, group_id: str) -> PasswordGroup | None:
        return self.app.vault.password_group_by_id(group_id)

    def group_entry_count(self, group_id: str) -> int:
        return sum(group_id in entry.group_ids for entry in self.app.vault.password_entries)

    def create_group(self, name: str | None = None) -> bool:
        if not self._guard():
            return False
        value = name or GroupNameDialog.ask(self.app, "新建密码分组")
        if not value:
            return False
        try:
            group = self.group_service.create(value)
        except (ValueError, VaultError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return False
        self.active_group_id = group.id
        self.view_model.set_scope(GroupScope(group.id, group.name))
        self.refresh()
        self.app._show_status(f"已创建密码分组“{group.name}”。")
        return True

    def rename_group(self, group_id: str, name: str) -> bool:
        try:
            group = self.group_service.rename(group_id, name)
        except (ValueError, VaultError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return False
        if isinstance(self.view_model.scope, GroupScope) and self.view_model.scope.group_id == group.id:
            self.view_model.set_scope(GroupScope(group.id, group.name))
        self.refresh()
        self.app._show_status(f"已将密码分组重命名为“{group.name}”。")
        return True

    def delete_group(self, group_id: str) -> bool:
        try:
            group = self.group_service.delete(group_id)
        except (ValueError, VaultError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self.app)
            return False
        if self.active_group_id == group_id:
            self.active_group_id = None
            self.view_model.set_scope(AllScope("全部密码"))
        self.refresh()
        self.app._show_status(f"已删除密码分组“{group.name}”。")
        return True

    def manage_groups(self) -> None:
        if self._guard():
            PasswordGroupManagerDialog.show(self.app, self)
