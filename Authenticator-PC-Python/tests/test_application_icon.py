"""Regression coverage for the actual Windows taskbar window icons."""

import ctypes
import os
import tkinter as tk
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from presentation.application_icon import APP_USER_MODEL_ID, configure_application_identity, set_window_icon


@pytest.mark.skipif(os.name != "nt", reason="Windows shell identity")
def test_process_identity_uses_stable_application_id(monkeypatch):
    set_identity = Mock(return_value=0)
    shell = SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=set_identity)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: shell)
    assert configure_application_identity()
    set_identity.assert_called_once_with(APP_USER_MODEL_ID)
    assert set_identity.argtypes == [ctypes.c_wchar_p]


@pytest.mark.skipif(os.name != "nt", reason="Windows shell identity")
def test_identity_failure_does_not_prevent_startup(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise OSError("shell unavailable")

    monkeypatch.setattr(ctypes, "WinDLL", unavailable)
    assert not configure_application_identity()


@pytest.mark.skipif(os.name != "nt", reason="Windows native window handles")
def test_main_and_compact_windows_have_explicit_small_and_large_icons():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    root = tk.Tk()
    root.withdraw()
    try:
        set_window_icon(root, default=True)
        compact = tk.Toplevel(root)
        compact.withdraw()
        set_window_icon(compact)
        root.update_idletasks()
        for window in (root, compact):
            hwnd = user32.GetParent(window.winfo_id())
            assert hwnd
            # WM_GETICON: both taskbar/Alt+Tab (large) and titlebar (small).
            assert user32.SendMessageW(hwnd, 0x7F, 0, 0)
            assert user32.SendMessageW(hwnd, 0x7F, 1, 0)
            assert window.icon_image is not None
            native = window._native_application_icon
            assert len(native._icons) == 1
            expected = next(iter(native._icons.values()))
            assert tuple(user32.SendMessageW(hwnd, 0x7F, kind, 0) for kind in (0, 1)) == expected
            native.apply()
            assert len(native._icons) == 1  # repeated mapping reuses handles
    finally:
        root.destroy()
    assert not native._icons  # release native icon resources on shutdown
