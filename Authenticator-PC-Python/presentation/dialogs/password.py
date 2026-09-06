"""保险库密码输入及可选二次确认对话框。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from presentation.constants import APP_NAME
from presentation.styles import center_dialog, configure_dialog_surface


class PasswordDialog(tk.Toplevel):
    """收集非空密码；密码从不写入日志或设置，只经返回值交给保险库服务。"""

    def __init__(
        self,
        parent: Any,
        title: str,
        prompt: str,
        confirm: bool = False,
        min_length: int = 1,
    ) -> None:
        """创建密码表单；``confirm`` 为真时显示确认输入框。"""

        super().__init__(parent)
        self.result: str | None = None
        self.confirm_required = confirm
        self.min_length = max(1, min_length)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        configure_dialog_surface(self)

        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 22))
        frame.grid(sticky="nsew")
        ttk.Label(frame, text=prompt, style="DialogMuted.TLabel", wraplength=360, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(frame, text="密码", style="Form.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*", width=34)
        password_entry.grid(row=1, column=1, sticky="ew", pady=4)

        self.confirm_var = tk.StringVar()
        if confirm:
            ttk.Label(frame, text="确认密码", style="Form.TLabel").grid(row=2, column=0, sticky="w", pady=5)
            confirm_entry = ttk.Entry(frame, textvariable=self.confirm_var, show="*", width=34)
            confirm_entry.grid(row=2, column=1, sticky="ew", pady=4)

        button_row = ttk.Frame(frame, style="Dialog.TFrame")
        button_row.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(button_row, text="取消", command=self.cancel, style="Secondary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text="继续", command=self.submit, style="Primary.TButton").grid(row=0, column=1)
        frame.columnconfigure(1, weight=1)

        self.bind("<Return>", lambda _event: self.submit())
        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        password_entry.focus_set()
        center_dialog(self, parent)
        self.grab_set()

    def submit(self) -> None:
        """验证非空和可选的两次一致性，成功后设置 ``result`` 并关闭。"""

        password = self.password_var.get()
        if not password:
            messagebox.showwarning(APP_NAME, "请输入密码。", parent=self)
            return
        if len(password) < self.min_length:
            messagebox.showwarning(
                APP_NAME,
                f"密码至少需要 {self.min_length} 个字符。",
                parent=self,
            )
            return
        if self.confirm_required and self.confirm_var.get() != password:
            messagebox.showwarning(APP_NAME, "两次输入的密码不一致。", parent=self)
            return
        self.result = password
        self.destroy()

    def cancel(self) -> None:
        """取消密码输入，不返回任何密码文本。"""

        self.destroy()

    @classmethod
    def ask(
        cls,
        parent: Any,
        title: str,
        prompt: str,
        confirm: bool = False,
        min_length: int = 1,
    ) -> str | None:
        """显示模态密码对话框并返回密码或 ``None``。"""

        dialog = cls(parent, title, prompt, confirm, min_length)
        parent.wait_window(dialog)
        return dialog.result


class MasterPasswordChangeDialog(tk.Toplevel):
    """收集当前主密码和两次新主密码。"""

    def __init__(self, parent: Any, min_length: int = 8) -> None:
        super().__init__(parent)
        self.result: tuple[str, str] | None = None
        self.min_length = min_length
        self.title("修改主密码")
        self.resizable(False, False)
        self.transient(parent)
        configure_dialog_surface(self)
        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 22))
        frame.grid(sticky="nsew")
        ttk.Label(
            frame,
            text="修改主密码不会解密本地文件。请输入当前主密码并设置新密码。",
            style="DialogMuted.TLabel",
            wraplength=380,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.current_var = tk.StringVar()
        self.new_var = tk.StringVar()
        self.confirm_var = tk.StringVar()
        labels = (("当前主密码", self.current_var), ("新主密码", self.new_var), ("确认新密码", self.confirm_var))
        first_entry: ttk.Entry | None = None
        for row, (label, variable) in enumerate(labels, start=1):
            ttk.Label(frame, text=label, style="Form.TLabel").grid(row=row, column=0, sticky="w", pady=5)
            entry = ttk.Entry(frame, textvariable=variable, show="*", width=34)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            first_entry = first_entry or entry
        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="取消", command=self.destroy, style="Secondary.TButton").grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(buttons, text="修改", command=self.submit, style="Primary.TButton").grid(row=0, column=1)
        frame.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda _event: self.submit())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        if first_entry is not None:
            first_entry.focus_set()
        center_dialog(self, parent)
        self.grab_set()

    def submit(self) -> None:
        current = self.current_var.get()
        new = self.new_var.get()
        if not current:
            messagebox.showwarning(APP_NAME, "请输入当前主密码。", parent=self)
            return
        if len(new) < self.min_length:
            messagebox.showwarning(APP_NAME, f"新主密码至少需要 {self.min_length} 个字符。", parent=self)
            return
        if new != self.confirm_var.get():
            messagebox.showwarning(APP_NAME, "两次输入的新主密码不一致。", parent=self)
            return
        self.result = (current, new)
        self.destroy()

    @classmethod
    def ask(cls, parent: Any, min_length: int = 8) -> tuple[str, str] | None:
        dialog = cls(parent, min_length)
        parent.wait_window(dialog)
        return dialog.result
