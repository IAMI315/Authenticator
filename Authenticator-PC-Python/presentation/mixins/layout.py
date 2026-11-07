"""Reference-dashboard main-window layout and responsive presentation shell."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from presentation.application_icon import set_window_icon
from presentation.canvas_table import CanvasDataTable, ColumnSpec, RowAction
from presentation.constants import APP_NAME
from presentation.dashboard_widgets import DashboardStatsView
from presentation.icon_registry import IconRegistry
from presentation.mixins.base import WindowMixin
from presentation.module_switch import ModuleSegmentedSwitch
from presentation.navigation_sidebar import NavigationSidebar
from presentation.password_workspace import PasswordWorkspace
from presentation.scheduling import TrailingDebouncer
from presentation.styles import (
    GLASS_SURFACE,
    SELECTION,
    TEXT_PRIMARY,
    UI_FONT,
    configure_app_style,
)
from presentation.tooltip import Tooltip
from presentation.view_models import NavigationScope


class LayoutMixin(WindowMixin):
    """Build the application chrome while delegating all data changes to controllers."""

    def _configure_style(self) -> None:
        configure_app_style(self, self.dpi_context)

    def _set_icon(self) -> None:
        set_window_icon(self, default=True)

    def _build_menu(self) -> None:
        """Create only popup menus; the native application menu bar is intentionally removed."""

        self.configure(menu="")
        menu_options = self._menu_options()
        self.more_menu = tk.Menu(self, **menu_options)
        self.more_menu.add_command(label="导入备份...", command=self.import_file)
        self.more_menu.add_command(label="导出加密备份...", command=self.export_encrypted_backup)
        self.more_menu.add_command(label="导出明文 JSON...", command=self.export_plain_backup)
        self.more_menu.add_separator()
        self.more_menu.add_command(label="粘贴 otpauth URI...", command=self.import_text)
        self.more_menu.add_command(label="导出 otpauth URI...", command=self.export_uris)
        self.more_menu.add_command(
            label="导出到 Google Authenticator...",
            command=self.export_google_authenticator_qr,
        )
        self.more_menu.add_separator()
        self.more_menu.add_command(label="修改主密码...", command=self.set_password)
        self.more_menu.add_command(label="设置...", command=self.open_settings)
        self.more_menu.add_separator()
        self.more_menu.add_command(label="本机 API 说明", command=self.show_api_help)
        self.more_menu.add_command(label="关于", command=self.show_about)
        self.more_menu.add_command(label="退出", command=self._shutdown)

        self.otp_action_menu = tk.Menu(self, **menu_options)
        self.otp_action_menu.add_command(label="收藏", command=lambda: self.set_selected_favorite(True))
        self.otp_action_menu.add_command(label="取消收藏", command=lambda: self.set_selected_favorite(False))
        self.otp_action_menu.add_command(label="置顶", command=lambda: self.set_selected_pinned(True))
        self.otp_action_menu.add_command(label="取消置顶", command=lambda: self.set_selected_pinned(False))
        self.otp_action_menu.add_separator()
        self.otp_action_menu.add_command(label="查看 URI", command=self.show_uri)
        self.otp_action_menu.add_separator()
        self.otp_action_menu.add_command(label="删除", command=self.delete_selected)

        self.export_menu = tk.Menu(self, **menu_options)
        self.export_menu.add_command(label="加密备份（推荐）", command=self.export_encrypted_backup)
        self.export_menu.add_command(label="明文 JSON...", command=self.export_plain_backup)
        self.export_menu.add_separator()
        self.export_menu.add_command(
            label="Google Authenticator 二维码...",
            command=self.export_google_authenticator_qr,
        )

    @staticmethod
    def _menu_options() -> dict[str, Any]:
        return {
            "tearoff": False,
            "background": GLASS_SURFACE,
            "foreground": TEXT_PRIMARY,
            "activebackground": SELECTION,
            "activeforeground": TEXT_PRIMARY,
            "borderwidth": 0,
            "activeborderwidth": 0,
            "font": (UI_FONT, 9),
        }

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Any,
        action: bool = True,
        style: str = "Secondary.TButton",
        *,
        icon: str | None = None,
        tooltip: str | None = None,
    ) -> ttk.Button:
        image = self.icons.image(icon, 18, "#FFFFFF" if style == "Primary.TButton" else None) if icon else None
        button = ttk.Button(
            parent,
            text=text,
            image=image,
            compound="left",
            command=command,
            style=style,
            width=self._button_text_width(text),
        )
        if image is not None:
            self._toolbar_images.append(image)
            setattr(button, "_icon_key", icon)
            setattr(button, "_icon_tint", "#FFFFFF" if style == "Primary.TButton" else None)
        if action:
            self.action_widgets.append(button)
        if tooltip:
            self._tooltips.append(Tooltip(button, tooltip))
        return button

    @staticmethod
    def _button_text_width(text: str) -> int:
        """Return a compact ttk width that still accommodates CJK labels."""

        return max(3, sum(2 if ord(character) > 127 else 1 for character in text) + 2)

    def _build_widgets(self) -> None:
        self.icons = IconRegistry(self, self.dpi_context)
        self._toolbar_images: list[Any] = []
        self._tooltips: list[Tooltip] = []
        self._sidebar_user_override: bool | None = None
        self._responsive_layout_signature: tuple[int, bool, bool] | None = None
        self._responsive_debouncer = TrailingDebouncer(self, 160, self._apply_responsive_layout)

        header = ttk.Frame(self, style="Header.TFrame", padding=(20, 13, 20, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        self.header_frame = header
        brand = ttk.Frame(header, style="Header.TFrame")
        brand.grid(row=0, column=0, sticky="w")
        self.header_brand = brand
        brand_icon = self.icons.image("app", 38)
        self._toolbar_images.append(brand_icon)
        self.brand_icon_label = ttk.Label(brand, image=brand_icon, style="HeaderIcon.TLabel")
        self.brand_icon_label.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        ttk.Label(brand, text=APP_NAME, style="HeaderTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(brand, textvariable=self.security_var, style="HeaderSub.TLabel").grid(row=1, column=1, sticky="w", pady=(2, 0))

        self.module_switch = ModuleSegmentedSwitch(
            header,
            self.module_coordinator.switch,
            self.dpi_context,
        )
        self.module_switch.grid(row=0, column=2, padx=(16, 0), sticky="e")

        actions = ttk.Frame(header, style="Header.TFrame")
        actions.grid(row=0, column=1, sticky="e")
        self.header_actions = actions
        self.toolbar_buttons: dict[str, ttk.Button] = {}
        specs = (
            ("add", "新增", self.module_coordinator.add_item, True, "Primary.TButton", "add"),
            ("import", "导入", self.import_file, True, "HeaderAction.TButton", "import"),
            ("export", "导出", self._show_export_menu, True, "HeaderAction.TButton", "export"),
            ("compact", "轻量模式", lambda: self.set_compact_mode(True), True, "HeaderAction.TButton", "compact"),
        )
        for column, (key, text, command, action, style, icon) in enumerate(specs):
            button = self._button(actions, text, command, action, style, icon=icon, tooltip=text)
            button.grid(row=0, column=column, padx=3)
            self.toolbar_buttons[key] = button
        self.topmost_button = self._button(
            actions,
            "置顶",
            self.toggle_always_on_top,
            action=False,
            style="TopmostOff.TButton",
            icon="topmost",
            tooltip="切换窗口置顶",
        )
        self.topmost_button.grid(row=0, column=4, padx=(9, 3))
        self.toolbar_buttons["topmost"] = self.topmost_button
        self.vault_lock_button = self._button(
            actions,
            "解锁",
            self._toggle_vault_lock,
            action=False,
            style="VaultUnlocked.TButton",
            icon="unlock",
        )
        self.vault_lock_button.grid(row=0, column=5, padx=3)
        self.toolbar_buttons["vault_lock"] = self.vault_lock_button
        self.vault_lock_tooltip = Tooltip(self.vault_lock_button, "点击锁定保险库")
        self._tooltips.append(self.vault_lock_tooltip)
        self.more_button = self._button(
            actions, "", self._show_more_menu, action=False, style="HeaderIcon.TButton", icon="more", tooltip="更多功能"
        )
        self.more_button.grid(row=0, column=6, padx=(7, 0))

        body = ttk.Frame(self, style="App.TFrame", padding=(14, 10, 14, 8))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self.body_frame = body
        self.sidebar = NavigationSidebar(body, self.icons, self.search_var, self._on_navigation_selected, self._toggle_sidebar)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.sidebar.configure(width=210)
        self.sidebar.grid_propagate(False)

        content = ttk.Frame(body, style="App.TFrame")
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        self.content_frame = content
        self.stats_view = DashboardStatsView(content, self.icons)
        self.stats_view.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        workspace_host = ttk.Frame(content, style="App.TFrame")
        workspace_host.grid(row=1, column=0, sticky="nsew")
        workspace_host.columnconfigure(0, weight=1)
        workspace_host.rowconfigure(0, weight=1)
        self.workspace_host = workspace_host
        self.otp_workspace = ttk.Frame(workspace_host, style="App.TFrame")
        self.otp_workspace.grid(row=0, column=0, sticky="nsew")
        self.otp_workspace.columnconfigure(0, weight=1)
        self.otp_workspace.rowconfigure(1, weight=1)

        list_header = ttk.Frame(self.otp_workspace, style="Glass.TFrame", padding=(14, 10))
        self.otp_list_header = list_header
        list_header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        list_header.columnconfigure(1, weight=1)
        ttk.Label(list_header, text="账号列表", style="ListTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.search_entry = ttk.Entry(list_header, textvariable=self.search_var, style="Search.TEntry")
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(18, 8))
        self.search_entry.bind("<Escape>", self._clear_search_event)
        ttk.Label(list_header, textvariable=self.result_summary_var, style="SearchSummary.TLabel").grid(row=0, column=2, padx=(0, 8))
        self.otp_show_pinned_button = self._button(
            list_header,
            "置顶可见",
            self.toggle_otp_show_pinned,
            action=False,
            style="ModuleActive.TButton" if self.settings.otp_show_pinned else "ModuleInactive.TButton",
            icon="pin",
            tooltip="显示或隐藏置顶账号",
        )
        self.otp_show_pinned_button.grid(row=0, column=3, padx=3)
        self._button(list_header, "新建分组", self.create_group, style="Quiet.TButton", icon="folder").grid(row=0, column=4, padx=3)
        self._button(list_header, "管理分组", self.manage_groups, style="Quiet.TButton", icon="settings").grid(row=0, column=5, padx=(3, 0))

        otp_columns = (
            ColumnSpec("select", "", 34, 34, align="center"),
            ColumnSpec("pin", "", 32, 30, align="center"),
            ColumnSpec("service", "服务", 145, 92, 2, sortable=True),
            ColumnSpec("account", "账号", 205, 120, 3, sortable=True),
            ColumnSpec("code", "验证码", 130, 105, 2, "center"),
            ColumnSpec("remaining", "剩余", 70, 62, align="center"),
            ColumnSpec("type", "类型", 145, 105, 1, sortable=True),
            ColumnSpec(
                "created", "创建时间", 132, 105, 1,
                sortable=True, initial_sort_direction="descending",
            ),
            ColumnSpec("actions", "操作", 46, 42, align="center"),
        )
        self.otp_table = CanvasDataTable(
            self.otp_workspace,
            otp_columns,
            icons=self.icons,
            primary_column="code",
            service_column="service",
            on_selection=self._on_selection,
            on_action=self._on_otp_table_action,
            on_context=self._show_otp_context,
            on_sort=self._on_otp_sort,
        )
        self.otp_table.set_sort_state(
            self.main_view_model.sort_spec.field.value,
            self.main_view_model.sort_spec.direction.value,
        )
        self.otp_table.grid(row=1, column=0, sticky="nsew")
        self.tree = self.otp_table

        self.context_menu = tk.Menu(self, **self._menu_options())
        self.context_menu.add_command(label="复制验证码", command=self.copy_selected)
        self.context_menu.add_command(label="编辑", command=self.edit_selected)
        self.context_menu.add_command(label="分组...", command=self.assign_selected_groups)
        self.context_menu.add_command(label="下一个 HOTP", command=self.next_hotp)
        self.context_menu.add_command(label="收藏", command=lambda: self.set_selected_favorite(True))
        self.context_menu.add_command(label="取消收藏", command=lambda: self.set_selected_favorite(False))
        self.context_menu.add_command(label="置顶", command=lambda: self.set_selected_pinned(True))
        self.context_menu.add_command(label="取消置顶", command=lambda: self.set_selected_pinned(False))
        self.context_menu.add_command(label="查看 URI", command=self.show_uri)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="删除", command=self.delete_selected)

        self.password_workspace = PasswordWorkspace(workspace_host, self.password_controller, self.icons)
        self.password_workspace.grid(row=0, column=0, sticky="nsew")
        self.password_controller.attach(self.password_workspace)

        footer = ttk.Frame(self, style="Footer.TFrame", padding=(16, 9, 16, 9))
        self.main_footer = footer
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        status_frame = ttk.Frame(footer, style="Footer.TFrame")
        status_frame.grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, text="●", style="Ready.TLabel").grid(row=0, column=0, padx=(0, 7))
        ttk.Label(status_frame, textvariable=self.status_var, style="FooterStatus.TLabel").grid(row=0, column=1)
        self.detail_label = ttk.Label(status_frame, textvariable=self.detail_var, style="FooterDetail.TLabel")
        self.detail_label.grid(row=0, column=2, padx=(14, 0))

        action_host = ttk.Frame(footer, style="Footer.TFrame")
        action_host.grid(row=0, column=1, sticky="e")
        action_host.columnconfigure(0, weight=1)
        action_host.rowconfigure(0, weight=1)
        self.otp_footer = ttk.Frame(action_host, style="Footer.TFrame")
        self.otp_footer.grid(row=0, column=0, sticky="nsew")
        self.otp_footer_buttons: dict[str, ttk.Button] = {}
        self.otp_selection_widgets: list[ttk.Button] = []
        otp_actions = (
            ("copy", "复制验证码", self.copy_selected, "Primary.TButton"),
            ("edit", "编辑", self.edit_selected, "Secondary.TButton"),
            ("group", "分组", self.assign_selected_groups, "Secondary.TButton"),
            ("hotp", "下一个 HOTP", self.next_hotp, "Secondary.TButton"),
            ("uri", "查看 URI", self.show_uri, "Secondary.TButton"),
            ("delete", "删除", self.delete_selected, "Danger.TButton"),
        )
        for column, (key, text, command, style) in enumerate(otp_actions):
            button = self._button(self.otp_footer, text, command, style=style)
            button.grid(row=0, column=column, padx=3)
            self.otp_footer_buttons[key] = button
            self.otp_selection_widgets.append(button)
        self.otp_footer_more = self._button(
            self.otp_footer, "更多操作", self._show_otp_action_menu, style="Secondary.TButton"
        )
        self.password_footer = self.password_workspace.create_footer(action_host)
        self.password_footer.grid(row=0, column=0, sticky="nsew")

        self.module_coordinator.attach(
            self.otp_workspace,
            self.password_workspace,
            self.module_switch,
            self.toolbar_buttons["add"],
            self.otp_footer,
            self.password_footer,
        )
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        # A normal binding on a Tk root also appears in every descendant's
        # bindtags. Use a private tag so child geometry changes do not invoke
        # the two root-window resize schedulers hundreds of times per drag.
        self._root_configure_tag = f"MainWindowConfigure:{id(self)}"
        self.bindtags((self._root_configure_tag, *self.bindtags()))
        self.bind_class(self._root_configure_tag, "<Configure>", self._on_root_configure)
        self.after_idle(self._apply_responsive_layout)

    def _on_root_configure(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is not self:
            return
        self._schedule_responsive_layout(event)
        self._schedule_window_size_save(event)

    def _show_more_menu(self) -> None:
        self.more_menu.tk_popup(self.more_button.winfo_rootx(), self.more_button.winfo_rooty() + self.more_button.winfo_height())

    def _toggle_vault_lock(self) -> None:
        """单一安全按钮按当前状态调用既有锁定或解锁流程。"""

        if self.locked:
            self.unlock_vault()
        else:
            self.lock_vault()

    def _update_vault_lock_button(self) -> None:
        """同步合并按钮的状态文本、图标、高亮样式与操作提示。"""

        if not hasattr(self, "vault_lock_button"):
            return
        locked = self.locked
        icon_key = "lock" if locked else "unlock"
        tint = "#C64653" if locked else None
        image = self.icons.image(icon_key, 18, tint)
        setattr(self.vault_lock_button, "_dynamic_icon", image)
        setattr(self.vault_lock_button, "_icon_key", icon_key)
        setattr(self.vault_lock_button, "_icon_tint", tint)
        show_text = not getattr(self, "_header_compact", False) and self.dpi_context.logical_px(self.winfo_width()) >= 1360
        label = ("锁定" if locked else "解锁") if show_text else ""
        self.vault_lock_button.configure(
            text=label,
            width=self._button_text_width(label),
            image=image,
            style="VaultLocked.TButton" if locked else "VaultUnlocked.TButton",
        )
        self.vault_lock_tooltip.text = "点击解锁保险库" if locked else "点击锁定保险库"

    def _show_export_menu(self) -> None:
        button = self.toolbar_buttons["export"]
        self.export_menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

    def _show_otp_action_menu(self) -> None:
        self.otp_action_menu.tk_popup(
            self.otp_footer_more.winfo_rootx(),
            self.otp_footer_more.winfo_rooty() - self.otp_action_menu.winfo_reqheight(),
        )

    def _on_otp_table_action(self, row_id: str, action: RowAction) -> None:
        if action in {"copy_primary", "activate"}:
            self.copy_selected()
        elif action == "toggle_favorite":
            self.toggle_favorite(row_id)
        elif action == "toggle_pin":
            self.toggle_pin(row_id)
        else:
            self.context_menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _show_otp_context(self, _row_id: str, x_root: int, y_root: int) -> None:
        self.context_menu.tk_popup(x_root, y_root)

    def _on_navigation_selected(self, scope: NavigationScope) -> None:
        if self.module_coordinator.active == "otp":
            self.main_view_model.set_scope(scope)
            self.active_group_id = getattr(scope, "group_id", None)
            self.refresh_tree()
        elif self.module_coordinator.active == "passwords":
            self.password_controller.select_scope(scope)
            self._refresh_dashboard_shell()

    def _toggle_sidebar(self) -> None:
        self._sidebar_user_override = not self.sidebar.collapsed
        self._responsive_layout_signature = None
        self._responsive_debouncer.cancel()
        self._apply_responsive_layout()

    def _schedule_responsive_layout(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is not self:
            return
        self._responsive_debouncer.trigger()

    def _apply_responsive_layout(self) -> None:
        if self._mui_surface_active():
            return
        if self.dpi_context.refresh_for_window(self):
            self._refresh_dpi_resources()
        width = max(self.dpi_context.logical_px(self.winfo_width()), 1)
        collapsed = width < 1120 if self._sidebar_user_override is None else self._sidebar_user_override
        compact = width < 1120
        self._header_compact = compact
        signature = (self.dpi_context.dpi, compact, collapsed)
        if signature == self._responsive_layout_signature:
            return
        self._responsive_layout_signature = signature
        self.sidebar.set_collapsed(collapsed)
        self.sidebar.configure(width=self.dpi_context.dp(58 if collapsed else 210))
        if compact:
            self.detail_label.grid_remove()
            self.header_brand.grid(row=0, column=0, rowspan=1, sticky="w")
            self.header_actions.grid(row=0, column=1, sticky="e", pady=0)
            self.module_switch.grid(row=0, column=2, sticky="e", padx=(10, 0))
        else:
            self.detail_label.grid(row=0, column=2, padx=(14, 0))
            self.header_brand.grid(row=0, column=0, rowspan=1, sticky="w")
            self.header_actions.grid(row=0, column=1, sticky="e", pady=0)
            self.module_switch.grid(row=0, column=2, sticky="e", padx=(10, 0))
        compact_labels = {
            "import": "",
            "export": "",
            "compact": "",
        }
        full_labels = {"import": "导入", "export": "导出", "compact": "轻量模式"}
        labels = compact_labels if compact else full_labels
        for key, label in labels.items():
            self.toolbar_buttons[key].configure(text=label, width=self._button_text_width(label))
        self.toolbar_buttons["add"].configure(width=8)
        self.toolbar_buttons["topmost"].configure(width=6)
        self.more_button.configure(width=3)
        secondary = ("hotp", "uri", "delete")
        if compact:
            self.toolbar_buttons["import"].grid_remove()
            self.toolbar_buttons["export"].grid_remove()
            for key in secondary:
                self.otp_footer_buttons[key].grid_remove()
            self.otp_footer_more.grid(row=0, column=6, padx=3)
        else:
            self.toolbar_buttons["import"].grid(row=0, column=1, padx=3)
            self.toolbar_buttons["export"].grid(row=0, column=2, padx=3)
            if width < 1360:
                for key in ("import", "export", "compact"):
                    self.toolbar_buttons[key].configure(text="", width=3)
            self.otp_footer_more.grid_remove()
            positions = {"hotp": 3, "uri": 4, "delete": 5}
            for key in secondary:
                self.otp_footer_buttons[key].grid(row=0, column=positions[key], padx=3)
        self.password_workspace.set_compact_actions(compact)
        self._update_vault_lock_button()

    def _refresh_dpi_resources(self) -> None:
        self._set_icon()
        configure_app_style(self, self.dpi_context)
        self.icons.invalidate_scale()
        self._toolbar_images.clear()
        brand_icon = self.icons.image("app", 38)
        self._toolbar_images.append(brand_icon)
        self.brand_icon_label.configure(image=brand_icon)
        buttons = list(self.toolbar_buttons.values()) + [self.more_button]
        for button in buttons:
            icon = getattr(button, "_icon_key", None)
            if not icon:
                continue
            image = self.icons.image(icon, 18, getattr(button, "_icon_tint", None))
            self._toolbar_images.append(image)
            button.configure(image=image)
        self.header_frame.configure(padding=(
            self.dpi_context.dp(20), self.dpi_context.dp(13),
            self.dpi_context.dp(20), self.dpi_context.dp(12),
        ))
        self.body_frame.configure(padding=(
            self.dpi_context.dp(14), self.dpi_context.dp(10),
            self.dpi_context.dp(14), self.dpi_context.dp(8),
        ))
        self.otp_list_header.configure(padding=(self.dpi_context.dp(14), self.dpi_context.dp(10)))
        self.main_footer.configure(padding=(
            self.dpi_context.dp(16), self.dpi_context.dp(9),
            self.dpi_context.dp(16), self.dpi_context.dp(9),
        ))
        self.sidebar.invalidate_scale()
        self.otp_table.invalidate_scale()
        self.password_workspace.table.invalidate_scale()
        self.stats_view.invalidate_scale()
        self.module_switch.invalidate_scale()

    def _refresh_dashboard_shell(self) -> None:
        if not hasattr(self, "sidebar"):
            return
        if self.module_coordinator.active == "otp":
            self.sidebar.set_query_variable(self.search_var)
            self.sidebar.set_items(self.main_view_model.navigation_items(), self.main_view_model.scope)
            self.stats_view.set_otp(self.main_view_model.dashboard_stats())
        elif self.module_coordinator.active == "passwords":
            self.sidebar.set_query_variable(self.password_workspace.query_var)
            self.sidebar.set_items(self.password_view_model.navigation_items(), self.password_view_model.scope)
            self.stats_view.set_passwords(self.password_view_model.dashboard_stats())
        self.sidebar.set_security(self.security_var.get())
