"""分组相关 UI 操作和服务持久化回调。"""

from __future__ import annotations

from tkinter import messagebox

from domain.entities import DEFAULT_GROUP_ID, DEFAULT_GROUP_NAME
from domain.identifiers import normalise_issuer_name
from infrastructure.errors import VaultError
from presentation.constants import APP_NAME
from presentation.dialogs import GroupAssignmentDialog, GroupManagerDialog, GroupNameDialog
from presentation.mixins.base import WindowMixin
from presentation.view_models import AllScope, GroupScope


class GroupActionsMixin(WindowMixin):
    """将分组对话框操作委托给 ``GroupService``，并维护 UI 状态/提示。"""

    def _persist_vault(self) -> None:
        """无 UI 地保存当前保险库，供应用服务在事务中调用。

        服务层依赖此回调以便保存失败后恢复内存快照；UI 事件会捕获 ``VaultError``
        并在各自交互流程中显示对应提示。
        """

        self.vault_repository.save(self.vault)

    def _persist_settings(self) -> None:
        """分别保存公开偏好和加密敏感设置。"""

        if not getattr(self, "_vault_loaded", False):
            return
        if self.settings.secure_dirty:
            secure_values = self.settings.secure_values()
            previous_values = dict(self.vault.secure_settings)
            self.vault.secure_settings = secure_values
            try:
                self.vault_repository.save(self.vault)
            except Exception:
                self.vault.secure_settings = previous_values
                raise
            self.settings.apply_secure_values(secure_values)
        self.settings_repository.save(self.settings)

    def _remember_last_issuer(self, issuer: str) -> bool:
        """保存最近使用的服务商；保存失败时恢复旧值并返回 ``False``。"""

        issuer = normalise_issuer_name(issuer)
        previous_issuer = self.settings.last_issuer
        if not issuer or issuer == previous_issuer:
            return True
        self.settings.last_issuer = issuer
        try:
            self._persist_settings()
        except VaultError:
            self.settings.last_issuer = previous_issuer
            return False
        return True

    def create_group(self, name: str | None = None) -> bool:
        """弹出名称对话框（或使用传入名称）创建分组，并将其设为活动分组。"""

        if not self._guard_unlocked():
            return False
        if name is None:
            name = GroupNameDialog.ask(self, "新建分组")
        if name is None:
            return False
        try:
            group = self.group_service.create(name)
        except (VaultError, ValueError) as error:
            messagebox.showwarning(APP_NAME, str(error), parent=self)
            return False
        self.active_group_id = group.id
        self.main_view_model.set_scope(GroupScope(group.id, group.name))
        self.refresh_tree()
        self._show_status(f"已新建分组“{group.name}”。")
        return True

    def rename_group(self, group_id: str, name: str) -> bool:
        """重命名指定自定义分组；默认分组在 UI 和服务层都被拒绝。"""

        if not self._guard_unlocked():
            return False
        group = self.vault.group_by_id(group_id)
        if group is None or group.id == DEFAULT_GROUP_ID:
            self._show_status("默认分组不能重命名。")
            return False
        try:
            renamed = self.group_service.rename(group_id, name)
        except (VaultError, ValueError) as error:
            messagebox.showwarning(APP_NAME, str(error), parent=self)
            return False
        if self.active_group_id == group_id:
            self.main_view_model.set_scope(GroupScope(renamed.id, renamed.name))
        self.refresh_tree()
        self._show_status(f"已将分组重命名为“{renamed.name}”。")
        return True

    def delete_group(self, group_id: str) -> bool:
        """确认后删除自定义分组，若它是活动分组则回退到全部账号。"""

        if not self._guard_unlocked():
            return False
        group = self.vault.group_by_id(group_id)
        if group is None or group.id == DEFAULT_GROUP_ID:
            self._show_status("默认分组不能删除。")
            return False
        if not messagebox.askyesno(APP_NAME, f"确定删除分组“{group.name}”吗？", parent=self):
            return False
        try:
            deleted = self.group_service.delete(group_id)
        except (VaultError, ValueError) as error:
            messagebox.showwarning(APP_NAME, str(error), parent=self)
            return False
        if self.active_group_id == group_id:
            self.active_group_id = None
            self.main_view_model.set_scope(AllScope(self.main_view_model.all_accounts_label))
        self.refresh_tree()
        self._show_status(f"已删除分组“{deleted.name}”，账号仍保留在“{DEFAULT_GROUP_NAME}”。")
        return True

    def manage_groups(self) -> None:
        """打开分组管理对话框，并注入 UI 控制器操作回调。"""

        if not self._guard_unlocked():
            return
        GroupManagerDialog.show(
            self,
            self.vault,
            self._group_entry_count,
            self.create_group,
            self.rename_group,
            self.delete_group,
        )

    def assign_selected_groups(self) -> None:
        """收集多选账号的成员变更，并作为一次批量事务交给分组服务。"""

        if not self._guard_unlocked():
            return
        entries = self._selected_entries()
        if not entries:
            self._show_status("请先选择一个或多个账号。")
            return
        changes = GroupAssignmentDialog.ask(self, self.vault.groups, entries)
        if changes is None:
            return
        if not changes:
            self._show_status("未修改账号分组。")
            return
        # 对话框只返回被用户实际切换的分组，保留每个账号其他未变更归属。
        assignments: dict[str, list[str]] = {}
        for entry in entries:
            group_ids = list(entry.group_ids)
            for group_id, should_include in changes.items():
                if should_include and group_id not in group_ids:
                    group_ids.append(group_id)
                elif not should_include:
                    group_ids = [candidate for candidate in group_ids if candidate != group_id]
            assignments[entry.id] = group_ids
        try:
            self.group_service.assign_many(assignments)
        except (VaultError, ValueError) as error:
            messagebox.showwarning(APP_NAME, str(error), parent=self)
            return
        self.refresh_tree()
        self._show_status(f"已更新 {len(entries)} 个账号的分组。")
