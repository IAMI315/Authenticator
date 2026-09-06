"""Typed commands for password-book mutations."""

from __future__ import annotations

from dataclasses import dataclass

from domain.passwords import PASSWORD_DEFAULT_GROUP_ID


@dataclass(frozen=True)
class CreatePasswordCommand:
    username: str
    password: str
    name: str = ""
    url: str = ""
    notes: str = ""
    pinned: bool = False
    group_ids: tuple[str, ...] = (PASSWORD_DEFAULT_GROUP_ID,)
    favorite: bool = False


@dataclass(frozen=True)
class UpdatePasswordCommand:
    username: str
    password: str
    name: str = ""
    url: str = ""
    notes: str = ""
    pinned: bool = False
    group_ids: tuple[str, ...] = (PASSWORD_DEFAULT_GROUP_ID,)
    favorite: bool = False
