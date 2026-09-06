"""粘贴多行 otpauth URI 或 JSON 文本的导入对话框。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from presentation.constants import APP_NAME
from presentation.dpi import dpi_context_for
from presentation.styles import (
    ACCENT,
    GLASS_BORDER,
    GLASS_SURFACE,
    SELECTION,
    TEXT_PRIMARY,
    center_dialog,
    configure_dialog_surface,
)


class TextImportDialog(tk.Toplevel):
    """只收集非空文本，实际解析和导入由后台任务/应用服务完成。"""

    def __init__(self, parent: Any) -> None:
        """创建可伸缩多行文本输入框和确认/取消操作。"""

        super().__init__(parent)
        self.result: str | None = None
        self.title("导入 otpauth URI")
        dpi = dpi_context_for(parent)
        self.minsize(dpi.dp(560), dpi.dp(360))
        self.transient(parent)
        configure_dialog_surface(self)

        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(20, 18))
        frame.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="每行粘贴一个 otpauth:// URI。", style="DialogMuted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        self.text = tk.Text(
            frame,
            wrap="word",
            height=14,
            font=("Consolas", 10),
            background=GLASS_SURFACE,
            foreground=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            selectbackground=SELECTION,
            selectforeground=TEXT_PRIMARY,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=GLASS_BORDER,
            highlightcolor=ACCENT,
            padx=12,
            pady=10,
        )
        self.text.grid(row=1, column=0, sticky="nsew")
        button_row = ttk.Frame(frame, style="Dialog.TFrame")
        button_row.grid(row=2, column=0, sticky="e", pady=(12, 0))
        ttk.Button(button_row, text="取消", command=self.cancel, style="Secondary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text="导入", command=self.submit, style="Primary.TButton").grid(row=0, column=1)
        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.text.focus_set()
        center_dialog(self, parent)
        self.grab_set()

    def submit(self) -> None:
        """返回用户输入的非空原始文本，不在 UI 线程解析格式。"""

        text = self.text.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showwarning(APP_NAME, "请至少粘贴一个 otpauth URI。", parent=self)
            return
        self.result = text
        self.destroy()

    def cancel(self) -> None:
        """取消文本导入。"""

        self.destroy()

    @classmethod
    def ask(cls, parent: Any) -> str | None:
        """显示模态文本对话框并返回原始文本或 ``None``。"""

        dialog = cls(parent)
        parent.wait_window(dialog)
        return dialog.result
