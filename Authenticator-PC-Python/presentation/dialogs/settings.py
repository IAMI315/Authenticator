"""自动锁定、本地数据目录和本机 API 信息设置对话框。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from presentation.constants import APP_NAME
from presentation.styles import UI_FONT, center_dialog, configure_dialog_surface


class SettingsDialog(tk.Toplevel):
    """编辑可写的自动锁定分钟数，并只读展示 API 地址和令牌。"""

    def __init__(
        self,
        parent: Any,
        autolock_minutes: int,
        otp_codes_visible: bool,
        passwords_visible: bool,
        data_directory: Path,
        api_endpoint: str,
        api_token: str,
        api_status: str,
    ) -> None:
        """构建设置表单；API 令牌只提供复制功能，不能在此处手工修改。"""

        super().__init__(parent)
        self.result: tuple[int, bool, bool] | None = None
        self.title("设置")
        self.resizable(False, False)
        self.transient(parent)
        configure_dialog_surface(self)

        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 22))
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="闲置多久后自动锁定（分钟）", style="Form.TLabel").grid(row=0, column=0, sticky="w", pady=6)
        self.autolock_var = tk.StringVar(value=str(autolock_minutes))
        ttk.Spinbox(frame, from_=0, to=1_440, textvariable=self.autolock_var, width=12).grid(row=0, column=1, sticky="w", pady=6)
        self.otp_codes_visible_var = tk.BooleanVar(value=otp_codes_visible)
        self.passwords_visible_var = tk.BooleanVar(value=passwords_visible)
        ttk.Checkbutton(frame, text="默认显示验证码", variable=self.otp_codes_visible_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Checkbutton(frame, text="默认显示密码本密码", variable=self.passwords_visible_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(
            frame,
            text=f"本地保险库目录：\n{data_directory}",
            style="DialogMuted.TLabel",
            justify="left",
            wraplength=440,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(16, 0))

        ttk.Separator(frame, orient="horizontal").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(18, 12))
        ttk.Label(frame, text="本机 API", style="Form.TLabel", font=(UI_FONT, 10, "bold")).grid(
            row=5, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(frame, text="服务地址", style="DialogMuted.TLabel").grid(row=6, column=0, sticky="w", pady=(8, 5))
        endpoint_row = ttk.Frame(frame, style="Dialog.TFrame")
        endpoint_row.grid(row=6, column=1, sticky="ew", pady=(8, 5))
        endpoint_row.columnconfigure(0, weight=1)
        endpoint_var = tk.StringVar(value=api_endpoint)
        endpoint_entry = ttk.Entry(endpoint_row, textvariable=endpoint_var, state="readonly", width=42)
        endpoint_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            endpoint_row,
            text="复制",
            command=lambda: self._copy_value(endpoint_var.get()),
            style="Secondary.TButton",
            width=5,
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(frame, text="访问令牌", style="DialogMuted.TLabel").grid(row=7, column=0, sticky="w", pady=5)
        token_row = ttk.Frame(frame, style="Dialog.TFrame")
        token_row.grid(row=7, column=1, sticky="ew", pady=5)
        token_row.columnconfigure(0, weight=1)
        token_var = tk.StringVar(value=api_token)
        token_entry = ttk.Entry(token_row, textvariable=token_var, state="readonly", width=42)
        token_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(
            token_row,
            text="复制",
            command=lambda: self._copy_value(token_var.get()),
            style="Secondary.TButton",
            width=5,
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(
            frame,
            text=f"状态：{api_status}\nAPI 仅监听本机，调用时需提供 X-Authenticator-Token。",
            style="DialogMuted.TLabel",
            justify="left",
            wraplength=500,
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(7, 0))
        button_row = ttk.Frame(frame, style="Dialog.TFrame")
        button_row.grid(row=9, column=0, columnspan=2, sticky="e", pady=(20, 0))
        ttk.Button(button_row, text="取消", command=self.cancel, style="Secondary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text="保存", command=self.submit, style="Primary.TButton").grid(row=0, column=1)
        self.bind("<Return>", lambda _event: self.submit())
        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        center_dialog(self, parent)
        self.grab_set()

    def submit(self) -> None:
        """校验 0 到 1440 的整数分钟数，成功后设置结果并关闭。"""

        try:
            value = int(self.autolock_var.get())
            if value < 0 or value > 1_440:
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_NAME, "请输入 0 到 1440 之间的整数。", parent=self)
            return
        self.result = (value, self.otp_codes_visible_var.get(), self.passwords_visible_var.get())
        self.destroy()

    def cancel(self) -> None:
        """取消设置修改。"""

        self.destroy()

    def _copy_value(self, value: str) -> None:
        """复制只读 API 地址或令牌到系统剪贴板。"""

        self.clipboard_clear()
        self.clipboard_append(value)

    @classmethod
    def ask(
        cls,
        parent: Any,
        autolock_minutes: int,
        otp_codes_visible: bool,
        passwords_visible: bool,
        data_directory: Path,
        api_endpoint: str,
        api_token: str,
        api_status: str,
    ) -> tuple[int, bool, bool] | None:
        """显示模态设置对话框并返回确认的自动锁定分钟数或 ``None``。"""

        dialog = cls(parent, autolock_minutes, otp_codes_visible, passwords_visible, data_directory, api_endpoint, api_token, api_status)
        parent.wait_window(dialog)
        return dialog.result
