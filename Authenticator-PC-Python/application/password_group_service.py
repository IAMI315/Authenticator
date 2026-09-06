"""Transactional password-group operations."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any

from application.password_ports import PasswordVaultPort
from domain.errors import PasswordGroupNotFoundError
from domain.passwords import (
    MAX_PASSWORD_GROUP_NAME_LENGTH,
    PASSWORD_DEFAULT_GROUP_ID,
    PASSWORD_DEFAULT_GROUP_NAME,
    PasswordGroup,
    normalise_password_group_ids,
)
from domain.validators import utc_now_iso


class PasswordGroupService:
    def __init__(self, vault: PasswordVaultPort, save: Callable[[], None]) -> None:
        self.vault = vault
        self._save = save

    def _transaction(self, operation: Callable[[], Any]) -> Any:
        entries = deepcopy(self.vault.password_entries)
        groups = deepcopy(self.vault.password_groups)
        try:
            result = operation()
            self._save()
            return result
        except Exception:
            self.vault.password_entries = entries
            self.vault.password_groups = groups
            raise

    def _find(self, group_id: str) -> PasswordGroup:
        group = next((candidate for candidate in self.vault.password_groups if candidate.id == group_id), None)
        if group is None:
            raise PasswordGroupNotFoundError("密码分组不存在")
        return group

    def _normalise_name(self, name: str, excluding_id: str | None = None) -> str:
        value = " ".join(str(name or "").split())
        if not value:
            raise ValueError("请输入分组名称")
        if len(value) > MAX_PASSWORD_GROUP_NAME_LENGTH:
            raise ValueError(f"分组名称不能超过 {MAX_PASSWORD_GROUP_NAME_LENGTH} 个字符")
        if value.casefold() in {PASSWORD_DEFAULT_GROUP_NAME.casefold(), "全部密码".casefold()}:
            raise ValueError("该名称是系统保留名称，不能使用")
        if any(
            group.id != excluding_id and group.name.casefold() == value.casefold()
            for group in self.vault.password_groups
        ):
            raise ValueError("已存在同名分组")
        return value

    def create(self, name: str) -> PasswordGroup:
        def operation() -> PasswordGroup:
            group = PasswordGroup(str(uuid.uuid4()), self._normalise_name(name), utc_now_iso())
            group.validate()
            self.vault.password_groups.append(group)
            return group

        return self._transaction(operation)

    def rename(self, group_id: str, name: str) -> PasswordGroup:
        def operation() -> PasswordGroup:
            group = self._find(group_id)
            if group.id == PASSWORD_DEFAULT_GROUP_ID:
                raise ValueError("默认分组不能重命名")
            group.name = self._normalise_name(name, excluding_id=group.id)
            group.validate()
            return group

        return self._transaction(operation)

    def delete(self, group_id: str) -> PasswordGroup:
        def operation() -> PasswordGroup:
            group = self._find(group_id)
            if group.id == PASSWORD_DEFAULT_GROUP_ID:
                raise ValueError("默认分组不能删除")
            self.vault.password_groups.remove(group)
            for entry in self.vault.password_entries:
                entry.group_ids = normalise_password_group_ids(
                    candidate for candidate in entry.group_ids if candidate != group_id
                )
            return group

        return self._transaction(operation)

    def assign(self, entry_ids: Sequence[str], group_ids: Sequence[str]) -> int:
        ids = set(entry_ids)
        known = {group.id for group in self.vault.password_groups}
        requested = normalise_password_group_ids(group_ids)
        unknown = [group_id for group_id in requested if group_id not in known]
        if unknown:
            raise ValueError(f"未知分组：{', '.join(unknown)}")

        def operation() -> int:
            changed = 0
            for entry in self.vault.password_entries:
                if entry.id in ids and entry.group_ids != requested:
                    entry.group_ids = list(requested)
                    changed += 1
            return changed

        return self._transaction(operation)

    def assign_many(self, assignments: Mapping[str, Iterable[str]]) -> int:
        known = {group.id for group in self.vault.password_groups}
        normalised: dict[str, list[str]] = {}
        for entry_id, group_ids in assignments.items():
            requested = normalise_password_group_ids(group_ids)
            unknown = [group_id for group_id in requested if group_id not in known]
            if unknown:
                raise ValueError(f"未知分组：{', '.join(unknown)}")
            normalised[str(entry_id)] = requested

        def operation() -> int:
            changed = 0
            for entry in self.vault.password_entries:
                requested = normalised.get(entry.id)
                if requested is not None and entry.group_ids != requested:
                    entry.group_ids = list(requested)
                    changed += 1
            return changed

        return self._transaction(operation)
