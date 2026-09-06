"""展示层中的本机 API 生命周期协调器。"""

from __future__ import annotations

import queue
from collections.abc import Callable

from infrastructure.api_server import ApiRequest, LocalApiServer
from infrastructure.api_service import ApiService


class ApiController:
    """连接 HTTP 工作线程队列与 Tk 主线程业务服务。

    ``requests`` 由 ``LocalApiServer`` 写入，主窗口每 50ms 调用 ``process``。这样
    ``ApiService`` 读取保险库时始终和 Tk UI 处在同一线程。
    """

    def __init__(
        self,
        api_service: ApiService,
        token: str,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """保存服务、令牌和可选错误回调，并创建跨线程请求队列。"""

        self.api_service = api_service
        self.token = token
        self.on_error = on_error
        self.requests: queue.Queue[ApiRequest] = queue.Queue()
        self.server: LocalApiServer | None = None
        self.error: str | None = None

    @property
    def endpoint(self) -> str:
        """返回运行中服务的地址，未启动时返回默认兼容地址。"""

        if self.server is not None:
            return self.server.endpoint
        return "http://127.0.0.1:8765/v1"

    @property
    def running(self) -> bool:
        """转发底层 HTTP 服务是否正在运行。"""

        return self.server is not None and self.server.running

    def start(self) -> None:
        """按需创建并启动本机 HTTP 服务，将绑定错误记录并通知 UI。"""

        if self.server is None:
            self.server = LocalApiServer(self.token, self.requests)
        error = self.server.start()
        self.error = error
        if error and self.on_error:
            self.on_error(error)

    def status_text(self) -> str:
        """生成设置对话框可直接显示的 API 状态文本。"""

        if self.error:
            return self.error
        return "运行中（仅本机可访问）" if self.running else "未启动"

    def process(self, maximum: int = 20) -> int:
        """在 Tk 主线程处理至多 ``maximum`` 个排队 API 请求。"""

        processed = 0
        while processed < maximum:
            try:
                request = self.requests.get_nowait()
            except queue.Empty:
                break
            try:
                # 单个 API 处理错误不应中断后续请求；HTTP 侧只获得通用错误对象。
                response = self.api_service.handle(request.action, request.payload)
            except Exception:
                response = (500, {"error": "internal_error"})
            try:
                request.response.put_nowait(response)
            except queue.Full:
                pass
            processed += 1
        return processed

    def stop(self) -> None:
        """停止本机 HTTP 服务并清空服务器引用，窗口关闭时调用。"""

        if self.server is not None:
            self.server.stop()
        self.server = None
