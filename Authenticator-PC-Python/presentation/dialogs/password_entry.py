"""Password-book create/edit dialog."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from application.password_commands import CreatePasswordCommand, UpdatePasswordCommand
from domain.passwords import PASSWORD_DEFAULT_GROUP_ID, PasswordEntry, normalise_password_url
from presentation.constants import APP_NAME
from presentation.dpi import dpi_context_for
from presentation.password_generator_panel import PasswordGeneratorPanel
from presentation.styles import UI_FONT, center_dialog, configure_dialog_surface

PasswordCommand = CreatePasswordCommand | UpdatePasswordCommand


class PasswordDialog(tk.Toplevel):
    def __init__(
        self,
        parent: Any,
        original: PasswordEntry | None = None,
        initial_group_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.original = original
        self.initial_group_id = initial_group_id
        self.result: PasswordCommand | None = None
        dpi = dpi_context_for(parent)
        self.title("编辑密码" if original else "新增密码")
        self.geometry(dpi.physical_geometry("680x610"))
        self.minsize(dpi.dp(620), dpi.dp(560))
        self.transient(parent)
        configure_dialog_surface(self)

        self.name_var = tk.StringVar(value=original.name if original else "")
        self.username_var = tk.StringVar(value=original.username if original else "")
        self.password_var = tk.StringVar(value=original.password if original else "")
        self.url_var = tk.StringVar(value=original.url if original else "")
        self.pinned_var = tk.BooleanVar(value=original.pinned if original else False)
        self.favorite_var = tk.BooleanVar(value=original.favorite if original else False)
        self.password_visible = False

        frame = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 20))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(
            frame,
            text="编辑密码记录" if original else "新增密码记录",
            style="HeaderTitle.TLabel",
            font=(UI_FONT, 15, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        fields = (
            ("名称/服务（选填）", self.name_var),
            ("用户名", self.username_var),
        )
        for row, (label, variable) in enumerate(fields, start=1):
            ttk.Label(frame, text=label, style="Form.TLabel").grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", pady=6)

        ttk.Label(frame, text="密码", style="Form.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        self.password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=3, column=1, sticky="ew", pady=6)
        self.reveal_button = ttk.Button(frame, text="显示", command=self.toggle_password, style="Quiet.TButton", width=7)
        self.reveal_button.grid(row=3, column=2, padx=(8, 0), pady=6)

        ttk.Label(frame, text="网址（选填）", style="Form.TLabel").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=self.url_var).grid(row=4, column=1, columnspan=2, sticky="ew", pady=6)

        generator = PasswordGeneratorPanel(frame, self.password_var)
        generator.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 8))

        ttk.Label(frame, text="备注（选填）", style="Form.TLabel").grid(row=6, column=0, sticky="nw", pady=6)
        self.notes_text = tk.Text(
            frame,
            height=7,
            wrap="word",
            font=(UI_FONT, 10),
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
        )
        self.notes_text.grid(row=6, column=1, columnspan=2, sticky="nsew", pady=6)
        if original:
            self.notes_text.insert("1.0", original.notes)
        frame.rowconfigure(6, weight=1)

        ttk.Checkbutton(frame, text="收藏", variable=self.favorite_var).grid(
            row=7, column=1, sticky="w", pady=(5, 0)
        )
        ttk.Checkbutton(frame, text="置顶显示", variable=self.pinned_var).grid(
            row=7, column=2, sticky="w", pady=(5, 0)
        )
        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="取消", command=self.destroy, style="Secondary.TButton").grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(buttons, text="保存", command=self.submit, style="Primary.TButton").grid(row=0, column=1)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_dialog(self, parent)
        self.grab_set()

    def toggle_password(self) -> None:
        self.password_visible = not self.password_visible
        self.password_entry.configure(show="" if self.password_visible else "*")
        self.reveal_button.configure(text="隐藏" if self.password_visible else "显示")

    def submit(self) -> None:
        try:
            url = normalise_password_url(self.url_var.get())
            group_ids = (
                tuple(self.original.group_ids)
                if self.original
                else (self.initial_group_id or PASSWORD_DEFAULT_GROUP_ID,)
            )
            name = self.name_var.get()
            username = self.username_var.get()
            password = self.password_var.get()
            notes = self.notes_text.get("1.0", "end-1c")
            pinned = self.pinned_var.get()
            favorite = self.favorite_var.get()
            candidate = PasswordEntry(
                id=self.original.id if self.original else "preview",
                name=name,
                username=username,
                password=password,
                url=url,
                notes=notes,
                pinned=pinned,
                group_ids=list(group_ids),
                favorite=favorite,
            )
            candidate.validate()
        except ValueError as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        if self.original:
            self.result = UpdatePasswordCommand(username, password, name, url, notes, pinned, group_ids, favorite)
        else:
            self.result = CreatePasswordCommand(username, password, name, url, notes, pinned, group_ids, favorite)
        self.destroy()

    @classmethod
    def ask(
        cls,
        parent: Any,
        original: PasswordEntry | None = None,
        initial_group_id: str | None = None,
    ) -> PasswordCommand | None:
        dialog = cls(parent, original, initial_group_id)
        parent.wait_window(dialog)
        return dialog.result
