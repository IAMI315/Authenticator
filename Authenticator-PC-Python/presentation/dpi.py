"""Windows DPI awareness and logical-pixel conversion for the Tk UI."""

from __future__ import annotations

import ctypes
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

BASE_DPI = 96
_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+[+-]\d+)?$")


class DpiMode(StrEnum):
    PER_MONITOR_V2 = "per-monitor-v2"
    PER_MONITOR = "per-monitor"
    SYSTEM = "system"
    UNSUPPORTED = "unsupported"


def configure_process_dpi_awareness() -> DpiMode:
    """Enable the best DPI mode available before Tk creates a window."""

    if os.name != "nt":
        return DpiMode.UNSUPPORTED
    user32 = ctypes.windll.user32
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 is the signed handle -4.
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return DpiMode.PER_MONITOR_V2
    except (AttributeError, OSError):
        pass
    try:
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2. S_OK and E_ACCESSDENIED both mean
        # the process already has a non-virtualized DPI mode.
        result = int(shcore.SetProcessDpiAwareness(2))
        if result in (0, -2147024891):
            return DpiMode.PER_MONITOR
    except (AttributeError, OSError):
        pass
    try:
        if user32.SetProcessDPIAware():
            return DpiMode.SYSTEM
    except (AttributeError, OSError):
        pass
    return DpiMode.UNSUPPORTED


def _window_dpi(window: Any) -> int:
    if os.name == "nt":
        try:
            dpi = int(ctypes.windll.user32.GetDpiForWindow(window.winfo_id()))
            if dpi > 0:
                return dpi
        except (AttributeError, OSError, TypeError):
            pass
    try:
        return max(BASE_DPI, round(float(window.winfo_fpixels("1i"))))
    except (AttributeError, TypeError, ValueError):
        return BASE_DPI


@dataclass
class DpiContext:
    """Mutable DPI state shared by windows and pixel-based drawing widgets."""

    dpi: int = BASE_DPI
    mode: DpiMode = DpiMode.UNSUPPORTED

    @property
    def scale(self) -> float:
        return max(0.5, self.dpi / BASE_DPI)

    def dp(self, value: int | float) -> int:
        return max(1, round(float(value) * self.scale))

    def logical_px(self, value: int | float) -> int:
        return round(float(value) / self.scale)

    def physical_geometry(self, geometry: str) -> str:
        match = _GEOMETRY_RE.fullmatch(geometry.strip())
        if match is None:
            return geometry
        width, height, position = match.groups()
        return f"{self.dp(int(width))}x{self.dp(int(height))}{position or ''}"

    def logical_geometry(self, width: int, height: int) -> str:
        return f"{self.logical_px(width)}x{self.logical_px(height)}"

    def refresh_for_window(self, window: Any) -> bool:
        """Refresh the monitor DPI and Tk point scaling; return whether it changed."""

        dpi = _window_dpi(window)
        changed = dpi != self.dpi
        self.dpi = dpi
        try:
            target = dpi / 72.0
            current = float(window.tk.call("tk", "scaling"))
            if abs(current - target) > 0.01:
                window.tk.call("tk", "scaling", target)
        except (AttributeError, TypeError, ValueError):
            pass
        return changed


def dpi_context_for(widget: Any) -> DpiContext:
    """Return the root DPI context, falling back to a context for this widget."""

    root = widget.winfo_toplevel()
    context = getattr(root, "dpi_context", None)
    if isinstance(context, DpiContext):
        return context
    context = DpiContext()
    context.refresh_for_window(widget)
    return context
