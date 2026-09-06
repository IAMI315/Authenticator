"""本机 API 传输层与主线程控制器共享的数据类型。"""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Any, TypeAlias

# API JSON 是开放字段对象；HTTP 状态码与对象响应共同构成一次 API 返回值。
JsonObject: TypeAlias = dict[str, Any]
ApiResponse: TypeAlias = tuple[int, JsonObject]


@dataclass
class ApiRequest:
    """HTTP 工作线程投递给 Tk 主线程的一次业务请求。

    ``action`` 是路由后的内部动作名，``payload`` 为已解析 JSON/查询参数，
    ``response`` 是容量为一的队列，用于将处理结果送回原 HTTP 线程。
    """

    action: str
    payload: JsonObject
    response: queue.Queue[ApiResponse]
