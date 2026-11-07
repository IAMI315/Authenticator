"""OTP Canvas-table filtering, rendering and selection state."""

from __future__ import annotations

import time
import tkinter as tk
from typing import Any

from application.sorting import OtpSortField, OtpSortSpec, SortDirection
from domain.entities import OTPEntry
from infrastructure.errors import VaultError
from presentation.canvas_table import TableRow
from presentation.mixins.base import WindowMixin
from presentation.view_models import AllScope, GroupScope


class AccountListMixin(WindowMixin):
    _search_after_id: str | None
    active_group_id: str | None

    def _schedule_search(self, *_args: Any) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after_idle(self._apply_search)

    def _apply_search(self) -> None:
        self._search_after_id = None
        self.refresh_tree()

    def _on_otp_sort(self, column_key: str) -> None:
        try:
            field = OtpSortField(column_key)
        except ValueError:
            return
        current = self.main_view_model.sort_spec
        if current.field is field:
            direction = (
                SortDirection.DESCENDING
                if current.direction is SortDirection.ASCENDING
                else SortDirection.ASCENDING
            )
        else:
            direction = (
                SortDirection.DESCENDING
                if field is OtpSortField.CREATED
                else SortDirection.ASCENDING
            )
        spec = OtpSortSpec(field, direction)
        self.main_view_model.set_sort(spec)
        self.settings.otp_sort_field = field.value
        self.settings.otp_sort_direction = direction.value
        self.otp_table.set_sort_state(field.value, direction.value)
        try:
            self.settings_repository.save(self.settings)
        except VaultError:
            self._show_status("排序已应用，但无法保存排序设置。")
        self.refresh_tree()
        self.otp_table.restore_scroll(0.0)

    def focus_search(self, _event: tk.Event[Any] | None = None) -> str:
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"

    def _clear_search_event(self, _event: tk.Event[Any]) -> str:
        self.clear_search()
        return "break"

    def _refresh_group_selector(self) -> None:
        scope = self.main_view_model.scope
        if isinstance(scope, GroupScope) and self.vault.group_by_id(scope.group_id) is None:
            self.main_view_model.set_scope(AllScope(self.main_view_model.all_accounts_label))
        self.active_group_id = (
            self.main_view_model.scope.group_id
            if isinstance(self.main_view_model.scope, GroupScope)
            else None
        )

    def _active_group_name(self) -> str:
        return self.main_view_model.active_group_name()

    def _group_entry_count(self, group_id: str) -> int:
        return sum(group_id in entry.group_ids for entry in self.vault.entries)

    def _selected_entry(self) -> OTPEntry | None:
        entries = self._selected_entries()
        return entries[0] if len(entries) == 1 else None

    def _selected_entries(self) -> list[OTPEntry]:
        selected_ids = set(self.otp_table.selection())
        return [entry for entry in self.vault.entries if entry.id in selected_ids]

    def _visible_entries(self) -> list[OTPEntry]:
        self._sync_view_model()
        return self.main_view_model.visible_entries()

    def _sync_view_model(self) -> None:
        self.main_view_model.update_state(
            query=self.search_var.get(),
            active_group_id=self.active_group_id,
            locked=self.locked,
            scope=self.main_view_model.scope,
        )

    def _table_row(self, entry: OTPEntry, now: float) -> TableRow:
        row = self._row_presenter.row(entry, now)
        return TableRow(
            id=entry.id,
            values={
                "service": row.service,
                "account": row.account,
                "code": row.code if self.settings.otp_codes_visible or "invalid" in row.tags else "••••••",
                "remaining": row.expires,
                "type": row.entry_type,
                "created": row.created_at,
            },
            favorite=entry.favorite,
            pinned=entry.pinned,
            invalid="invalid" in row.tags,
            remaining_seconds=row.remaining_seconds,
            period=row.period,
            icon_key=row.icon_key or row.service,
            tags=row.tags,
        )

    def refresh_tree(self) -> None:
        if not hasattr(self, "otp_table"):
            return
        if self._mui_surface_active():
            # MUI owns rendering and will request a fresh service snapshot.
            # Rebuilding the hidden Canvas tree on every model change causes
            # needless layout work during WebView-backed operation.
            return
        self._refresh_group_selector()
        self._sync_view_model()
        self._code_cache.clear()
        self._displayed_entries = []
        selected_ids = self.otp_table.selection()
        scroll_fraction = self.otp_table.scroll_fraction()

        self.security_var.set(
            self.main_view_model.security_summary(
                self.vault.encrypted,
                self.settings.autolock_minutes,
            )
        )
        if self.locked:
            self.result_summary_var.set(self.main_view_model.result_summary())
            self.detail_var.set("解锁保险库后即可查看账号。")
            self.otp_table.set_rows((), empty_message="保险库已锁定，解锁后查看账号。")
            self.otp_table.set_locked(True)
            for widget in self.action_widgets:
                widget.configure(state="disabled")
            self.vault_lock_button.configure(state="normal")
        else:
            for widget in self.action_widgets:
                widget.configure(state="normal")
            self.vault_lock_button.configure(state="normal" if self.vault.encrypted else "disabled")
            visible_entries = self._visible_entries()
            self._displayed_entries = visible_entries
            self.result_summary_var.set(self.main_view_model.result_summary(len(visible_entries)))
            if not visible_entries:
                if self.search_var.get().strip():
                    message = "没有符合搜索条件的账号。"
                elif not isinstance(self.main_view_model.scope, AllScope):
                    message = f"“{self.main_view_model.scope.label}”中暂无账号。"
                else:
                    message = "暂无账号。请新增账号或导入。"
                self.detail_var.set("可手动新增账号，或导入 otpauth URI。")
            else:
                message = ""
            now = time.time()
            self.otp_table.set_rows(
                [self._table_row(entry, now) for entry in visible_entries],
                empty_message=message,
            )
            self.otp_table.set_locked(False)
            retained = [entry_id for entry_id in selected_ids if self.otp_table.exists(entry_id)]
            if retained:
                self.otp_table.selection_set(retained)
                self.otp_table.set_focus(retained[0])
            self.otp_table.restore_scroll(scroll_fraction)

        self._update_vault_lock_button()
        self._update_otp_action_states()

        if self.compact_window is not None:
            self.compact_window.refresh()
        if hasattr(self, "module_coordinator"):
            self.module_coordinator.refresh_passwords()
            self.module_coordinator.refresh_server()
        self._refresh_dashboard_shell()

    def _update_visible_rows(self) -> None:
        if not hasattr(self, "otp_table") or self.locked:
            return
        now = time.time()
        self.otp_table.update_dynamic_rows(
            [self._table_row(entry, now) for entry in self._displayed_entries]
        )
        if self.module_coordinator.active == "otp":
            self.stats_view.set_otp(self.main_view_model.dashboard_stats(now))
        elif self.module_coordinator.active == "passwords":
            self.stats_view.set_passwords(self.password_view_model.dashboard_stats())
        if self.compact_window is not None:
            self.compact_window.refresh()

    def clear_search(self) -> None:
        self.search_var.set("")
        self.search_entry.focus_set()

    def _on_selection(self) -> None:
        entries = self._selected_entries()
        if not entries:
            self.detail_var.set("选择一个账号以复制、编辑或导出 URI。")
            self._update_otp_action_states()
            return
        if len(entries) > 1:
            self.detail_var.set(f"已选择 {len(entries)} 个账号，可批量调整分组。")
            self._update_otp_action_states()
            return
        entry = entries[0]
        detail = entry.type_label
        detail += f" | 计数器 {entry.counter}" if entry.otp_type == "hotp" else f" | 每 {entry.period} 秒更新"
        self.detail_var.set(detail)
        self._update_otp_action_states()

    def _update_otp_action_states(self) -> None:
        if not hasattr(self, "otp_footer_buttons"):
            return
        entries = self._selected_entries()
        count = len(entries)
        single = count == 1 and not self.locked
        multiple = count > 0 and not self.locked
        states = {
            "copy": single,
            "edit": single,
            "group": multiple,
            "hotp": single and entries[0].otp_type == "hotp",
            "uri": single,
            "delete": multiple,
        }
        for key, enabled in states.items():
            self.otp_footer_buttons[key].configure(state="normal" if enabled else "disabled")
        self.otp_footer_more.configure(state="normal" if multiple else "disabled")

    def toggle_otp_show_pinned(self) -> None:
        self.settings.otp_show_pinned = not self.settings.otp_show_pinned
        self.main_view_model.set_show_pinned(self.settings.otp_show_pinned)
        self._update_otp_show_pinned_button()
        try:
            self.settings_repository.save(self.settings)
        except VaultError:
            self._show_status("显示设置已应用，但无法保存。")
        self.refresh_tree()

    def _update_otp_show_pinned_button(self) -> None:
        if not hasattr(self, "otp_show_pinned_button"):
            return
        visible = self.settings.otp_show_pinned
        self.otp_show_pinned_button.configure(
            text="置顶可见",
            style="ModuleActive.TButton" if visible else "ModuleInactive.TButton",
        )

    def _on_double_click(self, _event: tk.Event[Any] | None = None) -> None:
        self.copy_selected()

    def _select_all_visible(self, _event: tk.Event[Any] | None = None) -> str:
        self.otp_table.selection_set([entry.id for entry in self._displayed_entries])
        return "break"

    def _extend_selection(self, direction: int) -> str:
        return self.otp_table._move_focus(direction, True)

    def _toggle_focused_selection(self, _event: tk.Event[Any] | None = None) -> str:
        return self.otp_table._toggle_focus_event()

    def _show_context_menu(self, event: tk.Event[Any]) -> None:
        row_id = self.otp_table.identify_row(event.y)
        if row_id:
            if row_id not in self.otp_table.selection():
                self.otp_table.selection_set(row_id)
            self.context_menu.tk_popup(event.x_root, event.y_root)
