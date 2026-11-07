"""Application identity and explicit native window icons for Windows taskbars."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any

from infrastructure.paths import resource_path

APP_USER_MODEL_ID = "Authenticator.Desktop.Distribution"


def configure_application_identity() -> bool:
    """Keep this application separate from Python's taskbar group, before Tk starts."""

    if os.name != "nt":
        return False
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        set_identity = shell32.SetCurrentProcessExplicitAppUserModelID
        set_identity.argtypes = [ctypes.c_wchar_p]
        set_identity.restype = ctypes.c_long
        return int(set_identity(APP_USER_MODEL_ID)) == 0
    except (AttributeError, OSError):
        return False


def set_window_icon(window: Any, *, default: bool = False) -> None:
    """Set the current window icon, not just the default for future Tk windows."""

    import tkinter as tk

    try:
        window.icon_image = tk.PhotoImage(master=window, file=str(resource_path("assets/icon.png")))
        window.iconphoto(default, window.icon_image)
    except tk.TclError:
        window.icon_image = None
    if os.name == "nt":
        try:
            icon_path = str(resource_path("assets/icon.ico"))
            if default:
                window.iconbitmap(default=icon_path)
            # Tk's `default=` alone does not reliably set WM_GETICON on the
            # current native wrapper, allowing Explorer to use Python's icon.
            window.iconbitmap(icon_path)
        except tk.TclError:
            pass
        try:
            native_icon = getattr(window, "_native_application_icon", None)
            if native_icon is None:
                native_icon = _WindowsWindowIcon(window)
                window._native_application_icon = native_icon
            native_icon.apply()
        except (AttributeError, OSError):
            pass


class _WindowsWindowIcon:
    """Own DPI-sized HICONs rather than Tk's rescaled small bitmap."""

    def __init__(self, window: Any) -> None:
        self.window = window
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetAncestor.restype = wintypes.HWND
        self.user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        self.user32.GetDpiForWindow.restype = wintypes.UINT
        self.user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
        self.user32.GetSystemMetricsForDpi.restype = ctypes.c_int
        self.user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        self.user32.LoadImageW.restype = wintypes.HANDLE
        self.user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.SendMessageW.restype = ctypes.c_ssize_t
        self.user32.DestroyIcon.argtypes = [wintypes.HICON]
        self.user32.DestroyIcon.restype = wintypes.BOOL
        self._icons: dict[tuple[int, int], tuple[int, int]] = {}
        window.bind("<Map>", self._mapped, add="+")
        window.bind("<Destroy>", self._destroyed, add="+")

    def apply(self) -> None:
        # winfo_id() is Tk's inner window; Explorer uses its outer wrapper.
        hwnd = self.user32.GetAncestor(self.window.winfo_id(), 2)
        if not hwnd:
            return
        dpi = self.user32.GetDpiForWindow(hwnd) or 96
        sizes = (
            self.user32.GetSystemMetricsForDpi(49, dpi),  # SM_CXSMICON
            self.user32.GetSystemMetricsForDpi(11, dpi),  # SM_CXICON
        )
        if sizes not in self._icons:
            icons: list[int] = []
            for size in sizes:
                handle = self.user32.LoadImageW(None, str(resource_path("assets/icon.ico")), 1, size, size, 0x10)
                if not handle:
                    for allocated in icons:
                        self.user32.DestroyIcon(allocated)
                    return
                icons.append(int(handle))
            self._icons[sizes] = (icons[0], icons[1])
        for kind, handle in enumerate(self._icons[sizes]):
            self.user32.SendMessageW(hwnd, 0x80, kind, handle)  # WM_SETICON

    def _mapped(self, event: Any) -> None:
        if event.widget is self.window:
            self.apply()

    def _destroyed(self, event: Any) -> None:
        if event.widget is self.window:
            for icons in self._icons.values():
                for handle in icons:
                    self.user32.DestroyIcon(handle)
            self._icons.clear()
