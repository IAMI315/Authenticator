"""账号新增/编辑对话框，负责收集 UI 输入并构造 ``OTPEntry``。"""

from __future__ import annotations

import tkinter as tk
import uuid
from tkinter import messagebox, ttk
from typing import Any

from application.import_export import QrImportPayload
from domain.entities import DEFAULT_GROUP_ID, TYPE_LABELS, OTPEntry
from domain.identifiers import normalise_issuer_name
from domain.validators import ALGORITHMS, infer_secret_encoding, utc_now_iso
from presentation.constants import APP_NAME
from presentation.qr_scan_flow import QrScanFlow
from presentation.styles import center_dialog, configure_dialog_surface

# UI 显示值与领域内部值的双向映射；领域层仍是最终校验者。
TYPE_FROM_LABEL = {label: value for value, label in TYPE_LABELS.items()}
ENCODING_LABELS = {"auto": "自动识别", "base32": "Base32", "hex": "十六进制"}
ENCODING_FROM_LABEL = {label: value for value, label in ENCODING_LABELS.items()}


class EntryDialog(tk.Toplevel):
    """账号编辑表单及其二维码扫码回填流程。

    ``result`` 为确认后通过 ``ask`` 返回的 ``OTPEntry``，取消时保持 ``None``。
    对话框只构造/校验实体，实际写入始终由主窗口的 ``AccountService`` 完成。
    """

    def __init__(
        self,
        parent: Any,
        entry: OTPEntry | None = None,
        issuer_options: list[str] | None = None,
        default_issuer: str = "",
    ) -> None:
        """根据可选旧实体初始化表单，创建类型、编码、周期和算法控件。"""

        super().__init__(parent)
        self.result: OTPEntry | None = None
        self.original = entry
        self._root_controller: Any = getattr(parent, "app", parent)
        self._qr_scan_flow = QrScanFlow(
            self,
            self._root_controller.qr_scanner,
            self._root_controller.background_tasks,
        )
        self.title("编辑账号" if entry else "新增账号")
        self.resizable(False, False)
        self.transient(parent)
        configure_dialog_surface(self)

        form = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 22))
        form.grid(sticky="nsew")
        initial_issuer = entry.issuer if entry else default_issuer
        self.issuer_var = tk.StringVar(value=normalise_issuer_name(initial_issuer))
        self.account_var = tk.StringVar(value=entry.account if entry else "")
        self.secret_var = tk.StringVar(value=entry.secret if entry else "")
        self.type_var = tk.StringVar(value=TYPE_LABELS[entry.otp_type] if entry else TYPE_LABELS["totp"])
        self.encoding_var = tk.StringVar(
            value=ENCODING_LABELS[entry.secret_encoding] if entry else ENCODING_LABELS["auto"]
        )
        self.period_var = tk.StringVar(value=str(entry.period if entry else 30))
        self.counter_var = tk.StringVar(value=str(entry.counter if entry else 0))
        self.digits_var = tk.StringVar(value=str(entry.digits if entry else 6))
        self.algorithm_var = tk.StringVar(value=entry.algorithm if entry else "SHA1")
        self.pinned_var = tk.BooleanVar(value=entry.pinned if entry else False)
        self.favorite_var = tk.BooleanVar(value=entry.favorite if entry else False)

        # 元组含义为“中文标签、绑定变量、是否使用服务商可编辑下拉框”。
        fields: list[tuple[str, tk.Variable, bool]] = [
            ("服务商", self.issuer_var, True),
            ("账号名称", self.account_var, False),
            ("密钥", self.secret_var, False),
        ]
        for row, (label, variable, is_issuer) in enumerate(fields):
            ttk.Label(form, text=label, style="Form.TLabel").grid(row=row, column=0, sticky="w", pady=6)
            widget: Any
            if is_issuer:
                widget = ttk.Combobox(
                    form,
                    textvariable=variable,
                    values=issuer_options or (),
                    width=39,
                    state="normal",
                )
            elif label == "密钥":
                secret_row = ttk.Frame(form, style="Dialog.TFrame")
                secret_row.columnconfigure(0, weight=1)
                widget = ttk.Entry(secret_row, textvariable=variable, width=31, show="")
                widget.grid(row=0, column=0, sticky="ew")
                self.scan_button = ttk.Button(
                    secret_row,
                    text="扫码识别",
                    command=self.scan_qr_code,
                    style="Secondary.TButton",
                )
                self.scan_button.grid(row=0, column=1, padx=(8, 0))
                widget = secret_row
            else:
                widget = ttk.Entry(form, textvariable=variable, width=42, show="")
            widget.grid(row=row, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="验证码类型", style="Form.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        type_box = ttk.Combobox(
            form,
            textvariable=self.type_var,
            values=list(TYPE_LABELS.values()),
            width=39,
            state="readonly",
        )
        type_box.grid(row=3, column=1, sticky="ew", pady=6)
        type_box.bind("<<ComboboxSelected>>", self._update_type_controls)

        ttk.Label(form, text="密钥编码", style="Form.TLabel").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Combobox(
            form,
            textvariable=self.encoding_var,
            values=list(ENCODING_LABELS.values()),
            width=39,
            state="readonly",
        ).grid(row=4, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="周期（秒）", style="Form.TLabel").grid(row=5, column=0, sticky="w", pady=6)
        self.period_entry = ttk.Spinbox(form, from_=1, to=86_400, textvariable=self.period_var, width=12)
        self.period_entry.grid(row=5, column=1, sticky="w", pady=6)

        ttk.Label(form, text="计数器", style="Form.TLabel").grid(row=6, column=0, sticky="w", pady=6)
        self.counter_entry = ttk.Spinbox(form, from_=0, to=9_223_372_036_854_775_807, textvariable=self.counter_var, width=18)
        self.counter_entry.grid(row=6, column=1, sticky="w", pady=6)

        ttk.Label(form, text="验证码位数", style="Form.TLabel").grid(row=7, column=0, sticky="w", pady=6)
        ttk.Combobox(form, textvariable=self.digits_var, values=("6", "7", "8"), width=12, state="readonly").grid(
            row=7, column=1, sticky="w", pady=6
        )

        ttk.Label(form, text="算法", style="Form.TLabel").grid(row=8, column=0, sticky="w", pady=6)
        ttk.Combobox(form, textvariable=self.algorithm_var, values=ALGORITHMS, width=12, state="readonly").grid(
            row=8, column=1, sticky="w", pady=6
        )

        ttk.Checkbutton(form, text="收藏账号", variable=self.favorite_var).grid(
            row=9, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(form, text="置顶显示", variable=self.pinned_var).grid(
            row=9, column=1, sticky="w", pady=(8, 0)
        )

        button_row = ttk.Frame(form, style="Dialog.TFrame")
        button_row.grid(row=10, column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(button_row, text="取消", command=self.cancel, style="Secondary.TButton").grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text="保存", command=self.submit, style="Primary.TButton").grid(row=0, column=1)

        form.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda _event: self.submit())
        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._update_type_controls()
        center_dialog(self, parent)
        self.grab_set()

    def scan_qr_code(self) -> None:
        """调用共享扫码模块，并在普通 OTP 成功后回填表单。"""

        self._qr_scan_flow.start(
            (self.master, self),
            self._apply_scanned_entry,
            self._handle_scan_error,
            on_cancel=self._scan_cancelled,
            on_state_changed=self._update_scan_state,
        )

    def _update_scan_state(self, state: str) -> None:
        """将共享扫码阶段映射为表单按钮状态。"""

        labels = {
            "automatic": "自动识别中...",
            "selecting": "框选二维码",
            "decoding": "识别中...",
        }
        self.scan_button.configure(text=labels.get(state, "识别中..."), state="disabled")

    def _scan_cancelled(self) -> None:
        """用户取消框选后恢复扫码按钮。"""

        if self.winfo_exists():
            self.scan_button.configure(text="扫码识别", state="normal")

    def _apply_scanned_entry(self, decoded: QrImportPayload) -> None:
        """回填单账号；Google 导出二维码则交给主窗口批量导入。"""

        if not self.winfo_exists():
            return
        if decoded.source == "google_authenticator":
            if self._root_controller.add_scanned_payload(decoded):
                self.cancel()
            else:
                self.scan_button.configure(text="扫码识别", state="normal")
            return
        entry = decoded.bundle.otp_entries[0]
        self.issuer_var.set(entry.issuer)
        self.account_var.set(entry.account)
        self.secret_var.set(entry.secret)
        self.type_var.set(TYPE_LABELS[entry.otp_type])
        self.encoding_var.set(ENCODING_LABELS[entry.secret_encoding])
        self.period_var.set(str(entry.period))
        self.counter_var.set(str(entry.counter))
        self.digits_var.set(str(entry.digits))
        self.algorithm_var.set(entry.algorithm)
        self._update_type_controls()
        self.scan_button.configure(text="已识别", state="normal")
        self.after(1600, lambda: self.scan_button.winfo_exists() and self.scan_button.configure(text="扫码识别"))

    def _handle_scan_error(self, error: Exception) -> None:
        """恢复扫码按钮并显示可选依赖缺失或解码失败信息。"""

        if not self.winfo_exists():
            return
        self.scan_button.configure(text="扫码识别", state="normal")
        if isinstance(error, ImportError):
            messagebox.showerror(APP_NAME, "扫码组件未安装，请改用手动输入或重新安装程序。", parent=self)
        else:
            messagebox.showwarning(APP_NAME, f"扫码失败：{error}", parent=self)

    def _update_type_controls(self, _event: tk.Event[Any] | None = None) -> None:
        """按 OTP 类型启用 HOTP 计数器或 TOTP 周期，并固定 Steam 显示设置。"""

        otp_type = TYPE_FROM_LABEL.get(self.type_var.get(), "totp")
        is_hotp = otp_type == "hotp"
        self.period_entry.configure(state="disabled" if is_hotp else "normal")
        self.counter_entry.configure(state="normal" if is_hotp else "disabled")
        if otp_type == "steam":
            self.digits_var.set("6")

    def submit(self) -> None:
        """从表单创建并验证 ``OTPEntry``；失败留在当前对话框并显示错误。"""

        try:
            otp_type = TYPE_FROM_LABEL[self.type_var.get()]
            encoding = ENCODING_FROM_LABEL[self.encoding_var.get()]
            if encoding == "auto":
                encoding = infer_secret_encoding(self.secret_var.get())
            issuer = normalise_issuer_name(self.issuer_var.get())
            if not issuer:
                raise ValueError("请输入服务商")
            entry = OTPEntry(
                id=self.original.id if self.original else str(uuid.uuid4()),
                issuer=issuer,
                account=self.account_var.get().strip(),
                secret=self.secret_var.get(),
                otp_type=otp_type,
                counter=int(self.counter_var.get()),
                period=int(self.period_var.get()),
                digits=int(self.digits_var.get()),
                algorithm=self.algorithm_var.get(),
                secret_encoding=encoding,
                pinned=self.pinned_var.get(),
                created_at=self.original.created_at if self.original else utc_now_iso(),
                group_ids=list(self.original.group_ids) if self.original else [DEFAULT_GROUP_ID],
                favorite=self.favorite_var.get(),
            )
            # Steam 最终固定为 5 字符；Battle.net 新建账号默认 8 位数字。
            if otp_type == "steam":
                entry.digits = 5
            if otp_type == "battle" and not self.original and self.digits_var.get() == "6":
                entry.digits = 8
            entry.validate()
            entry.code()
        except (KeyError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.result = entry
        self.destroy()

    def cancel(self) -> None:
        """关闭对话框并保持 ``result`` 为 ``None``。"""

        self._qr_scan_flow.cancel()
        self.destroy()

    @classmethod
    def ask(
        cls,
        parent: Any,
        entry: OTPEntry | None = None,
        issuer_options: list[str] | None = None,
        default_issuer: str = "",
    ) -> OTPEntry | None:
        """显示模态表单并在窗口关闭后返回确认的实体或 ``None``。"""

        dialog = cls(parent, entry, issuer_options, default_issuer)
        parent.wait_window(dialog)
        return dialog.result
