"""兼容旧格式的本地 JSON 保险库状态与序列化实现。

``Vault`` 是内存中的账号/分组集合，同时负责 ``authenticator-desktop/v1`` 的读取、
原子写入和可选 AES-GCM 加密。应用服务通过仓储端口调用它，而非 UI 直接调用。
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from domain.entities import DEFAULT_GROUP_ID, DEFAULT_GROUP_NAME, AccountGroup, OTPEntry, default_account_group
from domain.identifiers import normalise_group_ids
from domain.migrations import migrate_legacy_star_records
from domain.passwords import (
    PASSWORD_DEFAULT_GROUP_ID,
    PASSWORD_DEFAULT_GROUP_NAME,
    PasswordEntry,
    PasswordGroup,
    default_password_group,
    normalise_password_group_ids,
)
from infrastructure.crypto import VaultCryptoError, decrypt_payload, derive_key, encrypt_payload_with_key
from infrastructure.errors import VaultError

VAULT_FORMAT = "authenticator-desktop/v1"
VAULT_AAD = b"authenticator-desktop-v1"
PBKDF2_ITERATIONS = 600_000


class Vault:
    """可选 AES-GCM 加密、以原子替换方式保存的本地账号保险库。

    公共状态：``entries: list[OTPEntry]``、``groups: list[AccountGroup]``、
    ``encrypted: bool``。私有字段保存已加载信封和仅在解锁期间存在的密钥材料，
    不应由展示层直接修改。
    """

    def __init__(self, path: Path) -> None:
        """创建空保险库；``path`` 是唯一的持久化目标，不会在此时访问磁盘。"""

        self.path = path
        self.entries: list[OTPEntry] = []
        self.groups: list[AccountGroup] = [default_account_group()]
        self.password_entries: list[PasswordEntry] = []
        self.password_groups: list[PasswordGroup] = [default_password_group()]
        self.secure_settings: dict[str, str] = {}
        self.encrypted = False
        self._envelope: dict[str, Any] | None = None
        self._key: bytes | None = None
        self._salt: bytes | None = None
        self._iterations = PBKDF2_ITERATIONS
        self.migration_pending = False

    @staticmethod
    def _derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
        """保留旧类接口的密码派生转发，实际算法位于 ``infrastructure.crypto``。"""

        return derive_key(passphrase, salt, iterations)

    def _payload(self) -> dict[str, Any]:
        """把当前实体集合转换为未加密 JSON 负载，供 ``save`` 加密或直写。"""

        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "groups": [group.to_dict() for group in self.groups],
            "password_entries": [entry.to_dict() for entry in self.password_entries],
            "password_groups": [group.to_dict() for group in self.password_groups],
            "secure_settings": dict(self.secure_settings),
        }

    def _load_payload(self, payload: dict[str, Any]) -> None:
        """将已验证的 JSON 负载转为实体，并修复未知/缺失的分组归属。"""

        payload, self.migration_pending = migrate_legacy_star_records(payload)

        raw_entries = payload.get("entries", [])
        if not isinstance(raw_entries, list):
            raise VaultError("本地保险库的账号列表格式不正确")
        raw_groups = payload.get("groups", [])
        if not isinstance(raw_groups, list):
            raise VaultError("本地保险库的分组列表格式不正确")
        raw_password_entries = payload.get("password_entries", [])
        if not isinstance(raw_password_entries, list):
            raise VaultError("本地保险库的密码列表格式不正确")
        raw_password_groups = payload.get("password_groups", [])
        if not isinstance(raw_password_groups, list):
            raise VaultError("本地保险库的密码分组格式不正确")
        raw_secure_settings = payload.get("secure_settings", {})
        if not isinstance(raw_secure_settings, dict):
            raise VaultError("本地保险库的安全设置格式不正确")
        try:
            parsed_groups = [AccountGroup.from_dict(group) for group in raw_groups]
            entries = [OTPEntry.from_dict(entry) for entry in raw_entries]
            parsed_password_groups = [PasswordGroup.from_dict(group) for group in raw_password_groups]
            password_entries = [PasswordEntry.from_dict(entry) for entry in raw_password_entries]
        except (TypeError, ValueError) as error:
            raise VaultError("本地保险库包含无效的账号或分组记录") from error

        # 始终重建默认分组；历史文件即使缺少它也能安全迁移。
        groups = [default_account_group()]
        group_ids = {DEFAULT_GROUP_ID}
        group_names = {DEFAULT_GROUP_NAME.casefold()}
        for group in parsed_groups:
            if group.id == DEFAULT_GROUP_ID:
                continue
            if group.id in group_ids or group.name.casefold() in group_names:
                raise VaultError("本地保险库包含重复的分组")
            groups.append(group)
            group_ids.add(group.id)
            group_names.add(group.name.casefold())
        self.groups = groups
        self.entries = entries
        for entry in self.entries:
            entry.group_ids = self.normalise_entry_group_ids(entry.group_ids)

        password_groups = [default_password_group()]
        password_group_ids = {PASSWORD_DEFAULT_GROUP_ID}
        password_group_names = {PASSWORD_DEFAULT_GROUP_NAME.casefold()}
        for password_group in parsed_password_groups:
            if password_group.id == PASSWORD_DEFAULT_GROUP_ID:
                continue
            if (
                password_group.id in password_group_ids
                or password_group.name.casefold() in password_group_names
            ):
                raise VaultError("本地保险库包含重复的密码分组")
            password_groups.append(password_group)
            password_group_ids.add(password_group.id)
            password_group_names.add(password_group.name.casefold())
        self.password_groups = password_groups
        self.password_entries = password_entries
        for password_entry in self.password_entries:
            password_entry.group_ids = self.normalise_password_entry_group_ids(password_entry.group_ids)
        self.secure_settings = {
            key: value
            for key, value in raw_secure_settings.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    def normalise_entry_group_ids(self, value: Any) -> list[str]:
        """保留默认分组并过滤当前保险库中不存在的自定义分组 ID。"""

        known_group_ids = {group.id for group in self.groups}
        return [group_id for group_id in normalise_group_ids(value) if group_id in known_group_ids]

    def group_by_id(self, group_id: str) -> AccountGroup | None:
        """按 ID 查询分组；未找到时返回 ``None``，供 UI/API 做非异常分支。"""

        return next((group for group in self.groups if group.id == group_id), None)

    def normalise_password_entry_group_ids(self, value: Any) -> list[str]:
        known_group_ids = {group.id for group in self.password_groups}
        return [group_id for group_id in normalise_password_group_ids(value) if group_id in known_group_ids]

    def password_group_by_id(self, group_id: str) -> PasswordGroup | None:
        return next((group for group in self.password_groups if group.id == group_id), None)

    def merge_imported_groups(self, imported_groups: list[AccountGroup]) -> dict[str, str]:
        """合并导入分组，并返回“导入 ID -> 当前 ID”的映射。

        名称相同的分组复用本地 ID；ID 冲突但名称不同则为导入分组生成新 UUID。
        调用方须在保存失败时恢复本方法对 ``groups`` 造成的内存修改。
        """

        mapping = {DEFAULT_GROUP_ID: DEFAULT_GROUP_ID}
        existing_ids = {group.id for group in self.groups}
        existing_names = {group.name.casefold(): group for group in self.groups}
        for imported_group in imported_groups:
            imported_group.validate()
            if imported_group.id == DEFAULT_GROUP_ID:
                mapping[imported_group.id] = DEFAULT_GROUP_ID
                continue
            if imported_group.id in mapping:
                continue
            same_name_group = existing_names.get(imported_group.name.casefold())
            if same_name_group is not None:
                mapping[imported_group.id] = same_name_group.id
                continue
            group_id = imported_group.id if imported_group.id not in existing_ids else str(uuid.uuid4())
            group = AccountGroup(
                id=group_id,
                name=imported_group.name,
                created_at=imported_group.created_at,
            )
            group.validate()
            self.groups.append(group)
            existing_ids.add(group.id)
            existing_names[group.name.casefold()] = group
            mapping[imported_group.id] = group.id
        return mapping

    def merge_imported_password_groups(self, imported_groups: list[PasswordGroup]) -> dict[str, str]:
        mapping = {PASSWORD_DEFAULT_GROUP_ID: PASSWORD_DEFAULT_GROUP_ID}
        existing_ids = {group.id for group in self.password_groups}
        existing_names = {group.name.casefold(): group for group in self.password_groups}
        for imported_group in imported_groups:
            imported_group.validate()
            if imported_group.id == PASSWORD_DEFAULT_GROUP_ID:
                mapping[imported_group.id] = PASSWORD_DEFAULT_GROUP_ID
                continue
            same_name_group = existing_names.get(imported_group.name.casefold())
            if same_name_group is not None:
                mapping[imported_group.id] = same_name_group.id
                continue
            group_id = imported_group.id if imported_group.id not in existing_ids else str(uuid.uuid4())
            group = PasswordGroup(group_id, imported_group.name, imported_group.created_at)
            group.validate()
            self.password_groups.append(group)
            existing_ids.add(group.id)
            existing_names[group.name.casefold()] = group
            mapping[imported_group.id] = group.id
        return mapping

    def load(self) -> bool:
        """读取保险库文件，返回是否需要密码解锁。

        不存在的文件代表首次启动，初始化空集合；加密文件只缓存信封，不在没有
        密码的情况下把账号数据放入内存。
        """

        if not self.path.exists():
            self.entries = []
            self.groups = [default_account_group()]
            self.password_entries = []
            self.password_groups = [default_password_group()]
            self.secure_settings = {}
            self.encrypted = False
            self._envelope = None
            return False

        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise VaultError("无法读取本地保险库") from error

        if not isinstance(document, dict) or document.get("format") != VAULT_FORMAT:
            raise VaultError("这不是验证器桌面版的保险库文件")

        self.encrypted = bool(document.get("encrypted", False))
        self._envelope = document
        self._key = None
        self._salt = None
        if self.encrypted:
            self.entries = []
            self.groups = [default_account_group()]
            self.password_entries = []
            self.password_groups = [default_password_group()]
            self.secure_settings = {}
            return True

        self._load_payload(document)
        return False

    def unlock(self, passphrase: str) -> None:
        """解密已加载信封并填充实体集合；错误密码或损坏文件转为 ``VaultError``。"""

        if not self.encrypted:
            return
        if not self._envelope:
            raise VaultError("尚未加载加密保险库")

        try:
            payload, key, salt, iterations = decrypt_payload(
                self._envelope, passphrase, VAULT_AAD
            )
        except VaultCryptoError as error:
            raise VaultError(str(error)) from error

        self._load_payload(payload)
        self._key = key
        self._salt = salt
        self._iterations = iterations

    def set_passphrase(self, passphrase: str | None) -> None:
        """设置/修改密码，或传入 ``None`` 移除加密，然后立即保存当前负载。"""

        if passphrase:
            self.encrypted = True
            self._salt = os.urandom(16)
            self._iterations = PBKDF2_ITERATIONS
            self._key = self._derive_key(passphrase, self._salt, self._iterations)
        else:
            self.encrypted = False
            self._key = None
            self._salt = None
            self._iterations = PBKDF2_ITERATIONS
        self.save()

    def lock(self) -> None:
        """锁定加密保险库：清空内存实体和派生密钥，保留信封以便再次解锁。"""

        if self.encrypted:
            self.entries = []
            self.groups = [default_account_group()]
            self.password_entries = []
            self.password_groups = [default_password_group()]
            self.secure_settings = {}
            self._key = None

    def save(self) -> None:
        """将当前状态写入临时文件、刷新到磁盘后原子替换正式保险库文件。"""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._payload()
        if self.encrypted:
            if not self._key or not self._salt:
                raise VaultError("请先解锁保险库后再进行修改")
            cipher_envelope = encrypt_payload_with_key(
                payload, self._key, self._salt, VAULT_AAD, self._iterations
            )
            document: dict[str, Any] = {
                "format": VAULT_FORMAT,
                "version": 1,
                "encrypted": True,
                **cipher_envelope,
            }
        else:
            document = {
                "format": VAULT_FORMAT,
                "version": 1,
                "encrypted": False,
                **payload,
            }

        # 同目录临时文件使 ``os.replace`` 在同一文件系统内保持原子性。
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            self._envelope = document
        except OSError as error:
            raise VaultError("无法保存本地保险库") from error
