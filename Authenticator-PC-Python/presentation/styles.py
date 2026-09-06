"""Tkinter 主题色、字体令牌和 ttk 样式注册。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from presentation.dpi import DpiContext

# 颜色常量按“背景/表面/文本/动作/状态”分组；窗口和对话框都应复用而非写死颜色。
UI_FONT = "Microsoft YaHei UI"
WINDOW_BG = "#F3F6FB"
HEADER_BG = "#FBFCFF"
GLASS_SURFACE = "#FFFFFF"
GLASS_SURFACE_MUTED = "#F5F7FB"
GLASS_BORDER = "#DCE3ED"
GLASS_SHADOW = "#D1D9E5"
TEXT_PRIMARY = "#152033"
TEXT_MUTED = "#66748A"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
SECURE = "#17877B"
SECURE_HOVER = "#0F7168"
DANGER = "#C64653"
DANGER_HOVER = "#A93442"
SELECTION = "#E8F0FF"
PINNED_SURFACE = "#FFF8E8"
INVALID_TEXT = "#B22F3C"


def configure_dialog_surface(window: tk.Toplevel) -> None:
    """为任意对话框应用与主窗口一致的背景色。"""

    window.configure(background=WINDOW_BG)


def center_dialog(window: tk.Toplevel, parent: tk.Misc | None = None) -> None:
    """将普通弹窗居中到父窗口，并限制在当前虚拟桌面范围内。

    Tk 在没有显式位置时通常把 ``Toplevel`` 放到屏幕左上角。所有普通
    模态窗口统一通过这里定位，避免分组、设置和编辑对话框各自重复实现
    位置计算。调用时窗口内容应已创建，这样 ``reqwidth/reqheight`` 才准确。
    """

    owner = parent or window.master
    try:
        # Windows 的 ``geometry(+x+y)`` 使用客户区坐标，需扣除标题栏/边框
        # 偏移后才能让 Toplevel 的可见外框与父窗口真正同心。
        window.update_idletasks()
        decoration_x = window.winfo_rootx() - window.winfo_x()
        decoration_y = window.winfo_rooty() - window.winfo_y()
        # 在测量和移动期间隐藏窗口，避免用户看到从左上角跳到中心的瞬间。
        window.withdraw()
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        if width <= 1:
            width = window.winfo_reqwidth()
        if height <= 1:
            height = window.winfo_reqheight()
        if owner is not None and owner.winfo_exists():
            owner.update_idletasks()
            owner_x = owner.winfo_rootx()
            owner_y = owner.winfo_rooty()
            owner_width = owner.winfo_width()
            owner_height = owner.winfo_height()
            if owner_width <= 1:
                owner_width = owner.winfo_reqwidth()
            if owner_height <= 1:
                owner_height = owner.winfo_reqheight()
            x = owner_x + (owner_width - width) // 2
            y = owner_y + (owner_height - height) // 2
        else:
            x = (window.winfo_screenwidth() - width) // 2
            y = (window.winfo_screenheight() - height) // 2

        # 使用虚拟桌面边界处理多显示器；父窗口在某个显示器时仍优先保持其中心。
        virtual_x = window.winfo_vrootx()
        virtual_y = window.winfo_vrooty()
        virtual_width = window.winfo_vrootwidth()
        virtual_height = window.winfo_vrootheight()
        x = max(virtual_x, min(x, virtual_x + virtual_width - width)) - decoration_x
        y = max(virtual_y, min(y, virtual_y + virtual_height - height)) - decoration_y
        window.geometry(f"+{x}+{y}")
        window.deiconify()
        window.lift()
    except tk.TclError:
        # 窗口可能在后台任务完成前被关闭，定位失败不应影响业务流程。
        return


def configure_app_style(root: Any, dpi_context: DpiContext | None = None) -> None:
    """在 Tk 根窗口注册应用级 ttk 样式和 Combobox 下拉列表选项。"""

    dpi = dpi_context or DpiContext()
    px = dpi.dp
    root.configure(background=WINDOW_BG)
    root.option_add("*TCombobox*Listbox.background", GLASS_SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECTION)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.font", (UI_FONT, 10))
    # ``clam`` 在 Windows 上对颜色、边框和禁用状态的可控性优于系统主题。
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("App.TFrame", background=WINDOW_BG)
    style.configure("Glass.TFrame", background=GLASS_SURFACE)
    style.configure("Dialog.TFrame", background=GLASS_SURFACE)
    style.configure("Header.TFrame", background=HEADER_BG)
    style.configure("Footer.TFrame", background=HEADER_BG)
    style.configure("HeaderIcon.TLabel", background=HEADER_BG)
    style.configure("HeaderTitle.TLabel", background=HEADER_BG, foreground=TEXT_PRIMARY, font=(UI_FONT, 20, "bold"))
    style.configure("HeaderSub.TLabel", background=HEADER_BG, foreground=TEXT_MUTED, font=(UI_FONT, 9))
    style.configure("TLabel", background=GLASS_SURFACE, foreground=TEXT_PRIMARY, font=(UI_FONT, 10))
    style.configure("Form.TLabel", background=GLASS_SURFACE, foreground=TEXT_PRIMARY, font=(UI_FONT, 10))
    style.configure("DialogMuted.TLabel", background=GLASS_SURFACE, foreground=TEXT_MUTED, font=(UI_FONT, 9))
    style.configure("SearchLabel.TLabel", background=GLASS_SURFACE, foreground=TEXT_PRIMARY, font=(UI_FONT, 10, "bold"))
    style.configure("Detail.TLabel", background=GLASS_SURFACE, foreground=TEXT_MUTED, font=(UI_FONT, 9))
    style.configure("ListTitle.TLabel", background=GLASS_SURFACE, foreground=TEXT_PRIMARY, font=(UI_FONT, 12, "bold"))
    style.configure("Ready.TLabel", background=HEADER_BG, foreground="#16A34A", font=(UI_FONT, 10, "bold"))
    style.configure("FooterStatus.TLabel", background=HEADER_BG, foreground=TEXT_PRIMARY, font=(UI_FONT, 9))
    style.configure("FooterDetail.TLabel", background=HEADER_BG, foreground=TEXT_MUTED, font=(UI_FONT, 8))
    style.configure("TButton", font=(UI_FONT, 9), relief="flat", borderwidth=0)
    style.configure(
        "Secondary.TButton", padding=(px(14), px(8)), background=GLASS_SURFACE,
        foreground=TEXT_PRIMARY, bordercolor=GLASS_BORDER, lightcolor=GLASS_SURFACE,
        darkcolor=GLASS_BORDER, focusthickness=1, focuscolor=ACCENT,
    )
    style.map(
        "Secondary.TButton",
        background=[("disabled", GLASS_SURFACE_MUTED), ("pressed", "#E8F0F2"), ("active", "#F4F8F9")],
        foreground=[("disabled", "#9AABB1"), ("!disabled", TEXT_PRIMARY)],
        bordercolor=[("focus", ACCENT), ("active", "#C7DADF"), ("!disabled", GLASS_BORDER)],
    )
    style.configure(
        "Primary.TButton", padding=(px(16), px(8)), background=ACCENT, foreground="#FFFFFF",
        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
        focusthickness=1, focuscolor=ACCENT,
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", "#B9D4F2"), ("pressed", "#0B5FBD"), ("active", ACCENT_HOVER)],
        foreground=[("disabled", "#F7FBFF"), ("!disabled", "#FFFFFF")],
        bordercolor=[("focus", ACCENT), ("!disabled", ACCENT)],
    )
    style.configure(
        "Secure.TButton", padding=(px(14), px(8)), background=SECURE, foreground="#FFFFFF",
        bordercolor=SECURE, lightcolor=SECURE, darkcolor=SECURE,
    )
    style.map(
        "Secure.TButton",
        background=[("disabled", "#B9D9D4"), ("pressed", "#0D655D"), ("active", SECURE_HOVER)],
        foreground=[("disabled", "#F7FBFB"), ("!disabled", "#FFFFFF")],
    )
    style.configure(
        "Danger.TButton", padding=(px(14), px(8)), background=GLASS_SURFACE,
        foreground=DANGER, bordercolor="#E8C8CD", lightcolor=GLASS_SURFACE,
        darkcolor="#E8C8CD",
    )
    style.map(
        "Danger.TButton",
        background=[("disabled", GLASS_SURFACE_MUTED), ("pressed", "#F8E8EA"), ("active", "#FDF1F2")],
        foreground=[("disabled", "#CFA1A8"), ("!disabled", DANGER_HOVER)],
        bordercolor=[("focus", DANGER), ("active", "#E0B9BF"), ("!disabled", "#E8C8CD")],
    )
    style.configure(
        "Quiet.TButton", padding=(px(12), px(8)), background=GLASS_SURFACE_MUTED,
        foreground=TEXT_MUTED, bordercolor=GLASS_SURFACE_MUTED,
        lightcolor=GLASS_SURFACE_MUTED, darkcolor=GLASS_SURFACE_MUTED,
    )
    style.map(
        "Quiet.TButton",
        background=[("disabled", GLASS_SURFACE_MUTED), ("pressed", "#E4EFF1"), ("active", "#EAF2F4")],
        foreground=[("disabled", "#AAB8BD"), ("!disabled", TEXT_PRIMARY)],
    )
    style.configure(
        "HeaderAction.TButton", padding=(px(11), px(8)), background=HEADER_BG,
        foreground=TEXT_PRIMARY, bordercolor=GLASS_BORDER, borderwidth=1,
        lightcolor=HEADER_BG, darkcolor=GLASS_BORDER,
    )
    style.map(
        "HeaderAction.TButton",
        background=[("disabled", GLASS_SURFACE_MUTED), ("pressed", "#E8EEF8"), ("active", "#F3F6FB")],
        foreground=[("disabled", "#A1AABA"), ("!disabled", TEXT_PRIMARY)],
        bordercolor=[("focus", ACCENT), ("active", "#C9D5E6"), ("!disabled", GLASS_BORDER)],
    )
    style.configure(
        "HeaderIcon.TButton", padding=(px(9), px(8)), background=HEADER_BG,
        bordercolor=GLASS_BORDER, borderwidth=1, lightcolor=HEADER_BG, darkcolor=GLASS_BORDER,
    )
    style.map(
        "HeaderIcon.TButton",
        background=[("pressed", "#E8EEF8"), ("active", "#F3F6FB")],
        bordercolor=[("focus", ACCENT), ("!disabled", GLASS_BORDER)],
    )
    style.configure(
        "VaultUnlocked.TButton", padding=(px(11), px(8)), background=HEADER_BG,
        foreground=TEXT_PRIMARY, bordercolor=GLASS_BORDER, borderwidth=1,
        relief="flat", lightcolor=HEADER_BG, darkcolor=GLASS_BORDER,
    )
    style.map(
        "VaultUnlocked.TButton",
        background=[("disabled", GLASS_SURFACE_MUTED), ("pressed", "#E8EEF8"), ("active", "#F3F6FB")],
        foreground=[("disabled", "#A1AABA"), ("!disabled", TEXT_PRIMARY)],
        bordercolor=[("focus", ACCENT), ("active", "#C9D5E6"), ("!disabled", GLASS_BORDER)],
    )
    style.configure(
        "VaultLocked.TButton", padding=(px(11), px(8)), background="#FFF0F2",
        foreground="#A9283C", bordercolor="#E16A7A", borderwidth=1,
        relief="raised", lightcolor="#FFFFFF", darkcolor="#F2B8C1",
    )
    style.map(
        "VaultLocked.TButton",
        background=[("pressed", "#FFE0E5"), ("active", "#FFE8EC")],
        foreground=[("!disabled", "#A9283C")],
        bordercolor=[("focus", "#C64653"), ("!disabled", "#E16A7A")],
    )
    style.configure(
        "TEntry", padding=(px(11), px(8)), fieldbackground=GLASS_SURFACE,
        foreground=TEXT_PRIMARY, bordercolor=GLASS_BORDER, lightcolor=GLASS_SURFACE,
        darkcolor=GLASS_BORDER, insertcolor=TEXT_PRIMARY,
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", GLASS_SURFACE_MUTED), ("readonly", GLASS_SURFACE_MUTED)],
        foreground=[("disabled", "#92A2A8"), ("!disabled", TEXT_PRIMARY)],
        bordercolor=[("focus", ACCENT), ("!disabled", GLASS_BORDER)],
    )
    style.configure(
        "Search.TEntry", padding=(px(13), px(9)), fieldbackground=GLASS_SURFACE_MUTED,
        foreground=TEXT_PRIMARY, bordercolor="#D0E0E4", font=(UI_FONT, 10),
    )
    style.map("Search.TEntry", bordercolor=[("focus", ACCENT), ("!disabled", "#D0E0E4")])
    style.configure(
        "CompactClipboard.TLabel", padding=(px(4), 0, 0, 0), background=GLASS_SURFACE,
        foreground=TEXT_PRIMARY, font=(UI_FONT, 10),
    )
    style.configure(
        "CompactClipboard.TEntry", padding=(px(8), px(2)), fieldbackground=GLASS_SURFACE_MUTED,
        foreground=TEXT_PRIMARY, bordercolor="#D0E0E4", font=(UI_FONT, 10),
    )
    style.map("CompactClipboard.TEntry", bordercolor=[("focus", ACCENT), ("!disabled", "#D0E0E4")])
    style.configure(
        "TopmostOff.TButton", padding=(px(10), px(6)), background=GLASS_SURFACE_MUTED,
        foreground=TEXT_PRIMARY, borderwidth=0, relief="flat",
        lightcolor=GLASS_SURFACE_MUTED, darkcolor=GLASS_SURFACE_MUTED,
    )
    style.map(
        "TopmostOff.TButton", background=[("pressed", "#E4EFF1"), ("active", "#EAF2F4")],
        foreground=[("!disabled", TEXT_PRIMARY)],
    )
    style.configure(
        "TopmostOn.TButton", padding=(px(10), px(6)), background="#E8F3FF",
        foreground="#0D4E8B", borderwidth=1, relief="raised", bordercolor=ACCENT,
        lightcolor="#FFFFFF", darkcolor="#B8D2EC",
    )
    style.map(
        "TopmostOn.TButton", background=[("pressed", "#D9ECFF"), ("active", "#E0F0FF")],
        foreground=[("!disabled", "#0D4E8B")],
        bordercolor=[("focus", ACCENT), ("!disabled", ACCENT)],
    )
    style.configure(
        "ModuleInactive.TButton", padding=(px(18), px(7)), background=GLASS_SURFACE_MUTED,
        foreground=TEXT_MUTED, borderwidth=0, relief="flat",
    )
    style.map(
        "ModuleInactive.TButton",
        background=[("active", "#E8F0F2"), ("pressed", "#DDEBED")],
        foreground=[("!disabled", TEXT_MUTED)],
    )
    style.configure(
        "ModuleActive.TButton", padding=(px(18), px(7)), background="#E8F3FF",
        foreground="#0D4E8B", borderwidth=1, relief="raised", bordercolor=ACCENT,
        lightcolor="#FFFFFF", darkcolor="#B8D2EC",
    )
    style.map(
        "ModuleActive.TButton",
        background=[("active", "#E0F0FF"), ("pressed", "#D9ECFF")],
        foreground=[("!disabled", "#0D4E8B")], bordercolor=[("!disabled", ACCENT)],
    )
    style.configure(
        "TCombobox", padding=(px(9), px(7)), fieldbackground=GLASS_SURFACE,
        foreground=TEXT_PRIMARY, background=GLASS_SURFACE_MUTED,
        bordercolor=GLASS_BORDER, arrowsize=px(15),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", GLASS_SURFACE), ("disabled", GLASS_SURFACE_MUTED)],
        foreground=[("disabled", "#92A2A8"), ("!disabled", TEXT_PRIMARY)],
        bordercolor=[("focus", ACCENT), ("!disabled", GLASS_BORDER)],
        background=[("active", "#E9F1F3"), ("!disabled", GLASS_SURFACE_MUTED)],
    )
    style.configure(
        "TSpinbox", padding=(px(8), px(6)), fieldbackground=GLASS_SURFACE,
        foreground=TEXT_PRIMARY, bordercolor=GLASS_BORDER, arrowsize=px(13),
    )
    style.map(
        "TSpinbox", fieldbackground=[("disabled", GLASS_SURFACE_MUTED)],
        bordercolor=[("focus", ACCENT), ("!disabled", GLASS_BORDER)],
    )
    style.configure("TCheckbutton", background=GLASS_SURFACE, foreground=TEXT_PRIMARY, font=(UI_FONT, 9), padding=(0, px(4)))
    style.map(
        "TCheckbutton", background=[("active", GLASS_SURFACE)],
        foreground=[("disabled", "#9AABB1"), ("!disabled", TEXT_PRIMARY)],
        indicatorcolor=[("selected", ACCENT), ("!selected", GLASS_SURFACE)],
    )
    style.configure(
        "Generator.TLabelframe",
        background=GLASS_SURFACE,
        bordercolor=GLASS_BORDER,
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "Generator.TLabelframe.Label",
        background=GLASS_SURFACE,
        foreground=TEXT_PRIMARY,
        font=(UI_FONT, 9, "bold"),
    )
    style.configure(
        "Treeview", background=GLASS_SURFACE, fieldbackground=GLASS_SURFACE,
        foreground=TEXT_PRIMARY, rowheight=px(38), font=(UI_FONT, 10),
        borderwidth=0, relief="flat",
    )
    style.configure(
        "Treeview.Heading", background=GLASS_SURFACE_MUTED, foreground=TEXT_MUTED,
        font=(UI_FONT, 9, "bold"), padding=(px(12), px(11)), relief="flat", bordercolor=GLASS_BORDER,
    )
    style.map("Treeview", background=[("selected", SELECTION)], foreground=[("selected", "#0D4E8B")])
    style.map("Treeview.Heading", background=[("active", "#E8F0F2")], foreground=[("active", TEXT_PRIMARY)])
    style.configure(
        "Glass.Vertical.TScrollbar", background="#D7E4E7", troughcolor=GLASS_SURFACE,
        bordercolor=GLASS_SURFACE, arrowcolor=TEXT_MUTED, relief="flat",
    )
    style.map("Glass.Vertical.TScrollbar", background=[("active", "#BFD0D5"), ("pressed", "#AAC0C6")])
    style.configure("Status.TLabel", background=HEADER_BG, foreground=TEXT_MUTED, padding=(px(22), px(9)), font=(UI_FONT, 9))
    style.configure(
        "SearchSummary.TLabel", background="#E5F0FC", foreground=ACCENT,
        padding=(px(10), px(7)), font=(UI_FONT, 9, "bold"),
    )
