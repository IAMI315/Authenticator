"""Rendering-efficiency tests for Canvas, dashboard cards, and navigation."""

import time
import tkinter as tk
from collections.abc import Callable
from types import SimpleNamespace
from typing import TypeVar

from domain.entities import OTPEntry
from presentation.canvas_table import CanvasDataTable, ColumnSpec, TableRow
from presentation.compact_window import CompactAccountRow, CompactWindow
from presentation.dashboard_widgets import DashboardStatsView
from presentation.dpi import DpiContext
from presentation.glass_scrollbar import GlassScrollbar
from presentation.icon_registry import IconRegistry
from presentation.mixins.layout import LayoutMixin
from presentation.mixins.lifecycle import LifecycleMixin
from presentation.module_switch import OTP_FILL, PASSWORD_FILL, ModuleSegmentedSwitch
from presentation.navigation_sidebar import NavigationSidebar
from presentation.scheduling import TrailingDebouncer
from presentation.styles import center_dialog, configure_app_style
from presentation.view_models import AllScope, FavoriteScope, NavigationItem, OtpDashboardStats

_TkWindow = TypeVar("_TkWindow", bound=tk.Misc)


def _create_with_tcl_retry(factory: Callable[[], _TkWindow]) -> _TkWindow:
    # Windows 文件扫描器偶尔会在 Tcl 初始化读取脚本时短暂返回“文件不存在”。
    # 有限重试只处理这一瞬时初始化错误；安装缺失等持续问题仍会正常失败。
    for attempt in range(3):
        try:
            return factory()
        except tk.TclError as error:
            if "Can't find a usable" not in str(error) or attempt == 2:
                raise
            time.sleep(0.05)
    raise AssertionError("unreachable")


def _root() -> tk.Tk:
    root = _create_with_tcl_retry(tk.Tk)
    root.withdraw()
    root.geometry("960x520")
    return root


def test_canvas_virtualizes_rows_and_updates_visible_items_in_place():
    root = _root()
    try:
        table = CanvasDataTable(
            root,
            (
                ColumnSpec("service", "服务", 140),
                ColumnSpec("account", "账号", 260, weight=1),
                ColumnSpec("code", "验证码", 120),
                ColumnSpec("remaining", "剩余", 72),
            ),
            primary_column="code",
            service_column="service",
        )
        table.pack(fill="both", expand=True)
        root.update_idletasks()
        rows = [
            TableRow(
                str(index),
                {"service": "OpenAI", "account": f"user{index}@example.com", "code": "123456"},
                remaining_seconds=15,
                period=30,
            )
            for index in range(500)
        ]
        table.set_rows(rows)
        root.update_idletasks()

        assert 0 < len(table._rendered_ids) < 20
        visible_id = next(iter(table._rendered_ids))
        service_item = table._cell_items[(visible_id, "service")]
        code_item = table._cell_items[(visible_id, "code")]
        previous_code_text = table.body.itemcget(code_item, "text")
        changed = [
            TableRow(
                row.id,
                {**row.values, "code": "654321"},
                remaining_seconds=14,
                period=30,
            )
            for row in rows
        ]

        assert table.update_dynamic_rows(changed) is True
        assert table._cell_items[(visible_id, "service")] == service_item
        assert table.body.itemcget(code_item, "text") != previous_code_text
    finally:
        root.destroy()


def test_dashboard_updates_content_without_recreating_canvas_items():
    root = _root()
    try:
        view = DashboardStatsView(root, IconRegistry(root))
        view.pack(fill="x")
        root.update_idletasks()
        first = OtpDashboardStats(2, 2, 1, "TOTP", "单一类型")
        view.set_otp(first)
        root.update_idletasks()
        item_ids = [dict(card._items) for card in view.cards]

        view.set_otp(OtpDashboardStats(3, 3, 0, "TOTP", "单一类型"))
        root.update_idletasks()

        assert [dict(card._items) for card in view.cards] == item_ids
    finally:
        root.destroy()


def test_sidebar_restyles_active_item_without_rebuilding_controls():
    root = _root()
    try:
        query = tk.StringVar()
        sidebar = NavigationSidebar(root, IconRegistry(root), query, lambda _scope: None, lambda: None)
        sidebar.pack(fill="both", expand=True)
        all_scope = AllScope("全部账号")
        pinned_scope = FavoriteScope()
        items = (
            NavigationItem("all", "全部账号", 3, "folder", "primary", all_scope),
            NavigationItem("favorites", "收藏夹", 1, "star", "primary", pinned_scope),
        )
        sidebar.set_items(items, all_scope)
        original_frames = dict(sidebar._buttons)

        sidebar.set_items(items, pinned_scope)

        assert sidebar._buttons == original_frames
        assert sidebar.active_id == "favorites"
    finally:
        root.destroy()


