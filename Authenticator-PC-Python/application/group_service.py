"""分组及账号归属的事务应用服务，不依赖 Tkinter。"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, TypeVar

from domain.entities import AccountGroup
from domain.errors import GroupNotFoundError
from domain.identifiers import DEFAULT_GROUP_ID, normalise_group_ids

TransactionResult = TypeVar("TransactionResult")


def _now_iso() -> str:
    """生成新建分组使用的毫秒精度 UTC 时间。"""

    return datetime.now(UTC).isoformat(timespec="milliseconds")


class GroupService:
    """集中处理分组名称、成员归属与保存回滚规则。

    ``vault`` 为兼容迁移保留的鸭子类型，至少含 ``groups``、``entries`` 两个列表。
    所有公开写操作都通过 ``_transaction``，不能由 UI 直接改动这两个集合。
    """

    def __init__(
        self,
        vault: Any,
        save: Callable[[], None],
        default_group_name: str = "默认分组",
        all_accounts_label: str = "全部账号",
        max_name_length: int = 60,
    ) -> None:
        """保存分组规则中的显示文案和长度限制，便于 UI 与领域规则保持一致。"""

        self.vault = vault
        self._save = save
        self.default_group_name = default_group_name
        self.all_accounts_label = all_accounts_label
        self.max_name_length = max_name_length

    def _transaction(self, operation: Callable[[], TransactionResult]) -> TransactionResult:
        """执行分组/归属修改并保存；保存或校验失败时恢复完整快照。"""

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

    def _normalise_name(self, name: str, excluding_id: str | None = None) -> str:
        """规范化并验证自定义分组名称，拒绝保留名和大小写重复名。"""

        value = " ".join(str(name or "").split())
        if not value:
            raise ValueError("请输入分组名称")
        if len(value) > self.max_name_length:
            raise ValueError(f"分组名称不能超过 {self.max_name_length} 个字符")
        if value.casefold() in {self.default_group_name.casefold(), self.all_accounts_label.casefold()}:
            raise ValueError("该名称是系统保留名称，不能使用")
        if any(group.id != excluding_id and group.name.casefold() == value.casefold() for group in self.vault.groups):
            raise ValueError("已存在同名分组")
        return value

    def _find(self, group_id: str) -> AccountGroup:
        """按分组 ID 查找实体；未知 ID 抛出 ``GroupNotFoundError``。"""

        group = next((candidate for candidate in self.vault.groups if candidate.id == group_id), None)
        if group is None:
            raise GroupNotFoundError("分组不存在")
        return group

    def create(self, name: str) -> AccountGroup:
        """创建带 UUID 和创建时间的自定义分组。"""

        def operation() -> AccountGroup:
            """构造、校验并追加新分组。"""

            group = type(self.vault.groups[0])(
                id=str(uuid.uuid4()), name=self._normalise_name(name), created_at=_now_iso()
            )
            group.validate()
            self.vault.groups.append(group)
            return group

        return self._transaction(operation)

    def rename(self, group_id: str, name: str) -> AccountGroup:
        """重命名非默认分组，并保留同名检查和事务回滚。"""

        def operation() -> AccountGroup:
            """保护默认分组后更新目标分组名称。"""

            group = self._find(group_id)
            if group.id == DEFAULT_GROUP_ID:
                raise ValueError("默认分组不能重命名")
            group.name = self._normalise_name(name, excluding_id=group.id)
            group.validate()
            return group

        return self._transaction(operation)

    def delete(self, group_id: str) -> AccountGroup:
        """删除非默认分组，同时从所有账号中移除该分组归属。"""

        def operation() -> AccountGroup:
            """移除目标分组，并从每个账号的归属列表滤除其 ID。"""

            group = self._find(group_id)
            if group.id == DEFAULT_GROUP_ID:
                raise ValueError("默认分组不能删除")
            self.vault.groups.remove(group)
            for entry in self.vault.entries:
                entry.group_ids = normalise_group_ids(
                    candidate for candidate in entry.group_ids if candidate != group_id
                )
            return group

        return self._transaction(operation)

    def assign(self, account_ids: Iterable[str], group_ids: Iterable[str]) -> int:
        """以同一组 ID 覆盖多个账号的归属，返回发生变化的账号数。"""

        ids = {str(account_id) for account_id in account_ids}
        requested = tuple(str(group_id) for group_id in group_ids)
        known = {group.id for group in self.vault.groups}
        unknown = [group_id for group_id in requested if group_id not in known]
        if unknown:
            raise ValueError(f"未知分组：{', '.join(unknown)}")

        def operation() -> int:
            """对命中的账号以同一标准化分组列表进行覆盖。"""

            changed = 0
            for entry in self.vault.entries:
                if entry.id not in ids:
                    continue
                before = list(entry.group_ids)
                entry.group_ids = normalise_group_ids(requested)
                if entry.group_ids != before:
                    changed += 1
            return changed

        return self._transaction(operation)

    def assign_many(self, assignments: Mapping[str, Iterable[str]]) -> int:
        """在一次事务内分别更新多个账号的分组归属，返回变化数量。"""

        # 在开始事务前验证所有目标分组，避免操作到一半才发现未知 ID。
        known = {group.id for group in self.vault.groups}
        normalised: dict[str, list[str]] = {}
        for account_id, group_ids in assignments.items():
            requested = [str(group_id) for group_id in group_ids]
            unknown = [group_id for group_id in requested if group_id not in known]
            if unknown:
                raise ValueError(f"未知分组：{', '.join(unknown)}")
            normalised[str(account_id)] = normalise_group_ids(requested)

        def operation() -> int:
            """按账号 ID 应用预校验后的不同分组列表。"""

            changed = 0
            for entry in self.vault.entries:
                if entry.id not in normalised:
                    continue
                group_ids = normalised[entry.id]
                if entry.group_ids != group_ids:
                    entry.group_ids = group_ids
                    changed += 1
            return changed

        return self._transaction(operation)
