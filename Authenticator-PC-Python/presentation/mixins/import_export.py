"""导入导出 UI 工作流；文件 I/O 和解析通过后台任务执行。"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from application.import_export import BackupPasswordRequiredError, ImportBundle, parse_import_text
from application.import_service import ImportResult
from domain.google_authenticator import (
    GoogleAuthenticatorExport,
    export_google_authenticator_migration,
)
from infrastructure.errors import VaultError
from infrastructure.secure_storage import MIN_MASTER_PASSWORD_LENGTH
from presentation.constants import APP_NAME
from presentation.dialogs import (
    GoogleAuthenticatorExportDialog,
    PasswordDialog,
    TextImportDialog,
)
from presentation.mixins.base import WindowMixin
from presentation.styles import UI_FONT, center_dialog, configure_dialog_surface


class ImportExportMixin(WindowMixin):
    """连接文件/文本对话框、解析器、导入服务和导出格式的控制器。"""

    def _add_imported_entries(self, bundle: ImportBundle) -> ImportResult | None:
        """把后台解析结果交给事务导入服务，并汇总账号/分组/警告提示。"""

        try:
            result = self.import_service.import_bundle(bundle)
        except (VaultError, ValueError) as error:
            messagebox.showerror(APP_NAME, f"导入失败：{error}", parent=self)
            return None
        if result.accounts_added or result.groups_added:
            self.refresh_tree()
        message = f"已导入 {result.accounts_added} 个账号。"
        if result.groups_added:
            message += f"已导入 {result.groups_added} 个分组。"
        if result.duplicates_skipped:
            message += f"已跳过 {result.duplicates_skipped} 个重复账号。"
        if result.passwords_added:
            message += f"已导入 {result.passwords_added} 条密码。"
        if result.password_groups_added:
            message += f"已导入 {result.password_groups_added} 个密码分组。"
        if result.password_duplicates_skipped:
            message += f"已跳过 {result.password_duplicates_skipped} 条重复密码。"
        if bundle.warnings:
            message += f"已跳过 {len(bundle.warnings)} 条不支持或无效的记录。"
        self._show_status(message, clear_after=10_000)
        if bundle.warnings:
            messagebox.showwarning(APP_NAME, message, parent=self)
        return result

    def import_file(self) -> None:
        """选择文件后在后台读取和解析，成功时在 Tk 主线程导入。"""

        if not self._guard_unlocked():
            return
        selected = filedialog.askopenfilename(
            parent=self,
            title="导入验证器备份",
            filetypes=(("备份文件", "*.authbak *.json *.txt"), ("所有文件", "*.*")),
        )
        if not selected:
            return
        def load_import(passphrase: str | None = None) -> ImportBundle:
            """读取文件、自动识别加密信封，再调用纯导入解析器。"""

            return self.backup_service.load(selected, passphrase)

        def import_failed(error: Exception) -> None:
            """在主线程呈现读取或解析失败。"""

            if isinstance(error, BackupPasswordRequiredError):
                password = PasswordDialog.ask(
                    self,
                    "解密备份",
                    "此备份来自另一台电脑或不同的 Windows 用户。请输入生成备份时的主密码。",
                    min_length=MIN_MASTER_PASSWORD_LENGTH,
                )
                if password is None:
                    self._show_status("已取消导入加密备份。")
                    return
                self._run_background_operation(
                    lambda: load_import(password),
                    self._add_imported_entries,
                    status="正在解密并解析备份...",
                    on_error=lambda nested_error: messagebox.showerror(
                        APP_NAME, f"导入失败：{nested_error}", parent=self
                    ),
                )
                return
            messagebox.showerror(APP_NAME, f"导入失败：{error}", parent=self)

        self._run_background_operation(
            load_import,
            self._add_imported_entries,
            status="正在读取并解析备份...",
            on_error=import_failed,
        )

    def import_text(self) -> None:
        """从文本对话框获取 URI/JSON 内容，并在后台解析后导入。"""

        if not self._guard_unlocked():
            return
        content = TextImportDialog.ask(self)
        if not content:
            return
        def import_failed(error: Exception) -> None:
            """在主线程呈现文本导入失败。"""

            messagebox.showerror(APP_NAME, f"导入失败：{error}", parent=self)

        self._run_background_operation(
            lambda: parse_import_text(content),
            self._add_imported_entries,
            status="正在解析导入内容...",
            on_error=import_failed,
        )

    def export_backup(self) -> None:
        """兼容旧命令名称，默认执行推荐的加密备份。"""

        self.export_encrypted_backup()

    def export_encrypted_backup(self) -> None:
        """无密码提示地导出可由 DPAPI 或源主密码恢复的加密备份。"""

        if not self._guard_unlocked():
            return
        if not self.vault.entries and not self.vault.password_entries:
            self._show_status("暂无账号或密码可导出。")
            return
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="导出加密备份",
            defaultextension=".authbak",
            initialfile=f"authenticator-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.authbak",
            filetypes=(("加密备份", "*.authbak"),),
        )
        if not selected:
            return
        account_count = len(self.vault.entries)
        password_count = len(self.vault.password_entries)
        self._run_background_operation(
            lambda: self.backup_service.export_encrypted(selected, self.vault),
            lambda _result: self._show_status(
                f"已加密导出 {account_count} 个账号和 {password_count} 条密码。"
            ),
            status="正在导出加密备份...",
            on_error=lambda error: messagebox.showerror(APP_NAME, f"导出失败：{error}", parent=self),
        )

    def export_plain_backup(self) -> None:
        """确认明文密钥风险后，将桌面版 JSON 备份写入用户选择的文件。"""

        if not self._guard_unlocked():
            return
        if not self.vault.entries and not self.vault.password_entries:
            self._show_status("暂无账号或密码可导出。")
            return
        if not messagebox.askyesno(
            APP_NAME,
            "导出的 JSON 包含明文账号密钥和密码。请妥善保管，是否继续？",
            parent=self,
        ):
            return
        default_name = f"authenticator-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="导出桌面版备份",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=(("JSON 文件", "*.json"),),
        )
        if not selected:
            return
        account_count = len(self.vault.entries)
        password_count = len(self.vault.password_entries)

        def export_failed(error: Exception) -> None:
            """在主线程呈现备份写入失败。"""

            messagebox.showerror(APP_NAME, f"导出失败：{error}", parent=self)

        self._run_background_operation(
            lambda: self.backup_service.export_plain(selected, self.vault),
            lambda _result: self._show_status(
                f"已导出 {account_count} 个账号和 {password_count} 条密码。"
            ),
            status="正在导出备份...",
            on_error=export_failed,
        )

    def export_uris(self) -> None:
        """确认风险后导出一行一个的标准 otpauth URI 文本文件。"""

        if not self._guard_unlocked():
            return
        if not self.vault.entries:
            self._show_status("暂无账号可导出。")
            return
        if not messagebox.askyesno(
            APP_NAME,
            "导出的 URI 文件包含明文账号密钥。请妥善保管，是否继续？",
            parent=self,
        ):
            return
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="导出 otpauth URI",
            defaultextension=".txt",
            initialfile=f"authenticator-otpauth-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
            filetypes=(("文本文件", "*.txt"),),
        )
        if not selected:
            return
        entries = list(self.vault.entries)

        def write_uris() -> int:
            """工作线程函数：在内存快照中序列化 URI 后写入目标文件。"""

            self.backup_service.export_uris(selected, entries)
            return len(entries)

        def export_failed(error: Exception) -> None:
            """在主线程呈现 URI 文件写入失败。"""

            messagebox.showerror(APP_NAME, f"导出失败：{error}", parent=self)

        self._run_background_operation(
            write_uris,
            lambda _result: self._show_status(f"已导出 {len(entries)} 个 otpauth URI。"),
            status="正在导出 otpauth URI...",
            on_error=export_failed,
        )

    def export_google_authenticator_qr(self) -> None:
        """Generate Google-compatible migration QR batches for all OTP accounts."""

        if not self._guard_unlocked():
            return
        if not self.vault.entries:
            self._show_status("暂无验证码账号可导出。")
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Google 导入二维码包含账号密钥。请确保屏幕周围没有他人，并只使用可信设备扫描。是否继续？",
            parent=self,
        ):
            return
        entries = list(self.vault.entries)

        def show_export(export: GoogleAuthenticatorExport) -> None:
            GoogleAuthenticatorExportDialog(self, export)
            message = f"已生成 {len(export.uris)} 张二维码，共 {export.accounts_exported} 个账号。"
            if export.warnings:
                message += f"已跳过 {len(export.warnings)} 个不兼容账号。"
            self._show_status(message, clear_after=10_000)

        self._run_background_operation(
            lambda: export_google_authenticator_migration(entries),
            show_export,
            status="正在生成 Google Authenticator 二维码...",
            on_error=lambda error: messagebox.showerror(
                APP_NAME,
                f"生成 Google Authenticator 二维码失败：{error}",
                parent=self,
            ),
        )

    def show_uri(self) -> None:
        """显示单选账号的 URI，并提供显式复制按钮，不自动写入剪贴板。"""

        if not self._guard_unlocked():
            return
        entry = self._selected_entry()
        if not entry:
            self._show_status("请先选择一个账号。")
            return
        dialog = tk.Toplevel(self)
        dialog.title("otpauth URI")
        dialog.transient(self)
        dialog.resizable(True, False)
        configure_dialog_surface(dialog)
        frame = ttk.Frame(dialog, style="Dialog.TFrame", padding=(22, 20))
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=f"{entry.title} 的 URI", style="Form.TLabel", font=(UI_FONT, 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        uri_var = tk.StringVar(value=entry.to_uri())
        uri_entry = ttk.Entry(frame, textvariable=uri_var, width=84)
        uri_entry.grid(row=1, column=0, sticky="ew")

        def copy_uri() -> None:
            """复制当前 URI 输入框内容并在主窗口状态栏反馈。"""

            self.clipboard_clear()
            self.clipboard_append(uri_var.get())
            self._show_status(f"已复制 {entry.title} 的 URI。")

        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.grid(row=2, column=0, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="复制 URI", command=copy_uri, style="Primary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="关闭", command=dialog.destroy, style="Secondary.TButton").grid(row=0, column=1)
        uri_entry.focus_set()
        uri_entry.selection_range(0, "end")
        center_dialog(dialog, self)