def test_sidebar_collapse_reuses_controls_and_overflow_has_scrollbar():
    root = _root()
    try:
        root.geometry("230x260")
        query = tk.StringVar()
        sidebar = NavigationSidebar(root, IconRegistry(root), query, lambda _scope: None, lambda: None)
        sidebar.pack(fill="both", expand=True)
        scope = AllScope("全部账号")
        items = [NavigationItem("all", "全部账号", 20, "folder", "primary", scope)]
        items.extend(
            NavigationItem(f"provider-{index}", f"服务商 {index}", index, "grid", "providers", scope)
            for index in range(20)
        )
        sidebar.set_items(items, scope)
        root.update()
        original_frames = dict(sidebar._buttons)

        assert sidebar.list_scrollbar.grid_info()
        sidebar.set_collapsed(True)
        sidebar.set_collapsed(False)
        root.update()

        assert sidebar._buttons == original_frames
        assert sidebar.list_scrollbar.grid_info()
        assert sidebar.list_canvas.yview()[1] < 1.0
    finally:
        root.destroy()


def test_sidebar_toggle_always_changes_the_current_state():
    calls: list[bool] = []
    cancelled: list[bool] = []
    owner = SimpleNamespace(
        sidebar=SimpleNamespace(collapsed=True),
        _sidebar_user_override=None,
        _responsive_layout_signature=(120, True, True),
        _responsive_debouncer=SimpleNamespace(cancel=lambda: cancelled.append(True)),
        _apply_responsive_layout=lambda: calls.append(True),
    )

    LayoutMixin._toggle_sidebar(owner)

    assert owner._sidebar_user_override is False
    assert owner._responsive_layout_signature is None
    assert cancelled == [True]
    assert calls == [True]


def test_trailing_debouncer_coalesces_a_burst_without_repeated_timer_churn():
    root = _root()
    try:
        calls: list[bool] = []
        debouncer = TrailingDebouncer(root, 20, lambda: calls.append(True))

        for _index in range(100):
            debouncer.trigger()
        root.after(40, root.quit)
        root.mainloop()

        assert calls == [True]
        assert not debouncer.pending
    finally:
        root.destroy()


def test_hidden_table_defers_resize_work_until_reactivated():
    root = _root()
    try:
        table = CanvasDataTable(
            root,
            (ColumnSpec("service", "服务", 140), ColumnSpec("code", "验证码", 120)),
            primary_column="code",
            service_column="service",
        )
        table.pack(fill="both", expand=True)
        row = TableRow("one", {"service": "OpenAI", "code": "123456"})
        table.set_rows([row])
        root.update_idletasks()
        table.set_layout_active(False)

        table._on_resize(SimpleNamespace())
        table.update_rows([TableRow("one", {"service": "OpenAI", "code": "654321"})])

        assert table._resize_dirty
        assert not table._resize_debouncer.pending
        table.set_layout_active(True)
        assert not table._resize_dirty
        assert table._row_by_id["one"].values["code"] == "654321"
        assert table.body.itemcget(table._cell_items[("one", "code")], "text").startswith("6")
    finally:
        root.destroy()


def test_glass_scrollbar_is_arrowless_and_supports_dragging():
    root = _root()
    try:
        commands: list[tuple[object, ...]] = []
        scrollbar = GlassScrollbar(root, lambda *args: commands.append(args))
        scrollbar.pack(side="right", fill="y")
        root.deiconify()
        root.update()
        scrollbar.set(0.2, 0.5)
        root.update_idletasks()

        assert len(scrollbar.find_all()) == 2
        assert scrollbar.itemcget(scrollbar._thumb_item, "state") == "normal"
        midpoint = int((scrollbar._thumb_outer_top + scrollbar._thumb_outer_bottom) / 2)
        scrollbar._on_press(SimpleNamespace(y=midpoint))
        scrollbar._on_drag(SimpleNamespace(y=midpoint + 20))
        scrollbar._on_release(SimpleNamespace())

        assert commands and commands[-1][0] == "moveto"
        scrollbar.set(0.0, 1.0)
        assert scrollbar.itemcget(scrollbar._thumb_item, "state") == "hidden"
    finally:
        root.destroy()


