"""保险库密码、锁定、设置、关于和 API 帮助等 UI 控制。"""

from __future__ import annotations

import time
from tkinter import messagebox

from infrastructure.errors import VaultError
from infrastructure.secure_storage import MIN_MASTER_PASSWORD_LENGTH, StorageLoadKind
from presentation.constants import APP_NAME
from presentation.dialogs import MasterPasswordChangeDialog, PasswordDialog, SettingsDialog
from presentation.mixins.base import WindowMixin


class VaultControlsMixin(WindowMixin):
    """把安全对话框操作委托给 ``VaultService`` 与设置仓储。"""

    def set_password(self) -> None:
        """验证当前主密码后只更新数据密钥的密码包装信封。"""

        if not self._guard_unlocked():
            return
        value = MasterPasswordChangeDialog.ask(self, MIN_MASTER_PASSWORD_LENGTH)
        if value is None:
            return
        current_password, new_password = value

        def password_set(_result: None) -> None:
            """主密码包装更新成功后重置活动计时。"""

            self.last_activity = time.monotonic()
            self.refresh_tree()
            self._show_status("主密码已修改，本地数据仍保持加密。")

        self._run_background_operation(
            lambda: self.vault_service.change_master_password(current_password, new_password),
            password_set,
            status="正在更新主密码...",
        )

    def remove_password(self) -> None:
        """强制加密版本不允许移除主密码。"""

        self._show_status("本地安全数据必须保持加密，不能移除主密码。")

    def lock_vault(self, auto_locked: bool = False) -> None:
        """立即清除已解锁数据和内存数据密钥。"""

        if self.locked:
            return
        self.vault_service.lock()
        self.locked = True
        self._storage_load_kind = StorageLoadKind.NEEDS_PASSWORD
        self.refresh_tree()
        self._show_status("保险库已自动锁定。" if auto_locked else "保险库已锁定。", clear_after=10_000)

    def unlock_vault(self) -> None:
        """请求密码并在后台解锁，成功回调仅在 Tk 主线程修改 UI 状态。"""

        prompt = (
            "请输入旧版保险库密码。解锁成功后将自动升级为强制加密格式。"
            if self._storage_load_kind == StorageLoadKind.NEEDS_LEGACY_PASSWORD
            else "请输入主密码解锁本地安全数据。"
        )
        password = PasswordDialog.ask(self, "解锁保险库", prompt)
        if password is None:
            return
        if self._storage_load_kind == StorageLoadKind.NEEDS_LEGACY_PASSWORD:
            self.vault.secure_settings = self.settings.secure_values()

        def unlocked(_result: None) -> None:
            """解锁成功后应用安全设置；旧版数据同时完成迁移。"""

            self._storage_load_kind = StorageLoadKind.AUTO_UNLOCKED
            self._activate_secure_data("本地安全数据已解锁。")

        self._run_background_operation(
            lambda: self.vault_service.unlock(password),
            unlocked,
            status="正在解锁保险库...",
        )

    def open_settings(self) -> None:
        """显示自动锁定与本机 API 设置，并在保存后更新安全摘要。"""

        if self.locked:
            self.unlock_vault()
            if self.locked:
                return
        value = SettingsDialog.ask(
            self,
            self.settings.autolock_minutes,
            self.data_directory,
            self.api_endpoint,
            self.api_token,
            self._api_status_text(),
        )
        if value is None:
            return
        self.settings.autolock_minutes = value
        try:
            self._persist_settings()
        except VaultError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.last_activity = time.monotonic()
        self.refresh_tree()
        status = "已关闭自动锁定。" if value == 0 else f"保险库将在闲置 {value} 分钟后自动锁定。"
        self._show_status(status)

    def show_about(self) -> None:
        """显示本地数据位置、支持的 OTP 类型和加密方案。"""

        messagebox.showinfo(
            APP_NAME,
            "验证器桌面版\n\n"
            "用于管理 TOTP、HOTP、Steam Guard 和 Battle.net 动态验证码的本地 Python 桌面程序。\n\n"
            f"保险库位置：\n{self.data_directory}\n\n"
            "本地安全数据始终使用 AES-256-GCM 加密；主密码恢复密钥使用 "
            "PBKDF2-HMAC-SHA256，正常启动由 Windows DPAPI 自动解锁。",
            parent=self,
        )

    def show_api_help(self) -> None:
        """显示稳定 API 路由、令牌位置和锁定时的访问限制。"""

        messagebox.showinfo(
            APP_NAME,
            "本机 API\n\n"
            f"服务地址：{self.api_endpoint}\n"
            "访问令牌可在“安全 -> 设置”中复制。\n\n"
            "GET /v1/accounts\n"
            "列出账号元数据。\n\n"
            "GET /v1/groups\n"
            "列出分组及账号数量。\n\n"
            "GET /v1/accounts/{id}/secret\n"
            "读取指定账号的密钥。\n\n"
            "POST /v1/accounts\n"
            "新增账号；可选 group_ids 指定已有分组。\n\n"
            "所有 API 请求必须带 X-Authenticator-Token 请求头；服务仅监听本机，保险库锁定时不会返回账号或密钥。",
            parent=self,
        )
