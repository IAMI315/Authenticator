"""账号新增、编辑、复制、HOTP、置顶和删除等 UI 操作控制。"""

from __future__ import annotations

from tkinter import messagebox
from typing import Any

from application.import_export import QrImportPayload
from domain.entities import OTPEntry
from domain.errors import DuplicateAccountError
from domain.identifiers import account_identity, unique_issuer_names
from infrastructure.errors import VaultError
from presentation.constants import APP_NAME
from presentation.dialogs import EntryDialog
from presentation.mixins.base import WindowMixin


class AccountActionsMixin(WindowMixin):
    """把账号对话框/扫码结果连接到 ``AccountService`` 的用户交互控制器。"""

    def _store_new_entry(self, entry: OTPEntry) -> bool:
        """通过应用服务新增账号并刷新 UI；返回是否成功写入保险库。"""

        try:
            self.account_service.create(entry, active_group_id=self.active_group_id)
        except DuplicateAccountError as error:
            self._show_status(str(error))
            return False
        except (VaultError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return False
        saved_last_issuer = self._remember_last_issuer(entry.issuer)
        self.refresh_tree()
        if self.compact_window is not None:
            self.compact_window.refresh()
        if not saved_last_issuer:
            self._show_status("账号已新增，但未能保存“上次使用的服务商”。")
        return True

    def add_scanned_account(self, entry: OTPEntry) -> bool:
        """处理扫码得到的实体，先显示重复提示，再复用标准新增事务。"""

        if not self._guard_unlocked():
            return False
        duplicate = next(
            (existing for existing in self.vault.entries if account_identity(existing) == account_identity(entry)),
            None,
        )
        if duplicate is not None:
            self._show_status(f"账号已存在：{duplicate.title} · {duplicate.account}")
            if self.compact_window is not None:
                self.compact_window.status_var.set("账号已存在")
            return False
        if self._store_new_entry(entry):
            self._show_status(f"已扫码新增 {entry.title} · {entry.account}。")
            if self.compact_window is not None:
                self.compact_window.status_var.set("扫码成功，账号已添加")
                self.compact_window.highlight_accounts([entry.id])
            return True
        return False

    def add_scanned_payload(self, payload: QrImportPayload) -> bool:
        """Route a single OTP QR or Google migration batch through shared services."""

        if not self._guard_unlocked():
            return False
        if payload.source == "otpauth" and len(payload.bundle.otp_entries) == 1:
            return self.add_scanned_account(payload.bundle.otp_entries[0])
        existing_ids = {entry.id for entry in self.vault.entries}
        result = self._add_imported_entries(payload.bundle)
        if result is None:
            return False
        batch_note = ""
        if payload.batch_size > 1:
            batch_note = f"（第 {payload.batch_index + 1}/{payload.batch_size} 张）"
        feedback = (
            f"Google 导入完成：新增 {result.accounts_added} 个账号，"
            f"跳过 {result.duplicates_skipped} 个重复账号{batch_note}。"
        )
        self._show_status(feedback, clear_after=10_000)
        if self.compact_window is not None:
            self.compact_window.status_var.set(feedback)
            added_ids = [entry.id for entry in self.vault.entries if entry.id not in existing_ids]
            if added_ids:
                self.compact_window.highlight_accounts(added_ids)
        return True

    def add_account(self, from_compact: bool = False) -> None:
        """打开手动新增对话框；轻量窗口调用时以其作为模态父窗口。"""

        if not self._guard_unlocked():
            return
        dialog_parent: Any = self.compact_window if from_compact and self.compact_window is not None else self
        entry = EntryDialog.ask(
            dialog_parent,
            issuer_options=unique_issuer_names(self.vault.entries),
            default_issuer=self.settings.last_issuer,
        )
        if not entry:
            return
        if self._store_new_entry(entry):
            self.tree.selection_set(entry.id)
            self.tree.set_focus(entry.id)
            group_note = f"，并加入“{self._active_group_name()}”" if self.active_group_id is not None else ""
            self._show_status(f"已新增 {entry.title}{group_note}。")

    def edit_selected(self) -> None:
        """编辑单选账号，并由 ``AccountService`` 处理唯一性和保存回滚。"""

        if not self._guard_unlocked():
            return
        entry = self._selected_entry()
        if not entry:
            self._show_status("请先选择一个账号。")
            return
        changed = EntryDialog.ask(self, entry, issuer_options=unique_issuer_names(self.vault.entries))
        if not changed:
            return
        try:
            self.account_service.update(changed)
        except DuplicateAccountError as error:
            self._show_status(str(error))
            return
        except (VaultError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.refresh_tree()
        self.tree.selection_set(changed.id)
        self.tree.set_focus(changed.id)
        self._show_status(f"已更新 {changed.title}。")

    def copy_selected(self) -> None:
        """计算并复制单选账号的当前验证码；无效密钥显示领域错误。"""

        if not self._guard_unlocked():
            return
        entry = self._selected_entry()
        if not entry:
            self._show_status("请先选择一个账号。")
            return
        try:
            code = entry.code()
        except ValueError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        self._show_status(f"已复制 {entry.title} 的验证码。")

    def next_hotp(self) -> None:
        """对单选 HOTP 账号递增计数器并保存，随后保留其 Treeview 选择。"""

        if not self._guard_unlocked():
            return
        entry = self._selected_entry()
        if not entry:
            self._show_status("请先选择一个 HOTP 账号。")
            return
        if entry.otp_type != "hotp":
            self._show_status("只有基于计数器的账号可以生成下一个 HOTP。")
            return
        try:
            updated = self.account_service.increment_hotp(entry.id)
        except (VaultError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.refresh_tree()
        self.tree.selection_set(updated.id)
        self._show_status(f"已将 {updated.title} 的计数器更新为 {updated.counter}。")

    def set_selected_favorite(self, favorite: bool) -> None:
        if not self._guard_unlocked():
            return
        entries = self._selected_entries()
        if not entries:
            self._show_status("请先选择账号。")
            return
        try:
            self.account_service.set_favorite([entry.id for entry in entries], favorite)
        except (VaultError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.refresh_tree()
        self._show_status(f"已{'收藏' if favorite else '取消收藏'} {len(entries)} 个账号。")

    def toggle_favorite(self, account_id: str | None = None) -> None:
        entry = next((item for item in self.vault.entries if item.id == account_id), None) if account_id else None
        if entry is not None:
            if not self._guard_unlocked():
                return
            try:
                self.account_service.set_favorite([entry.id], not entry.favorite)
            except (VaultError, ValueError) as error:
                messagebox.showerror(APP_NAME, str(error), parent=self)
                return
            self.refresh_tree()
            self._show_status(f"已{'收藏' if entry.favorite else '取消收藏'} {entry.title}。")
            return
        if entry is None:
            entries = self._selected_entries()
            if len(entries) != 1:
                self._show_status("请只选择一个账号。")
                return
            entry = entries[0]
        self.set_selected_favorite(not entry.favorite)

    def set_selected_pinned(self, pinned: bool) -> None:
        if not self._guard_unlocked():
            return
        entries = self._selected_entries()
        if not entries:
            self._show_status("请先选择账号。")
            return
        try:
            self.account_service.set_pinned([entry.id for entry in entries], pinned)
        except (VaultError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.refresh_tree()
        self._show_status(f"已{'置顶' if pinned else '取消置顶'} {len(entries)} 个账号。")

    def toggle_pin(self, account_id: str | None = None) -> None:
        """Toggle one row icon, or all selected accounts when invoked from a menu."""

        if not self._guard_unlocked():
            return
        entry = next((item for item in self.vault.entries if item.id == account_id), None) if account_id else None
        entries = [entry] if entry is not None else self._selected_entries()
        if not entries:
            self._show_status("请先选择账号。")
            return
        pinned = not all(item.pinned for item in entries)
        if entry is not None:
            try:
                self.account_service.set_pinned([entry.id], pinned)
            except (VaultError, ValueError) as error:
                messagebox.showerror(APP_NAME, str(error), parent=self)
                return
            self.refresh_tree()
            self._show_status(f"已{'置顶' if pinned else '取消置顶'} {entry.title}。")
            return
        self.set_selected_pinned(pinned)

    def delete_selected(self) -> None:
        """确认后删除单选账号；删除不可撤销，因此必须在 UI 层二次确认。"""

        if not self._guard_unlocked():
            return
        entries = self._selected_entries()
        if not entries:
            self._show_status("请先选择账号。")
            return
        if not messagebox.askyesno(APP_NAME, f"确定删除所选 {len(entries)} 个账号吗？此操作无法撤销。", parent=self):
            return
        try:
            deleted = self.account_service.delete([entry.id for entry in entries])
        except (VaultError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.refresh_tree()
        self._show_status(f"已删除 {deleted} 个账号。")
