"""验证 API 业务响应、锁定保护、账号元数据和创建规则。"""

from application.account_service import AccountService
from application.search_service import filter_entries
from domain.entities import OTPEntry, default_account_group
from infrastructure.api_service import ApiService

SECRET = "JBSWY3DPEHPK3PXP"


class FakeVault:
    """仅实现 API 服务读取账号和分组所需能力的内存保险库替身。"""

    def __init__(self):
        """初始化空账号列表及默认分组。"""

        self.entries = []
        self.groups = [default_account_group()]

    def group_by_id(self, group_id):
        """按 ID 返回分组，模拟真实 ``Vault`` 的读取方法。"""

        return next((group for group in self.groups if group.id == group_id), None)


def make_entry(account="alice@example.com"):
    """构造可通过领域校验的固定测试账号。"""

    return OTPEntry(
        id=account,
        issuer="Example",
        account=account,
        secret=SECRET,
        created_at="2025-01-01T00:00:00Z",
    )


def make_service(vault, ready=lambda: True, locked=lambda: False):
    """使用内存保存回调构造 API 服务，允许测试注入就绪/锁定状态。"""

    account_service = AccountService(vault, lambda: None)
    return ApiService(
        vault,
        account_service,
        OTPEntry.from_dict,
        filter_entries,
        lambda: "2025-01-02T00:00:00Z",
        ready,
        locked,
    )


def test_api_service_health_and_vault_guards():
    """健康检查可报告状态；未就绪和锁定保险库必须阻止账号读取。"""

    vault = FakeVault()
    service = make_service(vault, ready=lambda: False)
    assert service.handle("health", {})[1]["status"] == "starting"
    assert service.handle("list_accounts", {}) == (503, {"error": "vault_not_ready"})

    locked_service = make_service(vault, locked=lambda: True)
    assert locked_service.handle("list_accounts", {}) == (423, {"error": "vault_locked"})


def test_api_service_lists_accounts_without_secrets_and_gets_secret_on_request():
    """列表响应不得包含密钥，显式密钥查询才可返回密钥。"""

    vault = FakeVault()
    vault.entries.append(make_entry())
    service = make_service(vault)

    status, payload = service.handle("list_accounts", {})
    assert status == 200
    assert payload["count"] == 1
    assert "secret" not in payload["accounts"][0]

    status, payload = service.handle("get_secret", {"id": "alice@example.com"})
    assert status == 200
    assert payload["account"]["secret"] == SECRET


def test_api_service_returns_current_code_without_exposing_secret():
    """验证码路由只返回当前动态码和计时信息，不复用密钥响应。"""

    vault = FakeVault()
    vault.entries.append(make_entry())
    service = make_service(vault)

    status, payload = service.handle("get_code", {"id": "alice@example.com"})
    assert status == 200
    assert payload["code"].isdigit()
    assert len(payload["code"]) == 6
    assert payload["remaining_seconds"] in range(1, 31)
    assert "secret" not in payload["account"]


def test_api_service_creates_account_and_rejects_duplicate():
    """创建应写入账号；同 ID 的重复请求必须返回冲突。"""

    vault = FakeVault()
    service = make_service(vault)
    request = {
        "id": "account-1",
        "issuer": "Example",
        "account": "alice@example.com",
        "secret": SECRET,
        "created_at": "2025-01-02T00:00:00Z",
    }

    status, payload = service.handle("create_account", request)
    assert status == 201
    assert payload["account"]["id"] == "account-1"
    assert vault.entries[0].group_ids == ["default"]

    duplicate_status, duplicate_payload = service.handle("create_account", request)
    assert duplicate_status == 409
    assert duplicate_payload == {"error": "account_id_exists"}


def test_api_service_rejects_unknown_group_and_ambiguous_lookup():
    """未知分组和按字段匹配到多账号时必须拒绝，避免错误读取/写入。"""

    vault = FakeVault()
    service = make_service(vault)
    request = {
        "issuer": "Example",
        "account": "alice@example.com",
        "secret": SECRET,
        "group_ids": ["missing"],
    }
    assert service.handle("create_account", request) == (
        400,
        {"error": "unknown_group_ids", "group_ids": ["missing"]},
    )

    vault.entries.extend([make_entry("same@example.com"), make_entry("other@example.com")])
    vault.entries[1].issuer = "Example"
    status, payload = service.handle("get_secret", {"issuer": "Example"})
    assert status == 409
    assert payload == {"error": "multiple_accounts_match"}


def test_api_service_preflights_scan_groups_without_starting_scan():
    """扫码 API 的分组校验沿用新增账号规则，实际 UI 启动由控制器负责。"""

    vault = FakeVault()
    service = make_service(vault)
    assert service.handle("scan_add", {"group_ids": ["default"]}) == (200, {"group_ids": ["default"]})
    assert service.handle("scan_add", {"group_ids": ["missing"]}) == (
        400,
        {"error": "unknown_group_ids", "group_ids": ["missing"]},
    )
