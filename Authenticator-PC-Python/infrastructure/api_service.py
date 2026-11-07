"""与 HTTP 传输无关的本机 API 业务服务。

传输层只需投递动作名和 JSON 负载；本类定义响应形状，并将账号新增委托给
``AccountService``，使 HTTP 调用和桌面 UI 使用同一套校验与事务规则。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from application.account_service import AccountService
from domain.errors import DuplicateAccountError
from domain.identifiers import account_identity, normalise_group_ids


class ApiService:
    """在主线程读取保险库并生成本机 API 响应。

    ``is_ready`` 防止耗时保险库操作期间读取中间状态，``is_locked`` 防止锁定时
    泄露账号或密钥。可选 UI 回调只在账号创建成功后执行。
    """

    def __init__(
        self,
        vault: Any,
        account_service: AccountService,
        entry_factory: Callable[[dict[str, Any]], Any],
        filter_entries: Callable[[list[Any], str], list[Any]],
        now_factory: Callable[[], str],
        is_ready: Callable[[], bool],
        is_locked: Callable[[], bool],
        refresh_callback: Callable[[], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> None:
        """注入保险库、账号服务、实体工厂、筛选规则和主窗口状态查询回调。"""

        self.vault = vault
        self.account_service = account_service
        self.entry_factory = entry_factory
        self.filter_entries = filter_entries
        self.now_factory = now_factory
        self.is_ready = is_ready
        self.is_locked = is_locked
        self.refresh_callback = refresh_callback
        self.status_callback = status_callback

    def account_metadata(self, entry: Any) -> dict[str, Any]:
        """构造不含密钥的账号元数据，供列表和创建成功响应复用。"""

        return {
            "id": entry.id,
            "issuer": entry.issuer,
            "account": entry.account,
            "otp_type": entry.otp_type,
            "pinned": entry.pinned,
            "created_at": entry.created_at,
            "group_ids": list(entry.group_ids),
            "groups": [
                {"id": group.id, "name": group.name}
                for group_id in entry.group_ids
                if (group := self.vault.group_by_id(group_id)) is not None
            ],
        }

    def find_entry(self, payload: dict[str, Any]) -> tuple[Any | None, tuple[int, dict[str, Any]] | None]:
        """按 ID 或服务商/账号定位唯一实体；失败时返回预构造 API 错误响应。"""

        account_id = str(payload.get("id") or "").strip()
        if account_id:
            entry = next((candidate for candidate in self.vault.entries if candidate.id == account_id), None)
            if entry is None:
                return None, (404, {"error": "account_not_found"})
            return entry, None

        issuer = str(payload.get("issuer") or "").strip()
        account = str(payload.get("account") or "").strip()
        if not issuer and not account:
            return None, (400, {"error": "account_identifier_required"})
        matches = [
            entry
            for entry in self.vault.entries
            if (not issuer or entry.issuer.casefold() == issuer.casefold())
            and (not account or entry.account.casefold() == account.casefold())
        ]
        if not matches:
            return None, (404, {"error": "account_not_found"})
        if len(matches) > 1:
            return None, (409, {"error": "multiple_accounts_match"})
        return matches[0], None

    def _create_account(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """从 API JSON 构造、验证并事务保存账号，返回兼容 HTTP 的状态/对象。"""

        try:
            entry = self.entry_factory(payload)
            entry.id = str(payload.get("id") or entry.id)
            entry.created_at = entry.created_at or self.now_factory()
            # API 只允许引用已存在分组，避免外部请求隐式创建分组。
            requested_group_ids = normalise_group_ids(payload.get("group_ids", payload.get("groups")))
            unknown_group_ids = [
                group_id for group_id in requested_group_ids if self.vault.group_by_id(group_id) is None
            ]
            if unknown_group_ids:
                return 400, {"error": "unknown_group_ids", "group_ids": unknown_group_ids}
            entry.group_ids = [
                group_id for group_id in requested_group_ids if self.vault.group_by_id(group_id) is not None
            ]
            entry.validate()
            entry.code()
        except (TypeError, ValueError) as error:
            return 400, {"error": "invalid_account", "message": str(error)}

        if any(existing.id == entry.id for existing in self.vault.entries):
            return 409, {"error": "account_id_exists"}
        if any(account_identity(existing) == account_identity(entry) for existing in self.vault.entries):
            return 409, {"error": "duplicate_account"}
        try:
            self.account_service.create(entry)
        except DuplicateAccountError:
            return 409, {"error": "duplicate_account"}
        # 各持久化实现可能抛出不同异常；API 统一成通用错误，不能泄露存储细节。
        except Exception:
            return 500, {"error": "vault_save_failed"}
        if self.refresh_callback:
            self.refresh_callback()
        if self.status_callback:
            self.status_callback(f"已通过 API 新增 {entry.title}。")
        return 201, {"account": self.account_metadata(entry)}

    def handle(self, action: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """处理一个已路由动作，并在读取数据前依次检查就绪和锁定状态。"""

        # 健康检查刻意绕过就绪/锁定保护，以便客户端判断当前可用状态。
        if action == "health":
            return 200, {
                "status": "ready" if self.is_ready() else "starting",
                "locked": self.is_locked(),
                "api_version": 1,
            }
        if not self.is_ready():
            return 503, {"error": "vault_not_ready"}
        if self.is_locked():
            return 423, {"error": "vault_locked"}

        if action == "list_accounts":
            entries = self.filter_entries(self.vault.entries, "")
            return 200, {"accounts": [self.account_metadata(entry) for entry in entries], "count": len(entries)}

        if action == "list_groups":
            groups = [
                {
                    "id": group.id,
                    "name": group.name,
                    "created_at": group.created_at,
                    "account_count": sum(group.id in entry.group_ids for entry in self.vault.entries),
                }
                for group in self.vault.groups
            ]
            return 200, {"groups": groups, "count": len(groups)}

        if action == "get_secret":
            entry, failure = self.find_entry(payload)
            if failure:
                return failure
            assert entry is not None
            return 200, {
                "account": {
                    **self.account_metadata(entry),
                    "secret": entry.secret,
                    "secret_encoding": entry.secret_encoding,
                    "counter": entry.counter,
                    "period": entry.period,
                    "digits": entry.digits,
                    "algorithm": entry.algorithm,
                }
            }

        if action == "get_code":
            entry, failure = self.find_entry(payload)
            if failure:
                return failure
            assert entry is not None
            try:
                code = entry.code()
            except ValueError as error:
                return 422, {"error": "invalid_account_secret", "message": str(error)}
            return 200, {
                "account": self.account_metadata(entry),
                "code": code,
                "remaining_seconds": entry.remaining_seconds(),
            }

        if action == "create_account":
            return self._create_account(payload)

        if action == "scan_add":
            group_ids = normalise_group_ids(payload.get("group_ids", payload.get("groups")))
            unknown_group_ids = [
                group_id for group_id in group_ids if self.vault.group_by_id(group_id) is None
            ]
            if unknown_group_ids:
                return 400, {"error": "unknown_group_ids", "group_ids": unknown_group_ids}
            return 200, {"group_ids": group_ids}

        return 500, {"error": "unknown_api_action"}
