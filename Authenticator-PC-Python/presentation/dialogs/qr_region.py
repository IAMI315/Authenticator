"""用于框选屏幕二维码区域的全屏半透明覆盖层。"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any

from presentation.styles import ACCENT


class ScreenRegionSelector(tk.Toplevel):
    """记录拖拽起止点并回调逻辑屏幕坐标的轻量全屏选择器。"""

    def __init__(self, parent: tk.Misc, callback: Callable[[tuple[int, int, int, int] | None], None]) -> None:
        """创建覆盖层；回调接收选区或 ``None``（Escape/过小选区/关闭）。"""

        super().__init__(parent)
        self.callback = callback
        self.start_x = 0
        self.start_y = 0
        self.selection_id: int | None = None
        self.configure(background="#101820")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.28)
        self.configure(cursor="crosshair")

        left = self.winfo_vrootx()
        top = self.winfo_vrooty()
        width = self.winfo_vrootwidth()
        height = self.winfo_vrootheight()
        self.geometry(f"{width}x{height}+{left}+{top}")

        self.canvas = tk.Canvas(self, background="#101820", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._start_selection)
        self.canvas.bind("<B1-Motion>", self._update_selection)
        self.canvas.bind("<ButtonRelease-1>", self._finish_selection)
        self.bind("<Escape>", lambda _event: self._finish(None))
        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(None))
        self.grab_set()
        self.focus_force()

    def _start_selection(self, event: tk.Event[Any]) -> None:
        """记录鼠标按下坐标，并删除上一轮绘制的选择矩形。"""

        self.start_x = event.x
        self.start_y = event.y
        if self.selection_id is not None:
            self.canvas.delete(self.selection_id)
            self.selection_id = None

    def _update_selection(self, event: tk.Event[Any]) -> None:
        """随鼠标拖动重绘选择矩形，仅作为视觉反馈，不执行截图。"""

        if self.selection_id is not None:
            self.canvas.delete(self.selection_id)
        self.selection_id = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            event.x,
            event.y,
            outline=ACCENT,
            width=3,
            fill="",
        )

    def _finish_selection(self, event: tk.Event[Any]) -> None:
        """计算标准化选区；小于最小尺寸时按取消处理。"""

        if event is None:
            self._finish(None)
            return
        left = min(self.start_x, event.x)
        top = min(self.start_y, event.y)
        right = max(self.start_x, event.x)
        bottom = max(self.start_y, event.y)
        if right - left < 12 or bottom - top < 12:
            self._finish(None)
            return
        self._finish((left + self.winfo_vrootx(), top + self.winfo_vrooty(), right + self.winfo_vrootx(), bottom + self.winfo_vrooty()))

    def _finish(self, bbox: tuple[int, int, int, int] | None) -> None:
        """释放模态抓取、销毁覆盖层并把选区传回调用方。"""

        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self.callback(bbox)
