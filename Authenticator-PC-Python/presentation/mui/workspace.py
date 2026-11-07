"""The MUI full-window workspace hosted inside a hardened local WebView2."""

from __future__ import annotations

import shutil
import tkinter as tk
from typing import Any, Literal

from infrastructure.paths import resource_path
from presentation.mui.bridge import MuiBridge
from presentation.webview_host import EdgeWebViewHost, WebViewUnavailableError


class MuiWorkspace(tk.Frame):
    """Own the local MUI server, transient renderer profile and WebView host."""

    def __init__(self, parent: tk.Misc, app: Any, *, mode: Literal["full", "compact"] = "full") -> None:
        super().__init__(parent, background="#EEF5FA", borderwidth=0, highlightthickness=0)
        self.app = app
        self.mode = mode
        self._active = False
        self._closed = False
        # Full and compact windows can coexist briefly while Tk switches
        # modes. Separate browser profiles prevent WebView2 lock contention.
        self.runtime_directory = (app.data_directory / "mui-runtime" / mode).resolve()
        self._clear_runtime()
        self.runtime_directory.mkdir(parents=True, exist_ok=True)
        static_directory = resource_path("frontend/dist")
        if not static_directory.is_dir() or not (static_directory / "index.html").is_file():
            raise WebViewUnavailableError("MUI 界面资源未构建")
        self.bridge = MuiBridge(
            app,
            static_directory,
            page_mode=mode,
            brand_icon_directory=self.runtime_directory / "brand-icons",
        )
        try:
            self.host = EdgeWebViewHost(
                self,
                cache_directory=self.runtime_directory,
                allowed_origin=self.bridge.origin,
            )
            self.host.pack(fill="both", expand=True)
            self.host.navigate(self.bridge.page_url)
        except Exception:
            self.bridge.close()
            self._clear_runtime()
            raise

    @property
    def active(self) -> bool:
        return self._active

    def activate(self) -> None:
        if self._closed:
            return
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()
        self.set_page_active(True)

    def deactivate(self) -> None:
        if self._closed:
            return
        self.place_forget()
        self.set_page_active(False)

    def set_page_active(self, active: bool) -> None:
        """Pause page polling while this renderer is hidden or withdrawn."""

        if self._closed:
            return
        active = bool(active)
        if self._active == active:
            return
        self._active = active
        self.host.set_page_active(active)

    def process_requests(self) -> None:
        if not self._closed:
            self.bridge.process_requests()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.host.destroy()
        except tk.TclError:
            pass
        self.bridge.close()
        self._clear_runtime()

    def _clear_runtime(self) -> None:
        """Remove only the application-owned transient renderer profile."""

        try:
            if self.runtime_directory.is_dir():
                shutil.rmtree(self.runtime_directory)
        except OSError:
            # WebView2 may still be relinquishing its own profile handles. Do
            # not sleep on Tk's event thread: the next startup clears this
            # application-owned transient directory before it is reused.
            pass
