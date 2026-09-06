"""账号写操作应用服务。

本模块是 UI/API 修改账号的唯一入口：先复制保险库内存状态，执行领域校验，保存，
任一步失败都恢复快照。它不导入 Tkinter，因此可由桌面窗口、API 和测试共用。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from typing import Any, TypeVar

from domain.entities import OTPEntry
from domain.errors import AccountNotFoundError, DuplicateAccountError
from domain.identifiers import account_identity, normalise_group_ids

TransactionResult = TypeVar("TransactionResult")


class AccountService:
    """维护账号集合的事务边界。

    ``vault`` 当前采用鸭子类型，以兼容 ``Vault`` 和轻量测试替身；它至少需要
    ``entries: list[OTPEntry]`` 与 ``groups`` 属性。``save`` 为无参持久化回调，
    失败时本类负责恢复两个列表的深拷贝。
    """

    def __init__(self, vault: Any, save: Callable[[], None]) -> None:
        """保存保险库对象和持久化回调，不在构造时读取或写入数据。"""

        self.vault = vault
        self._save = save

    def _transaction(self, operation: Callable[[], TransactionResult]) -> TransactionResult:
        """执行内存修改和保存的原子单元，异常时回滚账号与分组两个集合。"""

        # 分组也要进入快照：导入等上层流程可能在账号写入前合并分组。
        entries = deepcopy(self.vault.entries)
        groups = deepcopy(self.vault.groups)
        try:
            result = operation()
            self._save()
            return result
        except Exception:
            self.vault.entries = entries
            self.vault.groups = groups
            raise

    def _find(self, account_id: str) -> OTPEntry:
        """按稳定账号 ID 查找实体；不存在时抛出 ``AccountNotFoundError``。"""

        entry = next((candidate for candidate in self.vault.entries if candidate.id == account_id), None)
        if entry is None:
            raise AccountNotFoundError("账号不存在")
        return entry

    def _ensure_unique(self, entry: OTPEntry, excluding_id: str | None = None) -> None:
        """按服务商、账号、密钥和 OTP 类型检查重复；编辑时可排除自身 ID。"""

        identity = account_identity(entry)
        duplicate = next(
            (
                candidate
                for candidate in self.vault.entries
                if candidate.id != excluding_id and account_identity(candidate) == identity
            ),
            None,
        )
        if duplicate is not None:
            raise DuplicateAccountError(f"账号已存在：{duplicate.title}")

    def _normalise_known_group_ids(self, group_ids: Iterable[str]) -> list[str]:
        """规范化账号归属并拒绝当前保险库不存在的分组 ID。

        账号服务是所有新增和编辑路径的统一写入边界，因此不能只依赖 UI/API
        预校验，否则脚本、导入流程或未来调用方可能留下悬空分组引用。
        """

        normalised = normalise_group_ids(group_ids)
        known = {group.id for group in self.vault.groups}
        unknown = [group_id for group_id in normalised if group_id not in known]
        if unknown:
            raise ValueError(f"未知分组：{', '.join(unknown)}")
        return normalised

    def create(self, entry: OTPEntry, active_group_id: str | None = None) -> OTPEntry:
        """新增一个账号，并在指定活动分组存在时将其加入该分组。"""

        def operation() -> OTPEntry:
            """规范化、校验、去重并把单条账号追加到事务内存集合。"""

            requested_group_ids = list(entry.group_ids)
            if active_group_id and active_group_id not in entry.group_ids:
                requested_group_ids.append(active_group_id)
            entry.group_ids = self._normalise_known_group_ids(requested_group_ids)
            entry.validate()
            self._ensure_unique(entry)
            self.vault.entries.append(entry)
            return entry

        return self._transaction(operation)

    def create_many(self, entries: Iterable[OTPEntry], active_group_id: str | None = None) -> list[OTPEntry]:
        """原子新增一批账号，并同时检查既有记录和同批记录之间的重复。"""

        pending = list(entries)

        def operation() -> list[OTPEntry]:
            """逐条校验待导入账号，并把同批去重键加入局部集合。"""

            existing_keys = {account_identity(candidate) for candidate in self.vault.entries}
            added: list[OTPEntry] = []
            for entry in pending:
                requested_group_ids = list(entry.group_ids)
                if active_group_id and active_group_id not in entry.group_ids:
                    requested_group_ids.append(active_group_id)
                entry.group_ids = self._normalise_known_group_ids(requested_group_ids)
                entry.validate()
                identity = account_identity(entry)
                if identity in existing_keys:
                    raise DuplicateAccountError(f"账号已存在：{entry.title}")
                existing_keys.add(identity)
                self.vault.entries.append(entry)
                added.append(entry)
            return added

        return self._transaction(operation)

    def update(self, entry: OTPEntry) -> OTPEntry:
        """以相同 ID 替换现有账号，保留事务回滚和唯一性保证。"""

        def operation() -> OTPEntry:
            """按 ID 找到旧对象后，以已校验的新实体替换其列表位置。"""

            current = self._find(entry.id)
            entry.group_ids = self._normalise_known_group_ids(entry.group_ids)
            entry.validate()
            self._ensure_unique(entry, excluding_id=current.id)
            self.vault.entries[self.vault.entries.index(current)] = entry
            return entry

        return self._transaction(operation)

    def delete(self, account_ids: Iterable[str]) -> int:
        """删除给定 ID 集合，返回实际删除数量；空集合不会触发保存。"""

        ids = {str(account_id) for account_id in account_ids}
        if not ids:
            return 0

        def operation() -> int:
            """过滤待删除 ID，并用长度差计算实际删除数量。"""

            before = len(self.vault.entries)
            self.vault.entries[:] = [entry for entry in self.vault.entries if entry.id not in ids]
            return before - len(self.vault.entries)

        return self._transaction(operation)

    def increment_hotp(self, account_id: str) -> OTPEntry:
        """将 HOTP 账号计数器加一并保存；非 HOTP 账号会被拒绝。"""

        def operation() -> OTPEntry:
            """验证 HOTP 类型后原地递增计数器。"""

            entry = self._find(account_id)
            if entry.otp_type != "hotp":
                raise ValueError("只有基于计数器的账号可以生成下一个 HOTP")
            entry.counter += 1
            return entry

        return self._transaction(operation)

    def toggle_pinned(self, account_id: str) -> OTPEntry:
        """切换账号置顶状态并返回更新后的实体。"""

        def operation() -> OTPEntry:
            """反转目标账号的布尔置顶标记。"""

            entry = self._find(account_id)
            entry.pinned = not entry.pinned
            return entry

        return self._transaction(operation)

    def set_pinned(self, account_ids: Iterable[str], pinned: bool) -> int:
        """Set the pinned state for matching accounts in one transaction."""

        ids = {str(account_id) for account_id in account_ids}

        def operation() -> int:
            changed = 0
            for entry in self.vault.entries:
                if entry.id in ids and entry.pinned != pinned:
                    entry.pinned = pinned
                    changed += 1
            return changed

        return self._transaction(operation)

    def set_favorite(self, account_ids: Iterable[str], favorite: bool) -> int:
        """Set the favorite state for matching accounts in one transaction."""

        ids = {str(account_id) for account_id in account_ids}

        def operation() -> int:
            changed = 0
            for entry in self.vault.entries:
                if entry.id in ids and entry.favorite != favorite:
                    entry.favorite = favorite
                    changed += 1
            return changed

        return self._transaction(operation)
