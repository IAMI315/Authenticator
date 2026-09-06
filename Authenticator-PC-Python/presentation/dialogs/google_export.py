"""Google Authenticator migration QR export dialog."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

from domain.google_authenticator import GoogleAuthenticatorExport
from presentation.constants import APP_NAME
from presentation.styles import UI_FONT, center_dialog, configure_dialog_surface


class GoogleAuthenticatorExportDialog(tk.Toplevel):
    """Display Google migration batches as crisp, locally generated QR codes."""

    def __init__(self, parent: Any, export: GoogleAuthenticatorExport) -> None:
        super().__init__(parent)
        self.export = export
        self.index = 0
        self.qr_image: ImageTk.PhotoImage | None = None
        self.title("导出到 Google Authenticator")
        self.transient(parent)
        self.resizable(False, False)
        configure_dialog_surface(self)

        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 20))
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text="使用 Google Authenticator 扫描",
            style="Form.TLabel",
            font=(UI_FONT, 13, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="二维码包含账号密钥，请勿截图、转发或展示给他人。",
            style="DialogMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(5, 14))

        self.image_label = ttk.Label(frame, style="Dialog.TLabel")
        self.image_label.grid(row=2, column=0)
        self.page_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.page_var, style="DialogMuted.TLabel").grid(
            row=3, column=0, pady=(12, 0)
        )

        controls = ttk.Frame(frame, style="Dialog.TFrame")
        controls.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        controls.columnconfigure(1, weight=1)
        self.previous_button = ttk.Button(
            controls,
            text="上一张",
            command=lambda: self._move(-1),
            style="Secondary.TButton",
        )
        self.previous_button.grid(row=0, column=0)
        self.next_button = ttk.Button(
            controls,
            text="下一张",
            command=lambda: self._move(1),
            style="Primary.TButton",
        )
        self.next_button.grid(row=0, column=2, padx=(10, 0))
        ttk.Button(
            controls,
            text="关闭",
            command=self.destroy,
            style="Secondary.TButton",
        ).grid(row=0, column=3, padx=(10, 0))
        if export.warnings:
            ttk.Button(
                controls,
                text=f"查看 {len(export.warnings)} 个跳过项",
                command=self._show_warnings,
                style="Secondary.TButton",
            ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.bind("<Left>", lambda _event: self._move(-1))
        self.bind("<Right>", lambda _event: self._move(1))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._render_page()
        center_dialog(self, parent)
        self.grab_set()
        self.focus_force()

    def _render_page(self) -> None:
        import zxingcpp

        raw = zxingcpp.write_barcode(
            zxingcpp.BarcodeFormat.QRCode,
            self.export.uris[self.index],
            0,
            0,
            quiet_zone=4,
        )
        minimum = Image.fromarray(raw)
        dpi_context: Any = getattr(self.master, "dpi_context", None)
        target = dpi_context.dp(430) if dpi_context is not None else 430
        scale = max(4, min(8, target // minimum.width))
        rendered = minimum.resize(
            (minimum.width * scale, minimum.height * scale),
            Image.Resampling.NEAREST,
        )
        self.qr_image = ImageTk.PhotoImage(rendered, master=self)
        self.image_label.configure(image=self.qr_image)
        page_count = len(self.export.uris)
        self.page_var.set(
            f"第 {self.index + 1}/{page_count} 张 · 共 {self.export.accounts_exported} 个账号"
        )
        self.previous_button.configure(state="normal" if self.index > 0 else "disabled")
        self.next_button.configure(state="normal" if self.index + 1 < page_count else "disabled")

    def _move(self, offset: int) -> None:
        next_index = self.index + offset
        if 0 <= next_index < len(self.export.uris):
            self.index = next_index
            self._render_page()

    def _show_warnings(self) -> None:
        messagebox.showwarning(
            APP_NAME,
            "以下账号未导出：\n\n" + "\n".join(self.export.warnings),
            parent=self,
        )
