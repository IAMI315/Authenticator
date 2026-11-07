"""验证兼容 API 路径、URL 解码和不支持方法的纯路由规则。"""

from infrastructure.api_router import ApiRoute, ApiRouter


def test_api_router_matches_compatible_routes():
    """公开 GET/POST 路径应映射到计划中稳定的内部动作。"""

    router = ApiRouter()
    assert router.match("GET", "/v1/health") == ApiRoute("health")
    assert router.match("GET", "/v1/accounts") == ApiRoute("list_accounts")
    assert router.match("GET", "/v1/groups") == ApiRoute("list_groups")
    assert router.match("POST", "/v1/accounts") == ApiRoute("create_account", requires_json_body=True)
    assert router.match("POST", "/v1/accounts/scan") == ApiRoute("scan_add", requires_json_body=True)


def test_api_router_decodes_secret_lookups_and_rejects_unknown_routes():
    """密钥查询应 URL 解码，未知路径/方法应返回约定错误。"""

    router = ApiRouter()
    assert router.match("GET", "/v1/accounts/account%201/secret") == ApiRoute(
        "get_secret", {"id": "account 1"}
    )
    assert router.match("GET", "/v1/accounts/account%201/code") == ApiRoute(
        "get_code", {"id": "account 1"}
    )
    assert router.match("GET", "/v1/accounts/code?issuer=xAI&account=user%40example.com") == ApiRoute(
        "get_code", {"issuer": "xAI", "account": "user@example.com"}
    )
    assert router.match("GET", "/v1/accounts/secret?issuer=xAI&account=user%40example.com") == ApiRoute(
        "get_secret", {"issuer": "xAI", "account": "user@example.com"}
    )
    assert router.match("GET", "/v1/missing") == (404, {"error": "not_found"})
    assert router.match("DELETE", "/v1/accounts/anything") == (405, {"error": "method_not_allowed"})
