"""Tkinter 应用使用的轻量后台任务边界。"""

from __future__ import annotations

import queue
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from threading import Lock
from typing import Any


class BackgroundTaskRunner:
    """在线程池运行非 UI 工作，并把完成回调排队给调用线程。

    工作函数和完成回调的类型分别是 ``Callable[[], Any]``、
    ``Callable[[Any], None]``；调用方必须在 Tk 主线程周期性调用 ``drain``。
    """

    def __init__(
        self,
        max_workers: int = 2,
    ) -> None:
        """创建固定大小线程池、关闭锁和主线程待执行回调队列。"""

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="AuthenticatorWorker"
        )
        self._closed = False
        self._lock = Lock()
        self._callbacks: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()

    def submit(
        self,
        work: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
    ) -> Future[Any]:
        """提交工作并登记成功/失败回调，返回可供测试等待的 ``Future``。"""

        with self._lock:
            if self._closed:
                raise RuntimeError("后台任务执行器已关闭")
            future = self._executor.submit(work)

        def completed(done: Future[Any]) -> None:
            """在线程池回调上下文中只封装结果，绝不直接操作 Tk 控件。"""

            if done.cancelled():
                return
            try:
                result = done.result()
            except Exception as error:
                callback = partial(on_error, error)
            else:
                callback = partial(on_success, result)
            with self._lock:
                if self._closed:
                    return
            self._callbacks.put(callback)

        future.add_done_callback(completed)
        return future

    def drain(self, maximum: int = 20) -> int:
        """在调用线程执行至多 ``maximum`` 个已完成回调，返回实际处理数量。"""

        processed = 0
        while processed < maximum:
            try:
                callback = self._callbacks.get_nowait()
            except queue.Empty:
                break
            callback()
            processed += 1
        return processed

    def close(self) -> None:
        """拒绝新任务并取消尚未开始的工作；已运行任务不会阻塞窗口关闭。"""

        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
