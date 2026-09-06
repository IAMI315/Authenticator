"""可由完整界面和轻量窗口共同调用的屏幕二维码扫描流程。"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from infrastructure.qr_scanner import QrCodeNotFoundError

ScanSuccess = Callable[[Any], None]
ScanError = Callable[[Exception], None]
ScanStateChanged = Callable[[str], None]
RegionSelectorFactory = Callable[
    [tk.Misc, Callable[[tuple[int, int, int, int] | None], None]],
    Any,
]


class QrScannerPort(Protocol):
    """共享流程需要的扫码基础设施最小接口。"""

    def scan_screen(self) -> Any: ...

    def capture_region(
        self,
        bbox: tuple[int, int, int, int],
        logical_screen: tuple[int, int, int, int],
    ) -> Any: ...

    def decode(self, image: Any) -> Any: ...


class BackgroundTasksPort(Protocol):
    """把耗时工作送入后台并在 Tk 主线程交付回调的最小接口。"""

    def submit(
        self,
        work: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> Any: ...


def _create_region_selector(
    parent: tk.Misc,
    callback: Callable[[tuple[int, int, int, int] | None], None],
) -> Any:
    """延迟加载 Tk 覆盖层，避免共享流程与对话框集中导出形成循环依赖。"""

    from presentation.dialogs.qr_region import ScreenRegionSelector

    return ScreenRegionSelector(parent, callback)


@dataclass(frozen=True)
class _WindowSnapshot:
    widget: Any
    state: str | None


class QrScanFlow:
    """统一编排“自动识别全屏，无结果则框选”的非阻塞扫码流程。"""

    def __init__(
        self,
        host: tk.Misc,
        scanner: QrScannerPort,
        background_tasks: BackgroundTasksPort,
        *,
        selector_factory: RegionSelectorFactory = _create_region_selector,
        automatic_delay_ms: int = 140,
    ) -> None:
        self.host = host
        self.scanner = scanner
        self.background_tasks = background_tasks
        self.selector_factory = selector_factory
        self.automatic_delay_ms = automatic_delay_ms
        self.running = False
        self._generation = 0
        self._windows: list[_WindowSnapshot] = []
        self._windows_restored = True
        self._grab_owner: Any | None = None
        self._on_success: ScanSuccess | None = None
        self._on_error: ScanError | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._on_state_changed: ScanStateChanged | None = None

    def start(
        self,
        windows_to_hide: Iterable[Any],
        on_success: ScanSuccess,
        on_error: ScanError,
        *,
        on_cancel: Callable[[], None] | None = None,
        on_state_changed: ScanStateChanged | None = None,
    ) -> bool:
        """启动一次扫码；流程已运行时返回 ``False``，避免重复截图和覆盖层。"""

        if self.running:
            return False
        self.running = True
        self._generation += 1
        generation = self._generation
        self._on_success = on_success
        self._on_error = on_error
        self._on_cancel = on_cancel
        self._on_state_changed = on_state_changed
        self._windows = self._snapshot_windows(windows_to_hide)
        self._windows_restored = False
        try:
            self._grab_owner = self.host.grab_current()
        except (AttributeError, tk.TclError):
            self._grab_owner = None
        self._emit_state("automatic")
        self._hide_windows()
        try:
            self.host.update_idletasks()
            self.host.after(
                self.automatic_delay_ms,
                lambda: self._start_automatic_scan(generation),
            )
        except tk.TclError as error:
            self._finish_error(generation, error)
        return True

    def cancel(self) -> None:
        """取消当前流程并恢复窗口；后台结果到达后会因代次失效而被忽略。"""

        if not self.running:
            return
        callback = self._on_cancel
        self._finish()
        if callback is not None:
            callback()

    @staticmethod
    def _snapshot_windows(windows: Iterable[Any]) -> list[_WindowSnapshot]:
        snapshots: list[_WindowSnapshot] = []
        seen: set[int] = set()
        for window in windows:
            if window is None or id(window) in seen:
                continue
            seen.add(id(window))
            try:
                state = str(window.state())
            except (AttributeError, tk.TclError):
                state = None
            snapshots.append(_WindowSnapshot(window, state))
        return snapshots

    def _hide_windows(self) -> None:
        for snapshot in self._windows:
            try:
                snapshot.widget.withdraw()
            except (AttributeError, tk.TclError):
                pass

    def _restore_windows(self) -> None:
        if self._windows_restored:
            return
        self._windows_restored = True
        restored: list[Any] = []
        for snapshot in self._windows:
            if snapshot.state not in ("normal", "zoomed", "iconic"):
                continue
            try:
                snapshot.widget.deiconify()
                if snapshot.state == "zoomed":
                    snapshot.widget.state("zoomed")
                restored.append(snapshot.widget)
            except (AttributeError, tk.TclError):
                pass
        if restored:
            try:
                restored[-1].lift()
            except (AttributeError, tk.TclError):
                pass
        if self._grab_owner is not None:
            try:
                self._grab_owner.grab_set()
            except (AttributeError, tk.TclError):
                pass

    def _start_automatic_scan(self, generation: int) -> None:
        if not self._is_current(generation):
            return
        try:
            self.background_tasks.submit(
                self.scanner.scan_screen,
                lambda payload: self._finish_success(generation, payload),
                lambda error: self._automatic_scan_failed(generation, error),
            )
        except Exception as error:
            self._finish_error(generation, error)

    def _automatic_scan_failed(self, generation: int, error: Exception) -> None:
        if not self._is_current(generation):
            return
        if isinstance(error, QrCodeNotFoundError):
            self._emit_state("selecting")
            try:
                self.selector_factory(
                    self.host,
                    lambda bbox: self._region_selected(generation, bbox),
                )
            except Exception as selector_error:
                self._finish_error(generation, selector_error)
            return
        self._finish_error(generation, error)

    def _region_selected(
        self,
        generation: int,
        bbox: tuple[int, int, int, int] | None,
    ) -> None:
        if not self._is_current(generation):
            return
        if bbox is None:
            callback = self._on_cancel
            self._finish()
            if callback is not None:
                callback()
            return
        logical_screen = (
            self.host.winfo_vrootx(),
            self.host.winfo_vrooty(),
            self.host.winfo_vrootwidth(),
            self.host.winfo_vrootheight(),
        )
        try:
            image = self.scanner.capture_region(bbox, logical_screen)
        except Exception as error:
            self._finish_error(generation, error)
            return
        self._restore_windows()
        self._emit_state("decoding")
        try:
            self.background_tasks.submit(
                lambda: self.scanner.decode(image),
                lambda payload: self._finish_success(generation, payload),
                lambda error: self._finish_error(generation, error),
            )
        except Exception as error:
            self._finish_error(generation, error)

    def _finish_success(self, generation: int, payload: Any) -> None:
        if not self._is_current(generation):
            return
        callback = self._on_success
        self._finish()
        if callback is not None:
            callback(payload)

    def _finish_error(self, generation: int, error: Exception) -> None:
        if not self._is_current(generation):
            return
        callback = self._on_error
        self._finish()
        if callback is not None:
            callback(error)

    def _finish(self) -> None:
        self._restore_windows()
        self.running = False
        self._generation += 1
        self._windows = []
        self._grab_owner = None
        self._on_success = None
        self._on_error = None
        self._on_cancel = None
        self._on_state_changed = None

    def _emit_state(self, state: str) -> None:
        if self._on_state_changed is not None:
            self._on_state_changed(state)

    def _is_current(self, generation: int) -> bool:
        return self.running and generation == self._generation
