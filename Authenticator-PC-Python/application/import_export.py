"""Typed import parsing for desktop backups, extension backups and OTP URIs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from domain.entities import AccountGroup, OTPEntry
from domain.google_authenticator import (
    is_google_authenticator_migration_uri,
    parse_google_authenticator_migration,
)
from domain.migrations import migrate_legacy_star_records
from domain.passwords import PasswordEntry, PasswordGroup
from domain.servers import ServerProfile


@dataclass(frozen=True)
class ImportBundle:
    otp_entries: list[OTPEntry] = field(default_factory=list)
    otp_groups: list[AccountGroup] = field(default_factory=list)
    password_entries: list[PasswordEntry] = field(default_factory=list)
    password_groups: list[PasswordGroup] = field(default_factory=list)
    server_profiles: list[ServerProfile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BackupPasswordRequiredError(ValueError):
    """当前 Windows 用户不能无感解密备份，需要源主密码。"""


@dataclass(frozen=True)
class QrImportPayload:
    """Typed result shared by desktop and mobile QR workflows."""

    bundle: ImportBundle
    source: str
    batch_size: int = 1
    batch_index: int = 0
    batch_id: int = 0


def parse_qr_content(content: str) -> QrImportPayload:
    """Parse a standard OTP QR or a Google Authenticator migration QR."""

    value = content.strip()
    if is_google_authenticator_migration_uri(value):
        migration = parse_google_authenticator_migration(value)
        return QrImportPayload(
            bundle=ImportBundle(
                otp_entries=list(migration.entries),
                warnings=list(migration.warnings),
            ),
            source="google_authenticator",
            batch_size=migration.batch_size,
            batch_index=migration.batch_index,
            batch_id=migration.batch_id,
        )
    return QrImportPayload(
        bundle=ImportBundle(otp_entries=[OTPEntry.from_uri(value)]),
        source="otpauth",
    )


def parse_import_text(text: str) -> ImportBundle:
    content = text.strip()
    if not content:
        raise ValueError("所选文件为空")
    try:
        document = json.loads(content)
    except json.JSONDecodeError:
        uri_entries: list[OTPEntry] = []
        uri_warnings: list[str] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            value = line.strip()
            if not value:
                continue
            try:
                parsed_qr = parse_qr_content(value)
                uri_entries.extend(parsed_qr.bundle.otp_entries)
                uri_warnings.extend(parsed_qr.bundle.warnings)
            except ValueError:
                uri_warnings.append(f"第 {line_number} 行未能导入")
        if not uri_entries:
            raise ValueError("没有找到有效的验证码 URI")
        return ImportBundle(otp_entries=uri_entries, warnings=uri_warnings)

    if isinstance(document, dict) and document.get("format") == "authenticator-desktop/v1":
        document, _migrated = migrate_legacy_star_records(document)

    raw_entries: list[Any]
    raw_groups: list[Any] = []
    raw_password_entries: list[Any] = []
    raw_password_groups: list[Any] = []
    raw_server_profiles: list[Any] = []
    if isinstance(document, list):
        raw_entries = document
    elif isinstance(document, dict) and (
        isinstance(document.get("entries"), list)
        or isinstance(document.get("password_entries"), list)
        or isinstance(document.get("server_profiles"), list)
    ):
        raw_entries = document.get("entries", []) if isinstance(document.get("entries"), list) else []
        raw_groups = document.get("groups", []) if isinstance(document.get("groups"), list) else []
        raw_password_entries = (
            document.get("password_entries", []) if isinstance(document.get("password_entries"), list) else []
        )
        raw_password_groups = (
            document.get("password_groups", []) if isinstance(document.get("password_groups"), list) else []
        )
        raw_server_profiles = (
            document.get("server_profiles", []) if isinstance(document.get("server_profiles"), list) else []
        )
    elif isinstance(document, dict) and "secret" in document:
        raw_entries = [document]
    elif isinstance(document, dict):
        raw_entries = list(document.values())
    else:
        raise ValueError("不支持此 JSON 备份格式")

    entries: list[OTPEntry] = []
    groups: list[AccountGroup] = []
    password_entries: list[PasswordEntry] = []
    password_groups: list[PasswordGroup] = []
    server_profiles: list[ServerProfile] = []
    warnings: list[str] = []
    seen_group_ids: set[str] = set()
    seen_group_names: set[str] = set()
    for position, raw_group in enumerate(raw_groups, start=1):
        try:
            group = AccountGroup.from_dict(raw_group)
        except (TypeError, ValueError):
            warnings.append(f"第 {position} 个分组无效")
            continue
        if group.id in seen_group_ids or group.name.casefold() in seen_group_names:
            warnings.append(f"第 {position} 个分组重复")
            continue
        seen_group_ids.add(group.id)
        seen_group_names.add(group.name.casefold())
        groups.append(group)
    for position, raw_entry in enumerate(raw_entries, start=1):
        if not isinstance(raw_entry, dict):
            warnings.append(f"第 {position} 条记录不是账号")
            continue
        if raw_entry.get("dataType") == "Key":
            continue
        if raw_entry.get("encrypted") or raw_entry.get("dataType") == "EncOTPStorage":
            warnings.append(f"已跳过第 {position} 条加密记录")
            continue
        if not raw_entry.get("secret"):
            warnings.append(f"第 {position} 条记录没有可用密钥")
            continue
        try:
            entries.append(OTPEntry.from_dict(raw_entry))
        except ValueError:
            warnings.append(f"第 {position} 条记录无效")

    seen_password_group_ids: set[str] = set()
    seen_password_group_names: set[str] = set()
    for position, raw_group in enumerate(raw_password_groups, start=1):
        try:
            password_group = PasswordGroup.from_dict(raw_group)
        except (TypeError, ValueError):
            warnings.append(f"第 {position} 个密码分组无效")
            continue
        if (
            password_group.id in seen_password_group_ids
            or password_group.name.casefold() in seen_password_group_names
        ):
            warnings.append(f"第 {position} 个密码分组重复")
            continue
        seen_password_group_ids.add(password_group.id)
        seen_password_group_names.add(password_group.name.casefold())
        password_groups.append(password_group)
    for position, raw_entry in enumerate(raw_password_entries, start=1):
        try:
            password_entries.append(PasswordEntry.from_dict(raw_entry))
        except (TypeError, ValueError):
            warnings.append(f"第 {position} 条密码记录无效")
    seen_server_ids: set[str] = set()
    seen_server_identities: set[tuple[str, str, int, str]] = set()
    for position, raw_profile in enumerate(raw_server_profiles, start=1):
        try:
            profile = ServerProfile.from_dict(raw_profile)
        except (TypeError, ValueError):
            warnings.append(f"第 {position} 个服务器记录无效")
            continue
        if profile.id in seen_server_ids or profile.connection_identity in seen_server_identities:
            warnings.append(f"第 {position} 个服务器记录重复")
            continue
        seen_server_ids.add(profile.id)
        seen_server_identities.add(profile.connection_identity)
        server_profiles.append(profile)
    if not entries and not password_entries and not server_profiles:
        raise ValueError("备份中没有可用账号、密码或服务器记录")
    return ImportBundle(entries, groups, password_entries, password_groups, server_profiles, warnings)
