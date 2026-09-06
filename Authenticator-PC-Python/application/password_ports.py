"""Structural ports used by password-book application services."""

from __future__ import annotations

from typing import Any, Protocol

from domain.passwords import PasswordEntry, PasswordGroup


class PasswordVaultPort(Protocol):
    """Small mutable vault surface required by password services."""

    password_entries: list[PasswordEntry]
    password_groups: list[PasswordGroup]

    def password_group_by_id(self, group_id: str) -> PasswordGroup | None: ...

    def normalise_password_entry_group_ids(self, value: Any) -> list[str]: ...
