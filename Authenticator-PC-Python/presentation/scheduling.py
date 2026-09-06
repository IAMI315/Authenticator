"""Small Tk scheduling primitives used by resize-heavy presentation widgets."""

from __future__ import annotations

import math
import time
import tkinter as tk
from collections.abc import Callable


class TrailingDebouncer:
    """Run a callback once a burst of Tk events has remained quiet."""

    def __init__(self, widget: tk.Misc, delay_ms: int, callback: Callable[[], None]) -> None:
        self.widget = widget
        self.delay_ms = max(1, delay_ms)
        self.callback = callback
        self._after_id: str | None = None
        self._last_trigger = 0.0

    @property
    def pending(self) -> bool:
        return self._after_id is not None

    def trigger(self) -> None:
        self._last_trigger = time.monotonic()
        if self._after_id is None:
            self._after_id = self.widget.after(self.delay_ms, self._poll)

    def cancel(self) -> None:
        callback_id = self._after_id
        self._after_id = None
        if callback_id is None:
            return
        try:
            self.widget.after_cancel(callback_id)
        except tk.TclError:
            pass

    def flush(self) -> None:
        self.cancel()
        self.callback()

    def _poll(self) -> None:
        elapsed_ms = (time.monotonic() - self._last_trigger) * 1_000
        remaining_ms = self.delay_ms - elapsed_ms
        if remaining_ms > 1:
            self._after_id = self.widget.after(math.ceil(remaining_ms), self._poll)
            return
        self._after_id = None
        self.callback()
