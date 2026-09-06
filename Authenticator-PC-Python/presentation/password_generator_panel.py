"""Reusable Tk panel for configuring the domain password generator."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from domain.passwords import PasswordGeneratorOptions, generate_password
from presentation.constants import APP_NAME


class PasswordGeneratorPanel(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc, target: tk.StringVar) -> None:
        super().__init__(parent, text="密码生成器", padding=(12, 9), style="Generator.TLabelframe")
        self.target = target
        self.length_var = tk.IntVar(value=20)
        self.lowercase_var = tk.BooleanVar(value=True)
        self.uppercase_var = tk.BooleanVar(value=True)
        self.digits_var = tk.BooleanVar(value=True)
        self.symbols_var = tk.BooleanVar(value=True)
        self.ambiguous_var = tk.BooleanVar(value=True)

        ttk.Label(self, text="长度", style="Form.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(self, from_=8, to=128, textvariable=self.length_var, width=6).grid(
            row=0, column=1, sticky="w", padx=(7, 14)
        )
        options = (
            ("小写", self.lowercase_var),
            ("大写", self.uppercase_var),
            ("数字", self.digits_var),
            ("符号", self.symbols_var),
            ("排除易混淆字符", self.ambiguous_var),
        )
        for column, (label, variable) in enumerate(options, start=2):
            ttk.Checkbutton(self, text=label, variable=variable).grid(row=0, column=column, padx=4)
        ttk.Button(self, text="生成", command=self.generate, style="Secondary.TButton").grid(
            row=0, column=7, padx=(12, 0)
        )

    def generate(self) -> None:
        try:
            options = PasswordGeneratorOptions(
                length=int(self.length_var.get()),
                lowercase=self.lowercase_var.get(),
                uppercase=self.uppercase_var.get(),
                digits=self.digits_var.get(),
                symbols=self.symbols_var.get(),
                exclude_ambiguous=self.ambiguous_var.get(),
            )
            self.target.set(generate_password(options))
        except (ValueError, tk.TclError) as error:
            messagebox.showwarning(APP_NAME, str(error), parent=self.winfo_toplevel())