def test_compact_account_slot_reuses_widgets_when_entry_changes():
    root = _root()
    try:
        owner = SimpleNamespace(copy_text=lambda _value, _message: None)
        row = CompactAccountRow(root, owner, DpiContext())
        row.pack(fill="x")
        first = OTPEntry.from_uri(
            "otpauth://totp/OpenAI:first@example.com?secret=JBSWY3DPEHPK3PXP&issuer=OpenAI"
        )
        second = OTPEntry.from_uri(
            "otpauth://totp/GitHub:second@example.com?secret=JBSWY3DPEHPK3PXP&issuer=GitHub"
        )
        account_label = row.account_label
        code_label = row.code_label

        row.set_entry(first, "123456")
        row.set_entry(second, "654321")

        assert row.account_label is account_label
        assert row.code_label is code_label
        assert row.provider_var.get() == "GitHub"
        assert row.code_var.get() == "654321"
    finally:
        root.destroy()


def test_compact_account_highlight_keeps_widgets_and_geometry_stable():
    root = _root()
    try:
        owner = SimpleNamespace(copy_text=lambda _value, _message: None)
        row = CompactAccountRow(root, owner, DpiContext())
        row.pack(fill="x")
        root.update_idletasks()
        account_label = row.account_label
        code_label = row.code_label
        height = row.winfo_height()

        row.set_highlighted(True)
        assert row.cget("highlightbackground") == "#2563EB"
        assert row.cget("highlightthickness") == 2
        root.update_idletasks()
        assert row.winfo_height() == height

        row.set_highlighted(False)
        assert row.cget("highlightbackground") == "#DCE3ED"
        assert row.account_label is account_label
        assert row.code_label is code_label
    finally:
        root.destroy()


def test_compact_window_lists_all_accounts_and_scrolls_past_two_rows():
    root = _root()
    compact: CompactWindow | None = None
    try:
        configure_app_style(root)
        entries = [
            OTPEntry.from_uri(
                f"otpauth://totp/Service{index}:user{index}@example.com"
                "?secret=JBSWY3DPEHPK3PXP"
            )
            for index in range(4)
        ]
        root.dpi_context = DpiContext()  # type: ignore[attr-defined]
        root.icons = IconRegistry(root)  # type: ignore[attr-defined]
        root.settings = SimpleNamespace(compact_clipboard="", otp_codes_visible=True)  # type: ignore[attr-defined]
        root.window_on_top = False  # type: ignore[attr-defined]
        root.locked = False  # type: ignore[attr-defined]
        root.search_var = tk.StringVar(master=root)  # type: ignore[attr-defined]
        root.compact_view_model = SimpleNamespace(recent_entries=lambda: entries)  # type: ignore[attr-defined]
        root.qr_scanner = SimpleNamespace()  # type: ignore[attr-defined]
        root.background_tasks = SimpleNamespace()  # type: ignore[attr-defined]
        root._sync_view_model = lambda: None  # type: ignore[attr-defined]
        root._menu_options = lambda: {"tearoff": False}  # type: ignore[attr-defined]
        root.toggle_always_on_top = lambda: None  # type: ignore[attr-defined]
        root.set_compact_mode = lambda *_args: None  # type: ignore[attr-defined]
        root._persist_settings = lambda: None  # type: ignore[attr-defined]

        compact = CompactWindow(root)
        compact.update()

        assert list(compact.account_rows) == [entry.id for entry in entries]
        assert compact.status_label.winfo_height() > 0
        assert compact.status_label.winfo_rooty() + compact.status_label.winfo_height() <= (
            compact.winfo_rooty() + compact.winfo_height()
        )
        viewport_bottom = compact.accounts_canvas.winfo_rooty() + compact.accounts_canvas.winfo_height()
        for entry in entries[:2]:
            row = compact.account_rows[entry.id]
            assert row.winfo_rooty() + row.winfo_height() <= viewport_bottom
        assert compact.accounts_canvas.yview()[1] < 1.0

        initial_position = compact.accounts_canvas.yview()[0]
        compact._on_accounts_mousewheel(SimpleNamespace(delta=-120, num=None))
        compact.update_idletasks()
        assert compact.accounts_canvas.yview()[0] > initial_position
    finally:
        if compact is not None:
            compact.destroy()
        root.destroy()


def test_compact_window_close_exits_instead_of_switching_to_full_window():
    calls: list[str] = []
    owner = SimpleNamespace(_shutdown=lambda: calls.append("shutdown"))

    CompactWindow._close_application(SimpleNamespace(app=owner))

    assert calls == ["shutdown"]


