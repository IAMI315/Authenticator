"""验证器本机 API 的 loopback HTTP 传输层。

服务器绝不直接读取保险库。它只认证、限制和解析 HTTP 请求，再把小型动作/负载
消息放入 Tk 事件循环队列，由主线程中的 ``ApiService`` 处理。
"""

from __future__ import annotations

import hmac
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from infrastructure.api_dtos import ApiRequest, ApiResponse, JsonObject
from infrastructure.api_router import LOCAL_API_BASE_PATH, ApiRoute, ApiRouter

# 只监听 IPv4 loopback，避免令牌保护的接口暴露到局域网。
LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = 8765
LOCAL_API_MAX_BODY_BYTES = 256 * 1024
LOCAL_API_SCAN_TIMEOUT_SECONDS = 180


class _LocalThreadingHttpServer(ThreadingHTTPServer):
    """内部 HTTPServer 配置：请求线程为守护线程且允许快速重启端口。"""

    daemon_threads = True
    allow_reuse_address = True


class LocalApiServer:
    """仅本机可访问的 HTTP 服务器，将业务工作转发至调用方拥有的队列。"""

    def __init__(
        self,
        token: str,
        request_queue: queue.Queue[ApiRequest],
        host: str = LOCAL_API_HOST,
        port: int = LOCAL_API_PORT,
    ) -> None:
        """保存认证令牌、主线程请求队列及可测试的监听地址/端口。"""

        self.token = token
        self.request_queue = request_queue
        self.host = host
        self.port = port
        self.router = ApiRouter()
        self._server: _LocalThreadingHttpServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def endpoint(self) -> str:
        """返回当前监听地址的版本化 API 根路径。"""

        return f"http://{self.host}:{self.port}{LOCAL_API_BASE_PATH}"

    @property
    def running(self) -> bool:
        """仅在线程和 HTTPServer 都存在且服务线程存活时返回真。"""

        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(self) -> str | None:
        """启动守护 HTTP 线程；成功返回 ``None``，端口绑定失败返回用户可见文本。"""

        if self.running:
            return None
        service = self

        class RequestHandler(BaseHTTPRequestHandler):
            """每个连接使用的内部处理器，只做 HTTP 校验和队列转发。"""

            protocol_version = "HTTP/1.1"
            server_version = "AuthenticatorDesktopAPI/1.0"
            sys_version = ""

            def log_message(self, _format: str, *_args: Any) -> None:
                """屏蔽 BaseHTTPRequestHandler 默认访问日志，避免记录敏感请求路径。"""

                return

            def _write_json(self, status: int, document: JsonObject) -> None:
                """写入一条不缓存的 UTF-8 JSON HTTP 响应。"""

                payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def _is_authorised(self) -> bool:
                """从专用请求头或 Bearer 头读取令牌，并使用常量时间比较。"""

                supplied = self.headers.get("X-Authenticator-Token", "").strip()
                authorization = self.headers.get("Authorization", "").strip()
                if not supplied and authorization.lower().startswith("bearer "):
                    supplied = authorization[7:].strip()
                return bool(supplied) and hmac.compare_digest(supplied, service.token)

            def _require_token(self) -> bool:
                """验证令牌；失败时立即写入 401，调用方不应继续处理请求。"""

                if self._is_authorised():
                    return True
                self._write_json(401, {"error": "unauthorized"})
                return False

            def _dispatch(self, action: str, payload: JsonObject) -> None:
                """投递请求到主线程，并最多等待 10 秒的业务响应。"""

                # HTTP 工作线程只等待队列结果，不能访问 Tk 或保险库对象。
                response: queue.Queue[ApiResponse] = queue.Queue(maxsize=1)
                service.request_queue.put(ApiRequest(action, payload, response))
                timeout = LOCAL_API_SCAN_TIMEOUT_SECONDS if action == "scan_add" else 10
                try:
                    status, document = response.get(timeout=timeout)
                except queue.Empty:
                    self._write_json(503, {"error": "application_busy"})
                    return
                self._write_json(status, document)

            def _read_json_body(self) -> tuple[JsonObject | None, ApiResponse | None]:
                """按 Content-Length 限制读取并验证 JSON 对象请求体。"""

                content_length = self.headers.get("Content-Length")
                if content_length is None:
                    return None, (411, {"error": "content_length_required"})
                try:
                    length = int(content_length)
                except ValueError:
                    return None, (400, {"error": "invalid_content_length"})
                if length < 0:
                    return None, (400, {"error": "invalid_content_length"})
                if length > LOCAL_API_MAX_BODY_BYTES:
                    return None, (413, {"error": "payload_too_large"})
                try:
                    document = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return None, (400, {"error": "invalid_json"})
                if not isinstance(document, dict):
                    return None, (400, {"error": "json_object_required"})
                return document, None

            def _handle_route(self, method: str) -> None:
                """执行认证、纯路由匹配、可选 JSON 解析和主线程分派。"""

                if not self._require_token():
                    return
                route = service.router.match(method, self.path)
                if not isinstance(route, ApiRoute):
                    self._write_json(*route)
                    return
                payload = route.payload
                if route.requires_json_body:
                    document, failure = self._read_json_body()
                    if failure:
                        self._write_json(*failure)
                        return
                    payload = document or {}
                self._dispatch(route.action, payload)

            def do_GET(self) -> None:  # noqa: N802
                """BaseHTTPRequestHandler 约定的 GET 入口，转交统一路由处理。"""

                self._handle_route("GET")

            def do_POST(self) -> None:  # noqa: N802
                """BaseHTTPRequestHandler 约定的 POST 入口，转交统一路由处理。"""

                self._handle_route("POST")

            def do_PUT(self) -> None:  # noqa: N802
                """明确返回路由器定义的 405，不读取请求体或访问业务服务。"""

                response = service.router.match("PUT", self.path)
                assert not isinstance(response, ApiRoute)
                self._write_json(*response)

            def do_DELETE(self) -> None:  # noqa: N802
                """明确返回路由器定义的 405，不读取请求体或访问业务服务。"""

                response = service.router.match("DELETE", self.path)
                assert not isinstance(response, ApiRoute)
                self._write_json(*response)

        try:
            self._server = _LocalThreadingHttpServer((self.host, self.port), RequestHandler)
        except OSError as error:
            self._server = None
            return f"无法启动本机 API：{error}"
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, name="AuthenticatorLocalApi", daemon=True)
        self._thread.start()
        return None

    def stop(self) -> None:
        """停止 HTTP 服务并在短暂等待后回收守护线程引用。"""

        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
