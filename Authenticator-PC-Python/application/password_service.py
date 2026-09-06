"""Transactional password-record operations independent from Tkinter."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from copy import deepcopy
from typing import Any

from application.password_commands import CreatePasswordCommand, UpdatePasswordCommand
from application.password_ports import PasswordVaultPort
from application.password_search_service import PasswordSearchService
from application.sorting import PasswordSortSpec
from domain.errors import DuplicatePasswordError, PasswordNotFoundError
from domain.passwords import PasswordEntry, normalise_password_group_ids, password_identity
from domain.validators import utc_now_iso


class PasswordService:
    def __init__(
        self,
        vault: PasswordVaultPort,
        save: Callable[[], None],
        search_service: PasswordSearchService,
        now_factory: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.vault = vault
        self._save = save
        self._search_service = search_service
        self._now_factory = now_factory

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

    def _find(self, entry_id: str) -> PasswordEntry:
        entry = next((candidate for candidate in self.vault.password_entries if candidate.id == entry_id), None)
        if entry is None:
            raise PasswordNotFoundError("密码记录不存在")
        return entry

    def _ensure_unique(self, entry: PasswordEntry, excluding_id: str | None = None) -> None:
        duplicate = next(
            (
                candidate
                for candidate in self.vault.password_entries
                if candidate.id != excluding_id and password_identity(candidate) == password_identity(entry)
            ),
            None,
        )
        if duplicate is not None:
            raise DuplicatePasswordError(f"密码记录已存在：{duplicate.title}")

    def _known_group_ids(self, group_ids: Sequence[str]) -> list[str]:
        requested = normalise_password_group_ids(group_ids)
        unknown = [
            group_id
            for group_id in requested
            if self.vault.password_group_by_id(group_id) is None
        ]
        if unknown:
            raise ValueError(f"未知密码分组：{', '.join(unknown)}")
        return requested

    def list(
        self,
        query: str = "",
        group_id: str | None = None,
        sort_spec: PasswordSortSpec | None = None,
    ) -> list[PasswordEntry]:
        entries = self.vault.password_entries
        if group_id is not None:
            entries = [entry for entry in entries if group_id in entry.group_ids]
        return self._search_service.search(entries, query, sort_spec)

    def create(self, command: CreatePasswordCommand) -> PasswordEntry:
        def operation() -> PasswordEntry:
            entry = PasswordEntry(
                id=str(uuid.uuid4()),
                name=command.name,
                username=command.username,
                password=command.password,
                url=command.url,
                notes=command.notes,
                pinned=command.pinned,
                created_at=self._now_factory(),
                group_ids=self._known_group_ids(command.group_ids),
                favorite=command.favorite,
            )
            entry.validate()
            self._ensure_unique(entry)
            self.vault.password_entries.append(entry)
            return entry

        return self._transaction(operation)

    def update(self, entry_id: str, command: UpdatePasswordCommand) -> PasswordEntry:
        def operation() -> PasswordEntry:
            current = self._find(entry_id)
            updated = PasswordEntry(
                id=current.id,
                name=command.name,
                username=command.username,
                password=command.password,
                url=command.url,
                notes=command.notes,
                pinned=command.pinned,
                created_at=current.created_at,
                group_ids=self._known_group_ids(command.group_ids),
                favorite=command.favorite,
            )
            updated.validate()
            self._ensure_unique(updated, excluding_id=current.id)
            self.vault.password_entries[self.vault.password_entries.index(current)] = updated
            return updated

        return self._transaction(operation)

    def delete(self, entry_ids: Sequence[str]) -> int:
        ids = set(entry_ids)
        if not ids:
            return 0

        def operation() -> int:
            before = len(self.vault.password_entries)
            self.vault.password_entries[:] = [entry for entry in self.vault.password_entries if entry.id not in ids]
            return before - len(self.vault.password_entries)

        return self._transaction(operation)

    def set_pinned(self, entry_ids: Sequence[str], pinned: bool) -> int:
        ids = set(entry_ids)

        def operation() -> int:
            changed = 0
            for entry in self.vault.password_entries:
                if entry.id in ids and entry.pinned != pinned:
                    entry.pinned = pinned
                    changed += 1
            return changed

        return self._transaction(operation)

    def set_favorite(self, entry_ids: Sequence[str], favorite: bool) -> int:
        ids = set(entry_ids)

        def operation() -> int:
            changed = 0
            for entry in self.vault.password_entries:
                if entry.id in ids and entry.favorite != favorite:
                    entry.favorite = favorite
                    changed += 1
            return changed

        return self._transaction(operation)