def test_compact_window_foreground_presentation_restores_topmost_preference():
    calls: list[tuple[object, ...]] = []
    delayed: list[Callable[[], None]] = []
    compact = SimpleNamespace(
        app=SimpleNamespace(window_on_top=False),
        deiconify=lambda: calls.append(("deiconify",)),
        attributes=lambda *args: calls.append(("attributes", *args)),
        lift=lambda: calls.append(("lift",)),
        focus_force=lambda: calls.append(("focus_force",)),
        winfo_exists=lambda: True,
        after=lambda _milliseconds, callback: delayed.append(callback),
    )

    CompactWindow.present_in_foreground(compact)  # type: ignore[arg-type]
    assert calls == [
        ("deiconify",),
        ("attributes", "-topmost", True),
        ("lift",),
        ("focus_force",),
    ]

    delayed[0]()
    assert calls[-2:] == [("attributes", "-topmost", False), ("lift",)]


def test_shutdown_persists_the_mode_that_was_visible_at_exit():
    persisted: list[bool] = []
    owner = SimpleNamespace(
        _closing=False,
        compact_mode=True,
        settings=SimpleNamespace(compact_mode=False),
        _window_size_debouncer=SimpleNamespace(cancel=lambda: None),
        _responsive_debouncer=SimpleNamespace(cancel=lambda: None),
        _persist_settings=lambda: persisted.append(owner.settings.compact_mode),
        _save_window_size=lambda force=False: None,
        api_controller=None,
        ssh_sessions=SimpleNamespace(close_all=lambda: None),
        background_tasks=SimpleNamespace(close=lambda: None),
        destroy=lambda: None,
    )

    LifecycleMixin._shutdown(owner)

    assert persisted == [True]


def test_module_segmented_switch_uses_one_control_and_distinct_active_colors():
    root = _root()
    try:
        selected: list[str] = []
        switch = ModuleSegmentedSwitch(root, selected.append, DpiContext())
        switch.pack()
        root.update_idletasks()

        selection_id = switch.find_withtag("selection")[0]
        assert switch.active == "otp"
        assert switch.itemcget(selection_id, "fill") == OTP_FILL
        assert switch.winfo_reqwidth() == DpiContext().dp(178)

        switch._activate("passwords")
        assert selected == ["passwords"]
        switch.set_active("passwords")
        selection_id = switch.find_withtag("selection")[0]
        assert switch.itemcget(selection_id, "fill") == PASSWORD_FILL

        switch._toggle_from_keyboard(SimpleNamespace())
        assert selected == ["passwords", "otp"]
        switch.set_active("otp")
        selection_id = switch.find_withtag("selection")[0]
        assert switch.itemcget(selection_id, "fill") == OTP_FILL
    finally:
        root.destroy()


def test_main_header_places_brand_switch_and_actions_on_one_row(tmp_path):
    from presentation.main_window import MainWindow

    window = _create_with_tcl_retry(lambda: MainWindow(data_directory=tmp_path))
    try:
        assert window.header_brand.grid_info()["row"] == 0
        assert window.module_switch.grid_info()["row"] == 0
        assert window.header_actions.grid_info()["row"] == 0
        assert window.module_switch.grid_info()["column"] > window.header_actions.grid_info()["column"]
        assert window.module_coordinator.module_switch is window.module_switch
        assert "vault_lock" in window.toolbar_buttons
        assert "lock" not in window.toolbar_buttons
        assert "unlock" not in window.toolbar_buttons

        window.locked = True
        window._update_vault_lock_button()
        assert window.vault_lock_button.cget("style") == "VaultLocked.TButton"
        assert getattr(window.vault_lock_button, "_icon_key") == "lock"

        window.locked = False
        window._update_vault_lock_button()
        assert window.vault_lock_button.cget("style") == "VaultUnlocked.TButton"
        assert getattr(window.vault_lock_button, "_icon_key") == "unlock"
    finally:
        window.destroy()


def test_combined_vault_button_dispatches_action_from_current_state():
    actions: list[str] = []
    owner = SimpleNamespace(
        locked=False,
        lock_vault=lambda: actions.append("lock"),
        unlock_vault=lambda: actions.append("unlock"),
    )

    LayoutMixin._toggle_vault_lock(owner)
    owner.locked = True
    LayoutMixin._toggle_vault_lock(owner)

    assert actions == ["lock", "unlock"]


def test_dialog_centers_on_visible_parent_window():
    root = _root()
    dialog = tk.Toplevel(root)
    try:
        root.geometry("800x500+160+120")
        root.deiconify()
        root.update_idletasks()
        dialog.geometry("240x120")
        center_dialog(dialog, root)
        root.update_idletasks()
        dialog.update_idletasks()

        expected_x = root.winfo_rootx() + (root.winfo_width() - dialog.winfo_width()) // 2
        expected_y = root.winfo_rooty() + (root.winfo_height() - dialog.winfo_height()) // 2
        assert abs(dialog.winfo_rootx() - expected_x) <= 1
        assert abs(dialog.winfo_rooty() - expected_y) <= 1
    finally:
        dialog.destroy()
        root.destroy()
