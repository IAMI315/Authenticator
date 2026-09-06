"""Switch between peer OTP and password workspaces."""

from __future__ import annotations

from typing import Any, Literal

ModuleName = Literal["otp", "passwords"]


class ModuleCoordinator:
    def __init__(self, app: Any, password_controller: Any) -> None:
        self.app = app
        self.password_controller = password_controller
        self.active: ModuleName = "otp"
        self.otp_workspace: Any = None
        self.password_workspace: Any = None
        self.module_switch: Any = None
        self.primary_add_button: Any = None
        self.otp_footer: Any = None
        self.password_footer: Any = None
        self._password_dirty = True
        self._mounted = False

    def attach(
        self,
        otp_workspace: Any,
        password_workspace: Any,
        module_switch: Any,
        primary_add_button: Any,
        otp_footer: Any = None,
        password_footer: Any = None,
    ) -> None:
        self.otp_workspace = otp_workspace
        self.password_workspace = password_workspace
        self.module_switch = module_switch
        self.primary_add_button = primary_add_button
        self.otp_footer = otp_footer
        self.password_footer = password_footer
        self.switch("otp")

    def switch(self, module: ModuleName) -> None:
        if self._mounted and module == self.active:
            return
        self.password_controller.view_model.conceal()
        self.active = module
        self.app.otp_table.set_layout_active(module == "otp")
        self.password_workspace.table.set_layout_active(module == "passwords")
        if module == "otp":
            self.otp_workspace.grid()
            self.password_workspace.grid_remove()
            self.primary_add_button.configure(text="新增", command=self.app.add_account)
            if self.otp_footer is not None:
                self.otp_footer.grid()
            if self.password_footer is not None:
                self.password_footer.grid_remove()
        else:
            self.password_workspace.grid()
            self.otp_workspace.grid_remove()
            self.primary_add_button.configure(text="新增密码", command=self.password_controller.add)
            if self._password_dirty:
                self.password_controller.refresh()
                self._password_dirty = False
            if self.password_footer is not None:
                self.password_footer.grid()
            if self.otp_footer is not None:
                self.otp_footer.grid_remove()
        self.module_switch.set_active(module)
        if hasattr(self.app, "_refresh_dashboard_shell"):
            self.app._refresh_dashboard_shell()
        self._mounted = True

    def add_item(self) -> None:
        self.app.add_account() if self.active == "otp" else self.password_controller.add()

    def create_group(self) -> None:
        self.app.create_group() if self.active == "otp" else self.password_controller.create_group()

    def manage_groups(self) -> None:
        self.app.manage_groups() if self.active == "otp" else self.password_controller.manage_groups()

    def assign_groups(self) -> None:
        self.app.assign_selected_groups() if self.active == "otp" else self.password_controller.assign_groups()

    def focus_search(self) -> str:
        if self.active == "otp":
            return self.app.focus_search()
        self.password_workspace.focus_search()
        return "break"

    def refresh_passwords(self) -> None:
        if self.active == "passwords":
            self.password_controller.refresh()
            self._password_dirty = False
        else:
            self._password_dirty = True

    def conceal_passwords(self) -> None:
        self.password_controller.view_model.conceal()
        self.password_controller.refresh()
