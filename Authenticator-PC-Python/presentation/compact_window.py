"""轻量悬浮验证码窗口。

该窗口复用 ``MainWindow`` 的搜索、保险库、后台任务和视图模型状态；它不拥有独立
数据副本，因此完整界面和悬浮窗始终显示同一份账号集合。
"""

from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from typing import Any

from domain.entities import OTPEntry
from infrastructure.errors import VaultError
from presentation.application_icon import set_window_icon
from presentation.constants import APP_NAME, COMPACT_WINDOW_SIZE
from presentation.dpi import DpiContext
from presentation.glass_scrollbar import GlassScrollbar
from presentation.qr_scan_flow import QrScanFlow
from presentation.styles import (
    ACCENT,
    GLASS_BORDER,
    GLASS_SURFACE,
    TEXT_PRIMARY,
    UI_FONT,
    configure_dialog_surface,
)
from presentation.tooltip import Tooltip


class CompactAccountRow(tk.Frame):
    """Stable compact account slot whose widgets are updated instead of rebuilt."""

    def __init__(self, parent: tk.Misc, owner: CompactWindow, dpi_context: DpiContext) -> None:
        self.owner = owner
        self.dpi_context = dpi_context
        super().__init__(
            parent,
            background=GLASS_SURFACE,
            highlightthickness=2,
            highlightbackground=GLASS_BORDER,
            highlightcolor=GLASS_BORDER,
            height=dpi_context.dp(72),
        )
        self.grid_propagate(False)
        self.columnconfigure(1, weight=1)
        self.entry: OTPEntry | None = None
        self._account_full = ""
        self._account_font = tkfont.Font(family=UI_FONT, size=9)
        self.provider_var = tk.StringVar()
        self.account_var = tk.StringVar()
        self.code_var = tk.StringVar()
        self.provider_label = tk.Label(
            self,
            textvariable=self.provider_var,
            background=GLASS_SURFACE,
            foreground=TEXT_PRIMARY,
            font=(UI_FONT, 9, "bold"),
            anchor="w",
        )
        self.provider_label.grid(
            row=0, column=0, sticky="w", padx=(dpi_context.dp(10), dpi_context.dp(8)), pady=(dpi_context.dp(8), 0)
        )
        self.account_label = tk.Label(
            self,
            textvariable=self.account_var,
            background=GLASS_SURFACE,
            foreground=TEXT_PRIMARY,
            font=(UI_FONT, 9),
            anchor="e",
            cursor="hand2",
        )
        self.account_label.grid(
            row=0, column=1, sticky="ew", padx=(0, dpi_context.dp(10)), pady=(dpi_context.dp(8), 0)
        )
        self.code_label = tk.Label(
            self,
            textvariable=self.code_var,
            background=GLASS_SURFACE,
            foreground=ACCENT,
            font=(UI_FONT, 15, "bold"),
            anchor="w",
            cursor="hand2",
        )
        self.code_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            padx=dpi_context.dp(10),
            pady=(dpi_context.dp(2), dpi_context.dp(7)),
        )
        self.account_label.bind("<Button-1>", self._copy_account)
        self.code_label.bind("<Button-1>", self._copy_code)
        self.bind("<Configure>", self._fit_account)
        scroll_handler = getattr(self.owner, "_on_accounts_mousewheel", None)
        if scroll_handler is not None:
            for widget in (self, self.provider_label, self.account_label, self.code_label):
                widget.bind("<MouseWheel>", scroll_handler, add="+")
                widget.bind("<Button-4>", scroll_handler, add="+")
                widget.bind("<Button-5>", scroll_handler, add="+")

    def set_highlighted(self, highlighted: bool) -> None:
        """切换稳定边框颜色；边框厚度固定，避免高亮引起行内容位移。"""

        border = ACCENT if highlighted else GLASS_BORDER
        self.configure(highlightbackground=border, highlightcolor=border)

    def set_entry(self, entry: OTPEntry, code: str) -> None:
        self.entry = entry
        self._account_full = entry.account or "-"
        self.provider_var.set(entry.title)
        self.code_var.set(code)
        self._fit_account()

    def update_code(self, code: str) -> None:
        if self.entry is not None and self.code_var.get() != code:
            self.code_var.set(code)

    def clear(self) -> None:
        self.entry = None
        self._account_full = ""
        self.provider_var.set("")
        self.account_var.set("")
        self.code_var.set("")
        self.set_highlighted(False)

    def _fit_account(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if not self._account_full:
            self.account_var.set("")
            return
        available = max(self.dpi_context.dp(100), self.account_label.winfo_width() - self.dpi_context.dp(4))
        if self._account_font.measure(self._account_full) <= available:
            self.account_var.set(self._account_full)
            return
        suffix = "…"
        candidate = self._account_full
        while candidate and self._account_font.measure(candidate + suffix) > available:
            candidate = candidate[:-1]
        self.account_var.set(candidate + suffix)

    def _copy_account(self, _event: tk.Event[Any]) -> str:
        if self.entry is not None:
            self.owner.copy_text(self.entry.account or "-", f"已复制 {self.entry.title} 的账号。")
        return "break"

    def _copy_code(self, _event: tk.Event[Any]) -> str:
        if self.entry is not None:
            self.owner.copy_text(
                self.owner._code_for_entry(self.entry, time.time()),
                f"已复制 {self.entry.title} 的验证码。",
            )
        return "break"


class CompactWindow(tk.Toplevel):
    """用于快速查看、复制和扫码新增账号的小型顶层窗口。

    ``app`` 为主窗口控制器。账号行按 ID 复用并放入滚动视口，倒计时只修改
    文字变量，避免每秒销毁控件造成闪烁。
    """

    def __init__(self, app: Any, *, start_hidden: bool = False) -> None:
        """创建轻量窗口控件；预热时保持隐藏，避免首次切换加载。"""

        super().__init__(app)
        self.app = app
        self._start_hidden = start_hidden
        self._mui_workspace: Any | None = None
        if start_hidden:
            self.withdraw()
        self.dpi_context: DpiContext = app.dpi_context
        self.title("验证器悬浮窗")
        set_window_icon(self)
        self.resizable(False, False)
        self.geometry(self.dpi_context.physical_geometry(COMPACT_WINDOW_SIZE))
        # 标题栏关闭代表退出程序；“完整界面”按钮才负责返回主窗口。
        self.protocol("WM_DELETE_WINDOW", self._close_application)
        configure_dialog_surface(self)
        if self._mount_mui_workspace():
            return
        self._clipboard_click_after: str | None = None
        self._clipboard_editing = False
        self._clipboard_before_edit = ""
        self._images: list[Any] = []
        self._tooltips: list[Tooltip] = []
        self._highlighted_entry_ids: set[str] = set()
        self._highlight_after_id: str | None = None
        self._qr_scan_flow = QrScanFlow(
            self,
            app.qr_scanner,
            app.background_tasks,
        )

        surface = ttk.Frame(
            self,
            style="Dialog.TFrame",
            padding=(self.dpi_context.dp(14), self.dpi_context.dp(12)),
        )
        surface.pack(fill="both", expand=True)
        header = ttk.Frame(surface, style="Dialog.TFrame")
        header.pack(fill="x")
        header.columnconfigure(1, weight=1)
        brand_icon = app.icons.image("app", 22)
        self._images.append(brand_icon)
        ttk.Label(header, image=brand_icon, style="Form.TLabel").grid(row=0, column=0, padx=(0, 7))
        ttk.Label(
            header, text="验证器", style="Form.TLabel", font=(UI_FONT, 13, "bold")
        ).grid(row=0, column=1, sticky="w")
        pin_icon = app.icons.image("topmost", 15)
        expand_icon = app.icons.image("grid", 15)
        self._images.extend((pin_icon, expand_icon))
        self.topmost_button = ttk.Button(
            header,
            text="置顶",
            image=pin_icon,
            compound="left",
            command=app.toggle_always_on_top,
            width=6,
        )
        self.topmost_button.grid(row=0, column=2, padx=(8, 5), sticky="e")
        complete_button = ttk.Button(
            header,
            text="完整界面",
            image=expand_icon,
            compound="left",
            command=app.set_compact_mode,
            style="Quiet.TButton",
        )
        complete_button.grid(row=0, column=3, sticky="e")
        self._tooltips.extend((Tooltip(self.topmost_button, "切换窗口置顶"), Tooltip(complete_button, "返回完整界面")))

        self.search_entry = ttk.Entry(surface, textvariable=app.search_var, style="Search.TEntry")
        self.search_entry.pack(fill="x", pady=(self.dpi_context.dp(9), 0))
        self.search_entry.bind("<Escape>", self._clear_search_event)

        action_row = ttk.Frame(surface, style="Dialog.TFrame")
        action_row.pack(fill="x", pady=(self.dpi_context.dp(8), self.dpi_context.dp(7)))
        scan_icon = app.icons.image("scan-line", 17, "#FFFFFF")
        self._images.append(scan_icon)
        ttk.Button(
            action_row,
            text="扫码新增",
            image=scan_icon,
            compound="left",
            command=self.scan_add,
            style="Primary.TButton",
        ).pack(side="left", fill="x", expand=True)
        add_menu = tk.Menu(self, **app._menu_options())
        add_menu.add_command(label="扫码添加", command=self.scan_add)
        add_menu.add_command(label="手动添加", command=self.manual_add)
        ttk.Menubutton(action_row, text="▾", menu=add_menu, style="Secondary.TButton", width=3).pack(side="left", padx=(6, 0))

        recent_header = ttk.Frame(surface, style="Dialog.TFrame")
        recent_header.pack(fill="x", pady=(0, self.dpi_context.dp(4)))
        recent_header.columnconfigure(1, weight=1)
        ttk.Label(recent_header, text="最近添加", style="DialogMuted.TLabel").grid(row=0, column=0, sticky="w")
        self.clipboard_var = tk.StringVar(value=app.settings.compact_clipboard)
        self.clipboard_display = ttk.Label(
            recent_header,
            textvariable=self.clipboard_var,
            style="CompactClipboard.TLabel",
            anchor="w",
            cursor="hand2",
        )
        self.clipboard_display.grid(row=0, column=1, sticky="new", padx=(10, 0))
        self.clipboard_display.bind("<Button-1>", self._clipboard_single_click)
        self.clipboard_display.bind("<Double-1>", self._clipboard_double_click)
        self.clipboard_entry = ttk.Entry(
            recent_header,
            textvariable=self.clipboard_var,
            style="CompactClipboard.TEntry",
            width=23,
        )
        self.clipboard_entry.bind("<Return>", self._commit_clipboard)
        self.clipboard_entry.bind("<Escape>", self._cancel_clipboard)
        self.clipboard_entry.bind("<FocusOut>", self._commit_clipboard)

        # 先固定底部反馈栏，再让账号列表占用剩余高度；否则 expand 的列表
        # 会吞掉底部空间，导致复制/扫码反馈被遮挡。
        status_host = ttk.Frame(surface, style="Dialog.TFrame", height=self.dpi_context.dp(24))
        status_host.pack(side="bottom", fill="x", pady=(self.dpi_context.dp(3), 0))
        status_host.pack_propagate(False)
        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(
            status_host,
            textvariable=self.status_var,
            style="DialogMuted.TLabel",
            anchor="w",
        )
        self.status_label.pack(fill="both")

        accounts_host = tk.Frame(surface, background=GLASS_SURFACE, highlightthickness=0)
        accounts_host.pack(fill="both", expand=True)
        accounts_host.columnconfigure(0, weight=1)
        accounts_host.rowconfigure(0, weight=1)
        self.accounts_canvas = tk.Canvas(
            accounts_host,
            background=GLASS_SURFACE,
            highlightthickness=0,
            borderwidth=0,
            yscrollincrement=self.dpi_context.dp(5),
        )
        self.accounts_scrollbar = GlassScrollbar(
            accounts_host,
            self.accounts_canvas.yview,
            width=9,
            background=GLASS_SURFACE,
        )
        self.accounts_canvas.configure(yscrollcommand=self.accounts_scrollbar.set)
        self.accounts_canvas.grid(row=0, column=0, sticky="nsew")
        self.accounts_scrollbar.grid(row=0, column=1, sticky="ns", padx=(self.dpi_context.dp(3), 0))
        self.accounts_frame = ttk.Frame(self.accounts_canvas, style="Dialog.TFrame")
        self.accounts_frame.columnconfigure(0, weight=1)
        self.accounts_window_id = self.accounts_canvas.create_window(
            (0, 0), window=self.accounts_frame, anchor="nw"
        )
        self.accounts_frame.bind("<Configure>", self._on_accounts_frame_configure)
        self.accounts_canvas.bind("<Configure>", self._on_accounts_canvas_configure)
        for widget in (self.accounts_canvas, self.accounts_frame):
            widget.bind("<MouseWheel>", self._on_accounts_mousewheel, add="+")
            widget.bind("<Button-4>", self._on_accounts_mousewheel, add="+")
            widget.bind("<Button-5>", self._on_accounts_mousewheel, add="+")
        self.account_rows: dict[str, CompactAccountRow] = {}
        self._account_order: tuple[str, ...] = ()
        self.empty_var = tk.StringVar()
        self.empty_label = ttk.Label(
            self.accounts_frame,
            textvariable=self.empty_var,
            style="DialogMuted.TLabel",
            anchor="center",
        )

        self.update_topmost_button()
        self.refresh()

    def _mount_mui_workspace(self) -> bool:
        """Mount the React/MUI compact surface, retaining Tk as a fallback."""

        if not getattr(self.app, "_mui_requested", False):
            return False
        try:
            from presentation.mui.workspace import MuiWorkspace

            self._mui_workspace = MuiWorkspace(self, self.app, mode="compact")
            self._mui_workspace.pack(fill="both", expand=True)
            self._mui_workspace.set_page_active(not self._start_hidden)
            # Scanner/import callbacks already write to the main status token.
            # Sharing it gives the MUI footer immediate feedback without
            # duplicating sensitive status state in the embedded page.
            self.status_var = self.app.status_var
            return True
        except Exception:
            self._mui_workspace = None
            return False

    def process_mui_requests(self) -> None:
        """Let the main Tk event loop dispatch compact bridge commands."""

        if self._mui_workspace is not None:
            self._mui_workspace.process_requests()

    def close_mui_workspace(self) -> None:
        """Release the compact WebView2 profile before destroying its Toplevel."""

        if self._mui_workspace is None:
            return
        workspace, self._mui_workspace = self._mui_workspace, None
        workspace.close()

    def destroy(self) -> None:
        self.close_mui_workspace()
        super().destroy()

    def _close_application(self) -> None:
        """关闭轻量窗口时退出程序，并由主窗口保存当前模式。"""

        self.app._shutdown()

    def update_topmost_button(self) -> None:
        """根据主窗口共享的置顶状态刷新按钮视觉样式。"""

        if self._mui_workspace is not None:
            return
        self.topmost_button.configure(
            text="置顶",
            style="TopmostOn.TButton" if self.app.window_on_top else "TopmostOff.TButton",
        )

    def present_in_foreground(self) -> None:
        """显示轻量窗并短暂提升层级，避免切换时被其他窗口遮住。

        Windows 对刚从隐藏主窗口创建的 Toplevel 不一定自动授予前台层级。先临时
        置顶可可靠地将用户主动打开的窗口带到前面，随后恢复用户原有的置顶偏好，
        不会意外把普通轻量窗变成常驻置顶窗口。
        """

        preferred_topmost = bool(self.app.window_on_top)
        workspace = getattr(self, "_mui_workspace", None)
        if workspace is not None:
            workspace.set_page_active(True)
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()
        try:
            self.focus_force()
        except tk.TclError:
            # 失焦的窗口在销毁边缘可能拒绝焦点请求，但仍必须恢复置顶偏好。
            pass

        def restore_preference() -> None:
            if not self.winfo_exists():
                return
            self.attributes("-topmost", preferred_topmost)
            self.lift()

        self.after(160, restore_preference)

    def hide_for_full_mode(self) -> None:
        """Hide the reusable compact surface without tearing down WebView2."""

        if self._mui_workspace is not None:
            self._mui_workspace.set_page_active(False)
        self.withdraw()

    def refresh(self) -> None:
        """更新账号列表；倒计时刷新只改行文本并保留滚动位置。"""

        if self._mui_workspace is not None:
            return
        self.app._sync_view_model()
        recent = self.app.compact_view_model.recent_entries()
        next_order = tuple(entry.id for entry in recent)
        structure_changed = next_order != self._account_order
        self._account_order = next_order
        now = time.time()
        if self.app.locked:
            message = "保险库已锁定"
        elif not recent:
            message = "没有符合搜索条件的账号" if self.app.search_var.get().strip() else "暂无账号"
        else:
            message = ""
        if message:
            self.empty_var.set(message)
            self.empty_label.grid(row=0, column=0, sticky="nsew", pady=self.dpi_context.dp(12))
        else:
            self.empty_label.grid_remove()
        visible_ids = set(next_order)
        for index, entry in enumerate(recent):
            row = self.account_rows.get(entry.id)
            if row is None:
                row = CompactAccountRow(self.accounts_frame, self, self.dpi_context)
                self.account_rows[entry.id] = row
            code = self._code_for_entry(entry, now)
            display_code = code if self.app.settings.otp_codes_visible or code == "密钥无效" else "••••••"
            if row.entry is None or row.entry.id != entry.id:
                row.set_entry(entry, display_code)
            else:
                row.entry = entry
                row.update_code(display_code)
            row.set_highlighted(entry.id in self._highlighted_entry_ids)
            row.grid(row=index, column=0, sticky="ew", pady=(0, self.dpi_context.dp(5)))
        for entry_id, row in self.account_rows.items():
            if entry_id not in visible_ids:
                row.clear()
                row.grid_remove()
        self.accounts_canvas.configure(scrollregion=self.accounts_canvas.bbox("all") or (0, 0, 0, 0))
        if structure_changed:
            self.accounts_canvas.yview_moveto(0.0)

    def _on_accounts_frame_configure(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """同步列表滚动区域，不触发布局重建。"""

        if self.accounts_frame.winfo_exists():
            self.accounts_canvas.configure(scrollregion=self.accounts_canvas.bbox("all") or (0, 0, 0, 0))

    def _on_accounts_canvas_configure(self, event: tk.Event[tk.Canvas]) -> None:
        """让列表内容始终填满视口宽度，避免滚动时横向抖动。"""

        self.accounts_canvas.itemconfigure(self.accounts_window_id, width=max(1, event.width))

    def _on_accounts_mousewheel(self, event: tk.Event[Any]) -> str:
        """统一处理行、列表和滚动条上的鼠标滚轮。"""

        if getattr(event, "num", None) == 4:
            units = -1
        elif getattr(event, "num", None) == 5:
            units = 1
        else:
            units = -int(event.delta / 120) if event.delta else 0
        if units:
            self.accounts_canvas.yview_scroll(units, "units")
        return "break"

    def highlight_accounts(self, entry_ids: list[str] | tuple[str, ...] | set[str]) -> None:
        """高亮刚扫码新增且当前可见的账号，五秒后原位恢复普通边框。"""

        if self._mui_workspace is not None:
            self._mui_workspace.bridge.highlight_accounts(entry_ids)
            return
        if self._highlight_after_id is not None:
            try:
                self.after_cancel(self._highlight_after_id)
            except tk.TclError:
                pass
        self._highlighted_entry_ids = set(entry_ids)
        for row in self.account_rows.values():
            row.set_highlighted(
                row.entry is not None and row.entry.id in self._highlighted_entry_ids
            )
        self._highlight_after_id = self.after(5_000, self._clear_account_highlight)

    def _clear_account_highlight(self) -> None:
        """清除扫码成功反馈，不重建账号行。"""

        self._highlight_after_id = None
        self._highlighted_entry_ids.clear()
        for row in self.account_rows.values():
            row.set_highlighted(False)

    @staticmethod
    def _code_for_entry(entry: OTPEntry, now: float) -> str:
        """返回可显示验证码；无效密钥不会破坏整个悬浮窗口刷新。"""

        try:
            return entry.code(now)
        except ValueError:
            return "密钥无效"

    def copy_code(self, code: str, message: str = "已复制验证码。") -> None:
        """复制验证码的语义化快捷入口。"""

        self.copy_text(code, message)

    def copy_text(self, value: str, message: str) -> None:
        """写入系统剪贴板并把结果显示到轻量窗口状态栏。"""

        self.clipboard_clear()
        self.clipboard_append(value)
        self.status_var.set(message)

    def _clipboard_single_click(self, _event: tk.Event[Any]) -> str | None:
        """延迟单击复制，以便双击能取消它并进入编辑模式。"""

        if self._clipboard_editing:
            return None
        if self._clipboard_click_after is not None:
            self.after_cancel(self._clipboard_click_after)
        self._clipboard_click_after = self.after(220, self._copy_clipboard)
        return "break"

    def _copy_clipboard(self) -> None:
        """执行延迟后的常驻剪贴板复制。"""

        self._clipboard_click_after = None
        self.copy_text(self.clipboard_var.get(), "已复制常驻剪贴板内容。")

    def _clipboard_double_click(self, _event: tk.Event[Any]) -> str:
        """取消待执行的单击复制，将只读文本标签替换为编辑框。"""

        if self._clipboard_click_after is not None:
            self.after_cancel(self._clipboard_click_after)
            self._clipboard_click_after = None
        self._clipboard_editing = True
        self._clipboard_before_edit = self.clipboard_var.get()
        self.clipboard_display.grid_remove()
        self.clipboard_entry.grid(
            row=0, column=1, sticky="new", padx=(self.dpi_context.dp(10), 0)
        )
        self.clipboard_entry.focus_set()
        self.clipboard_entry.selection_range(0, "end")
        return "break"

    def _commit_clipboard(self, _event: tk.Event[Any] | None = None) -> str:
        """提交常驻剪贴板文本并尝试保存设置；保存失败保留当前 UI 文本。"""

        if not self._clipboard_editing:
            return "break"
        self._clipboard_editing = False
        self.clipboard_entry.grid_remove()
        self.clipboard_display.configure(text=self.clipboard_var.get())
        self.clipboard_display.grid()
        try:
            self.app.settings.compact_clipboard = self.clipboard_var.get()
            self.app._persist_settings()
        except VaultError:
            self.status_var.set("常驻剪贴板保存失败")
        else:
            self.status_var.set("常驻剪贴板已保存")
        return "break"

    def _cancel_clipboard(self, _event: tk.Event[Any] | None = None) -> str:
        """撤销正在编辑的常驻剪贴板文本，恢复进入编辑前的值。"""

        if self._clipboard_editing:
            self.clipboard_var.set(self._clipboard_before_edit)
            self._clipboard_editing = False
            self.clipboard_entry.grid_remove()
            self.clipboard_display.configure(text=self.clipboard_var.get())
            self.clipboard_display.grid()
        return "break"

    def _clear_search_event(self, _event: tk.Event[Any]) -> str:
        """处理 Escape：清空与主窗口共享的搜索变量并保持焦点。"""

        self.app.search_var.set("")
        self.search_entry.focus_set()
        return "break"

    def manual_add(self) -> None:
        """在主窗口控制器中打开手动新增对话框，结束后恢复悬浮窗前台显示。"""

        self.app.add_account(from_compact=True)
        if self.winfo_exists():
            self.deiconify()
            self.lift()

    def scan_add(self) -> None:
        """调用共享扫码模块；轻量窗口只处理流程状态与成功后的直接入库。"""

        self._qr_scan_flow.start(
            (self,),
            self._apply_scanned_account,
            self._handle_scan_error,
            on_cancel=lambda: self.status_var.set("就绪"),
            on_state_changed=self._update_scan_status,
        )

    def _update_scan_status(self, state: str) -> None:
        """把共享扫码模块的阶段转换为轻量窗口底部状态。"""

        messages = {
            "automatic": "正在识别屏幕二维码...",
            "selecting": "请框选二维码",
            "decoding": "正在识别二维码...",
        }
        self.status_var.set(messages.get(state, "正在识别二维码..."))

    def _apply_scanned_account(self, payload: Any) -> None:
        """在 Tk 主线程将单账号或 Google 批量结果交给主窗口。"""

        if not self.winfo_exists():
            return
        self.app.add_scanned_payload(payload)
        self.refresh()

    def _handle_scan_error(self, error: Exception) -> None:
        """在 Tk 主线程显示扫码失败信息，并区分缺少可选依赖的情况。"""

        if not self.winfo_exists():
            return
        self.status_var.set("扫码失败")
        if isinstance(error, ImportError):
            messagebox.showerror(APP_NAME, "扫码组件未安装，请改用手动输入。", parent=self)
        else:
            messagebox.showwarning(APP_NAME, f"扫码失败：{error}", parent=self)
