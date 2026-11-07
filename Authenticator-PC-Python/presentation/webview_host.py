"""Optional embedded Edge WebView2 host for the server workspace.

The application continues to work when the optional WebView2 integration is
unavailable. This is important for source tests and for older Windows systems
which do not have the Edge WebView2 runtime installed.
"""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
from pathlib import Path
from typing import Any


class WebViewUnavailableError(RuntimeError):
    """Raised when an embedded WebView2 control cannot be created."""


def initialize_webview_com() -> bool:
    """Initialize the UI thread as STA before importing the .NET WebView host."""

    if os.name != "nt":
        return False
    try:
        # COINIT_APARTMENTTHREADED; S_FALSE means the same apartment already
        # exists. RPC_E_CHANGED_MODE deliberately falls back to the browser.
        result = int(ctypes.windll.ole32.CoInitializeEx(None, 0x2))
        return result in (0, 1)
    except (AttributeError, OSError):
        return False


class EdgeWebViewHost(tk.Frame):
    """A Tk frame containing a Chromium-based Edge WebView2 control.

    ``cache_directory`` is intentionally caller-owned so sensitive workspaces
    can use an isolated transient profile instead of the executable-adjacent
    default WebView2 folder.  Server pages keep the backwards-compatible
    default when no directory is supplied.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        cache_directory: Path | None = None,
        allowed_origin: str | None = None,
    ) -> None:
        super().__init__(parent, background="#FFFFFF", borderwidth=0, highlightthickness=0)
        try:
            from tkwebview2.tkwebview2 import WebView2, have_runtime
            from webview.platforms.edgechromium import EdgeChrome
        except Exception as error:  # optional runtime dependency
            raise WebViewUnavailableError("未安装嵌入式网页组件") from error
        try:
            if not have_runtime():
                raise WebViewUnavailableError("未安装 Microsoft Edge WebView2 Runtime")
            # tkwebview2 3.5 supports both its historic ``web_view`` property
            # and pywebview 6's renamed ``webview`` property. The released
            # Python package still accesses the former directly, so retain a
            # narrow compatibility alias inside our optional host.
            if not hasattr(EdgeChrome, "web_view"):
                setattr(EdgeChrome, "web_view", property(lambda current: current.webview))
            self._view = (
                _SecureWebView2(self, 1, 1, cache_directory)
                if cache_directory is not None
                else WebView2(self, 1, 1)
            )
            self._view.pack(fill="both", expand=True)
            if allowed_origin is not None:
                self._harden_local_page(allowed_origin)
        except WebViewUnavailableError:
            raise
        except Exception as error:
            raise WebViewUnavailableError("无法初始化嵌入式网页组件") from error

    def navigate(self, url: str) -> None:
        try:
            self._view.load_url(url)
        except Exception as error:
            raise WebViewUnavailableError("无法加载服务器页面") from error

    def reload(self) -> None:
        try:
            self._view.reload()
        except Exception as error:
            raise WebViewUnavailableError("服务器页面尚未准备完成") from error

    def set_page_active(self, active: bool) -> None:
        """Tell a local MUI page whether it is currently visible."""

        if isinstance(self._view, _SecureWebView2):
            self._view.set_page_active(active)

    def _harden_local_page(self, allowed_origin: str) -> None:
        """Restrict a local MUI page to its own loopback origin.

        This callback is deliberately unavailable to the general server
        workspace: an embedded user-configured website must retain normal
        navigation, whereas the local authentication UI must not.
        """

        def ready(sender: Any, args: Any) -> None:
            if not bool(getattr(args, "IsSuccess", False)):
                return
            core = sender.CoreWebView2
            settings = core.Settings
            settings.AreDefaultContextMenusEnabled = False
            settings.AreDevToolsEnabled = False
            settings.AreBrowserAcceleratorKeysEnabled = False
            settings.IsStatusBarEnabled = False
            settings.IsZoomControlEnabled = False

            def navigation_starting(_source: Any, event: Any) -> None:
                uri = str(getattr(event, "Uri", ""))
                # ``startswith`` would also accept a lookalike origin such as
                # ``http://127.0.0.1:1234.example``. The renderer is only
                # allowed to load this exact loopback origin and its paths.
                if uri != allowed_origin and not uri.startswith(f"{allowed_origin}/"):
                    event.Cancel = True

            def new_window(_source: Any, event: Any) -> None:
                event.Handled = True

            core.NavigationStarting += navigation_starting
            core.NewWindowRequested += new_window
            # The CSP blocks storage-backed persistence as well; this removes
            # any convenient Web APIs from page code if a future dependency
            # attempts to use them.
            core.AddScriptToExecuteOnDocumentCreatedAsync(
                "Object.defineProperties(window,{localStorage:{get(){throw new Error('disabled')}},"
                "sessionStorage:{get(){throw new Error('disabled')}}});"
            )

        self._view.event_core_completed(ready)


class _SecureWebView2(tk.Frame):
    """Small ``tkwebview2`` equivalent with an explicit profile directory."""

    def __init__(self, parent: tk.Misc, width: int, height: int, cache_directory: Path) -> None:
        super().__init__(parent, width=width, height=height, background="#FFFFFF", borderwidth=0, highlightthickness=0)
        try:
            from tkwebview2 import tkwebview2 as host
            from webview.platforms.edgechromium import EdgeChrome
            from webview.window import Window
        except Exception as error:
            raise WebViewUnavailableError("无法加载嵌入式网页组件") from error
        cache_directory.mkdir(parents=True, exist_ok=True)
        self.control = host.Control()
        self.window = Window(
            f"mui-{id(self)}",
            str(id(self)),
            url=None,
            html="",
            width=width,
            height=height,
            resizable=True,
            min_size=(200, 100),
            hidden=False,
            frameless=False,
            easy_drag=True,
            minimized=False,
            on_top=False,
            confirm_close=False,
            background_color="#EEF5FA",
            transparent=False,
            text_select=True,
            localization=None,
            zoomable=False,
            draggable=False,
            vibrancy=False,
        )
        self.web_view = EdgeChrome(self.control, self.window, str(cache_directory))
        self.web = self.web_view.webview
        self.chwnd = int(str(self.control.Handle))
        host.user32.SetParent(self.chwnd, self.winfo_id())
        host.user32.MoveWindow(self.chwnd, 0, 0, width, height, True)
        self.core: Any = None
        self._page_active = True
        self._resize_after_id: str | None = None
        self._last_native_size: tuple[int, int] = (width, height)
        self.bind("<Configure>", self._resize)
        self.bind("<Destroy>", self._dispose, add="+")
        self.web.CoreWebView2InitializationCompleted += self._core_ready

    def _resize(self, _event: tk.Event[tk.Misc]) -> None:
        """Coalesce native child resizes while the user drags a window edge."""

        if self._resize_after_id is not None:
            return
        try:
            self._resize_after_id = self.after(16, self._flush_resize)
        except tk.TclError:
            self._resize_after_id = None

    def _flush_resize(self) -> None:
        self._resize_after_id = None
        try:
            from tkwebview2 import tkwebview2 as host

            size = (max(self.winfo_width(), 1), max(self.winfo_height(), 1))
            if size == self._last_native_size:
                return
            self._last_native_size = size
            host.user32.MoveWindow(self.chwnd, 0, 0, *size, True)
        except (ImportError, tk.TclError):
            pass

    def _dispose(self, _event: tk.Event[tk.Misc]) -> None:
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
            self._resize_after_id = None
        try:
            self.web.Dispose()
        except Exception:
            pass

    def _core_ready(self, sender: Any, _event: Any) -> None:
        self.core = sender.CoreWebView2
        try:
            self.core.NavigationCompleted += self._navigation_completed
        except Exception:
            pass
        self._apply_page_active()

    def _navigation_completed(self, _sender: Any, _event: Any) -> None:
        # A navigation creates a new JavaScript document, so replay the
        # visibility state after React has loaded rather than relying on an
        # event emitted against the previous blank document.
        self._apply_page_active()

    def set_page_active(self, active: bool) -> None:
        """Notify the local React page that it should start or stop polling."""

        self._page_active = bool(active)
        self._apply_page_active()

    def _apply_page_active(self) -> None:
        if self.core is None:
            return
        script = (
            f"window.__authenticatorPageActive={str(self._page_active).lower()};"
            "window.dispatchEvent(new CustomEvent('authenticator-page-activity',"
            f"{{detail:{{active:{str(self._page_active).lower()}}}}}));"
        )
        try:
            self.core.ExecuteScriptAsync(script)
        except Exception:
            # A navigation can replace the document between the state change
            # and this callback. The page defaults to active on its next load.
            pass

    def event_core_completed(self, command: Any) -> None:
        self.web.CoreWebView2InitializationCompleted += command

    def load_url(self, url: str) -> None:
        self.web_view.load_url(url)

    def reload(self) -> None:
        if self.core is None:
            raise RuntimeError("WebView2 尚未准备完成")
        self.core.Reload()
