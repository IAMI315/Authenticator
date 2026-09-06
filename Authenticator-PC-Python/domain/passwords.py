"""Password-book domain entities, validation, identity and generation rules."""

from __future__ import annotations

import secrets
import string
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from domain.validators import normalise_created_at, utc_now_iso

PASSWORD_DEFAULT_GROUP_ID = "password-default"
PASSWORD_DEFAULT_GROUP_NAME = "默认分组"
MAX_PASSWORD_GROUP_NAME_LENGTH = 60
MASKED_PASSWORD = "•" * 12


def normalise_password_group_ids(value: Any) -> list[str]:
    raw_values: Iterable[Any] = value if isinstance(value, Iterable) and not isinstance(value, (str, bytes)) else []
    result = [PASSWORD_DEFAULT_GROUP_ID]
    for raw_value in raw_values:
        group_id = str(raw_value or "").strip()
        if group_id and group_id not in result:
            result.append(group_id)
    return result


def normalise_password_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("网址必须是有效的 HTTP 或 HTTPS 地址")
    return url


@dataclass
class PasswordGroup:
    id: str
    name: str
    created_at: str | None = None

    def validate(self) -> None:
        self.id = str(self.id or "").strip()
        if not self.id or len(self.id) > 128:
            raise ValueError("密码分组标识无效")
        if self.id == PASSWORD_DEFAULT_GROUP_ID:
            self.name = PASSWORD_DEFAULT_GROUP_NAME
        else:
            self.name = " ".join(str(self.name or "").split())
            if not self.name:
                raise ValueError("请输入分组名称")
            if len(self.name) > MAX_PASSWORD_GROUP_NAME_LENGTH:
                raise ValueError(f"分组名称不能超过 {MAX_PASSWORD_GROUP_NAME_LENGTH} 个字符")
        self.created_at = normalise_created_at(self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, raw_group: dict[str, Any]) -> PasswordGroup:
        if not isinstance(raw_group, dict):
            raise ValueError("密码分组记录必须是对象")
        group = cls(
            id=str(raw_group.get("id") or ""),
            name=str(raw_group.get("name") or ""),
            created_at=raw_group.get("created_at", raw_group.get("createdAt")),
        )
        group.validate()
        return group


def default_password_group() -> PasswordGroup:
    return PasswordGroup(PASSWORD_DEFAULT_GROUP_ID, PASSWORD_DEFAULT_GROUP_NAME)


@dataclass
class PasswordEntry:
    id: str
    username: str
    password: str
    name: str = ""
    url: str = ""
    notes: str = ""
    pinned: bool = False
    created_at: str | None = None
    group_ids: list[str] = field(default_factory=lambda: [PASSWORD_DEFAULT_GROUP_ID])
    favorite: bool = False

    @property
    def title(self) -> str:
        return self.name or self.username

    def validate(self) -> None:
        self.id = str(self.id or "").strip()
        if not self.id or len(self.id) > 128:
            raise ValueError("密码记录标识无效")
        self.name = " ".join(str(self.name or "").split())
        self.username = str(self.username or "").strip()
        self.password = str(self.password or "")
        self.url = normalise_password_url(self.url)
        self.notes = str(self.notes or "").strip()
        if len(self.name) > 200:
            raise ValueError("名称/服务不能超过 200 个字符")
        if not self.username:
            raise ValueError("请输入用户名")
        if len(self.username) > 320:
            raise ValueError("用户名不能超过 320 个字符")
        if not self.password:
            raise ValueError("请输入密码")
        if len(self.password) > 4096:
            raise ValueError("密码不能超过 4096 个字符")
        if len(self.url) > 2048:
            raise ValueError("网址不能超过 2048 个字符")
        if len(self.notes) > 10_000:
            raise ValueError("备注不能超过 10000 个字符")
        self.created_at = normalise_created_at(self.created_at) or utc_now_iso()
        self.group_ids = normalise_password_group_ids(self.group_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "username": self.username,
            "password": self.password,
            "url": self.url,
            "notes": self.notes,
            "favorite": self.favorite,
            "pinned": self.pinned,
            "created_at": self.created_at,
            "group_ids": list(self.group_ids),
        }

    @classmethod
    def from_dict(cls, raw_entry: dict[str, Any]) -> PasswordEntry:
        if not isinstance(raw_entry, dict):
            raise ValueError("密码记录必须是对象")
        entry = cls(
            id=str(raw_entry.get("id") or uuid.uuid4()),
            name=str(raw_entry.get("name") or ""),
            username=str(raw_entry.get("username") or ""),
            password=str(raw_entry.get("password") or ""),
            url=str(raw_entry.get("url") or ""),
            notes=str(raw_entry.get("notes") or ""),
            pinned=bool(raw_entry.get("pinned", False)),
            created_at=raw_entry.get("created_at", raw_entry.get("createdAt")),
            group_ids=normalise_password_group_ids(raw_entry.get("group_ids", raw_entry.get("groups"))),
            favorite=bool(raw_entry.get("favorite", False)),
        )
        entry.validate()
        return entry


def password_identity(entry: PasswordEntry) -> tuple[str, str, str]:
    return entry.name.casefold().strip(), entry.username.casefold().strip(), entry.url.casefold().strip()


@dataclass(frozen=True)
class PasswordGeneratorOptions:
    length: int = 20
    lowercase: bool = True
    uppercase: bool = True
    digits: bool = True
    symbols: bool = True
    exclude_ambiguous: bool = True


def generate_password(options: PasswordGeneratorOptions = PasswordGeneratorOptions()) -> str:
    if not 8 <= options.length <= 128:
        raise ValueError("密码长度必须介于 8 到 128 之间")
    categories: list[str] = []
    if options.lowercase:
        categories.append(string.ascii_lowercase)
    if options.uppercase:
        categories.append(string.ascii_uppercase)
    if options.digits:
        categories.append(string.digits)
    if options.symbols:
        categories.append("!@#$%^&*()-_=+[]{};:,.?")
    if not categories:
        raise ValueError("请至少选择一种字符类型")
    if options.exclude_ambiguous:
        ambiguous = set("Il1O0o")
        categories = ["".join(character for character in category if character not in ambiguous) for category in categories]
    characters = [secrets.choice(category) for category in categories]
    pool = "".join(categories)
    characters.extend(secrets.choice(pool) for _ in range(options.length - len(characters)))
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)
