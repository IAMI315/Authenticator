"""本机 API 的纯路由匹配；不读取保险库，也不处理 HTTP 套接字。"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse

from infrastructure.api_dtos import ApiResponse, JsonObject

# 所有兼容 API 路径均以版本前缀开始，变更时需要同步 README 与自检。
LOCAL_API_BASE_PATH = "/v1"


@dataclass(frozen=True)
class ApiRoute:
    """路由成功后的传输无关动作描述。

    ``requires_json_body`` 为真时，HTTP 适配器必须读取并验证请求体后再投递。
    """

    action: str
    payload: JsonObject = field(default_factory=dict)
    requires_json_body: bool = False


class ApiRouter:
    """把 HTTP 方法与路径映射为与传输无关的内部动作。"""

    def match(self, method: str, target: str) -> ApiRoute | ApiResponse:
        """匹配请求目标；成功返回 ``ApiRoute``，失败直接返回状态码和错误对象。"""

        method = method.upper()
        parsed = urlparse(target)
        if method == "GET":
            return self._match_get(parsed.path, parsed.query)
        if method == "POST":
            if parsed.path == f"{LOCAL_API_BASE_PATH}/accounts":
                return ApiRoute("create_account", requires_json_body=True)
            return 404, {"error": "not_found"}
        return 405, {"error": "method_not_allowed"}

    @staticmethod
    def _match_get(path: str, query_string: str) -> ApiRoute | ApiResponse:
        """解析 GET 路由及按服务商/账号查询密钥时的查询参数。"""

        if path == f"{LOCAL_API_BASE_PATH}/health":
            return ApiRoute("health")
        if path == f"{LOCAL_API_BASE_PATH}/accounts":
            return ApiRoute("list_accounts")
        if path == f"{LOCAL_API_BASE_PATH}/groups":
            return ApiRoute("list_groups")
        if path == f"{LOCAL_API_BASE_PATH}/accounts/secret":
            query = parse_qs(query_string, keep_blank_values=True)
            payload = {key: values[-1] for key, values in query.items() if values}
            return ApiRoute("get_secret", payload)

        # ID 放在路径段中时需要先 URL 解码，才能与保险库中的原始 ID 比较。
        prefix = f"{LOCAL_API_BASE_PATH}/accounts/"
        suffix = "/secret"
        if path.startswith(prefix) and path.endswith(suffix):
            account_id = unquote(path[len(prefix) : -len(suffix)]).strip()
            if account_id:
                return ApiRoute("get_secret", {"id": account_id})
        return 404, {"error": "not_found"}
