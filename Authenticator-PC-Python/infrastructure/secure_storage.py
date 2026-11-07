"""强制加密的本地数据存储与旧保险库迁移。"""

from __future__ import annotations

import base64
import json
import os
import secrets
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from domain.entities import default_account_group
from domain.passwords import default_password_group
from infrastructure.crypto import (
    VaultCryptoError,
    decrypt_json_with_key,
    decrypt_payload,
    encrypt_json_with_key,
    unwrap_data_key,
    wrap_data_key,
)
from infrastructure.errors import VaultError
from infrastructure.key_protection import DeviceKeyProtector
from infrastructure.vault_store import PBKDF2_ITERATIONS, VAULT_AAD, VAULT_FORMAT

VAULT_VERSION = 2
MIN_MASTER_PASSWORD_LENGTH = 8
LOCAL_PAYLOAD_AAD = b"authenticator-desktop/v2/payload"
PASSWORD_WRAP_AAD = b"authenticator-desktop/v2/password-wrap"
DEVICE_KEY_FORMAT = "authenticator-desktop/device-key-v1"


class StorageLoadKind(StrEnum):
    AUTO_UNLOCKED = "auto_unlocked"
    NEEDS_SETUP = "needs_setup"
    NEEDS_PASSWORD = "needs_password"
    NEEDS_LEGACY_PASSWORD = "needs_legacy_password"


@dataclass(frozen=True)
class StorageLoadResult:
    kind: StorageLoadKind

    @property
    def unlocked(self) -> bool:
        return self.kind == StorageLoadKind.AUTO_UNLOCKED


def validate_master_password(passphrase: str) -> None:
    if len(passphrase) < MIN_MASTER_PASSWORD_LENGTH:
        raise VaultError(f"主密码至少需要 {MIN_MASTER_PASSWORD_LENGTH} 个字符")


class EncryptedDataStore:
    """拥有本地 v2 信封、数据密钥和设备自动解锁凭据。"""

    def __init__(
        self,
        vault_path: Path,
        device_key_path: Path,
        protector: DeviceKeyProtector,
    ) -> None:
        self.vault_path = vault_path
        self.device_key_path = device_key_path
        self.protector = protector
        self._data_key: bytes | None = None
        self._key_id: str | None = None
        self._password_wrap: dict[str, Any] | None = None
        self._document: dict[str, Any] | None = None
        self._legacy_document: dict[str, Any] | None = None

    @property
    def data_key(self) -> bytes:
        if self._data_key is None:
            raise VaultError("安全数据尚未解锁")
        return self._data_key

    @property
    def key_id(self) -> str:
        if self._key_id is None:
            raise VaultError("安全数据缺少密钥标识")
        return self._key_id

    @property
    def password_wrap(self) -> dict[str, Any]:
        if self._password_wrap is None:
            raise VaultError("安全数据缺少主密码恢复信息")
        return json.loads(json.dumps(self._password_wrap))

    def load(self, vault: Any) -> StorageLoadResult:
        self._clear_crypto_state()
        if not self.vault_path.exists():
            self._reset_vault(vault)
            vault.encrypted = False
            return StorageLoadResult(StorageLoadKind.NEEDS_SETUP)
        document = self._read_document(self.vault_path)
        if document.get("format") != VAULT_FORMAT:
            raise VaultError("这不是验证器桌面版的保险库文件")
        version = int(document.get("version", 1))
        if version == VAULT_VERSION and document.get("encrypted") is True:
            self._load_v2_metadata(document)
            self._reset_vault(vault)
            vault.encrypted = True
            try:
                data_key = self._read_device_key(self.key_id)
                self._decrypt_v2(vault, data_key)
            except (VaultError, VaultCryptoError):
                self._data_key = None
                return StorageLoadResult(StorageLoadKind.NEEDS_PASSWORD)
            self._data_key = data_key
            if vault.migration_pending:
                try:
                    self.save(vault)
                    vault.migration_pending = False
                except Exception:
                    self._data_key = None
                    self._reset_vault(vault)
                    vault.encrypted = True
                    raise
            return StorageLoadResult(StorageLoadKind.AUTO_UNLOCKED)
        self._legacy_document = document
        if document.get("encrypted") is True:
            self._reset_vault(vault)
            vault.encrypted = True
            return StorageLoadResult(StorageLoadKind.NEEDS_LEGACY_PASSWORD)
        vault.encrypted = False
        vault._load_payload(document)
        return StorageLoadResult(StorageLoadKind.NEEDS_SETUP)

    def initialize(self, vault: Any, passphrase: str) -> None:
        validate_master_password(passphrase)
        data_key = secrets.token_bytes(32)
        key_id = str(uuid.uuid4())
        password_envelope = wrap_data_key(
            data_key,
            passphrase,
            self._aad(PASSWORD_WRAP_AAD, key_id),
            PBKDF2_ITERATIONS,
        )
        protected_key = self.protector.protect(data_key)
        previous_state = (self._data_key, self._key_id, self._password_wrap, self._document)
        self._data_key = data_key
        self._key_id = key_id
        self._password_wrap = password_envelope
        vault.encrypted = True
        try:
            self._write_device_key(key_id, protected_key)
            self.save(vault)
            vault.migration_pending = False
        except Exception:
            self._data_key, self._key_id, self._password_wrap, self._document = previous_state
            raise
        self._legacy_document = None

    def unlock(self, vault: Any, passphrase: str, *, bind_device: bool = True) -> None:
        if self._legacy_document is not None:
            document = self._legacy_document
            pending_secure_settings = dict(vault.secure_settings)
            try:
                payload, _legacy_key, _salt, _iterations = decrypt_payload(
                    document,
                    passphrase,
                    VAULT_AAD,
                )
            except VaultCryptoError as error:
                raise VaultError(str(error)) from error
            vault._load_payload(payload)
            vault.secure_settings.update(pending_secure_settings)
            self.initialize(vault, passphrase)
            return
        try:
            data_key = unwrap_data_key(
                self.password_wrap,
                passphrase,
                self._aad(PASSWORD_WRAP_AAD, self.key_id),
            )
            self._decrypt_v2(vault, data_key)
        except VaultCryptoError as error:
            raise VaultError(str(error)) from error
        self._data_key = data_key
        if vault.migration_pending:
            try:
                self.save(vault)
                vault.migration_pending = False
            except Exception:
                self._data_key = None
                self._reset_vault(vault)
                vault.encrypted = True
                raise
        if bind_device:
            self._write_device_key(self.key_id, self.protector.protect(data_key))

    def save(self, vault: Any) -> None:
        key_id = self.key_id
        document: dict[str, Any] = {
            "format": VAULT_FORMAT,
            "version": VAULT_VERSION,
            "encrypted": True,
            "key_id": key_id,
            "password_wrap": self.password_wrap,
            "cipher": encrypt_json_with_key(
                vault._payload(),
                self.data_key,
                self._aad(LOCAL_PAYLOAD_AAD, key_id),
            ),
        }
        self._write_document(self.vault_path, document)
        self._document = document

    def lock(self, vault: Any) -> None:
        self._data_key = None
        self._reset_vault(vault)
        vault.encrypted = True

    def change_master_password(self, vault: Any, current: str, new: str) -> None:
        validate_master_password(new)
        try:
            verified_key = unwrap_data_key(
                self.password_wrap,
                current,
                self._aad(PASSWORD_WRAP_AAD, self.key_id),
            )
        except VaultCryptoError as error:
            raise VaultError("当前主密码不正确") from error
        if not secrets.compare_digest(verified_key, self.data_key):
            raise VaultError("当前主密码不正确")
        previous_wrap = self._password_wrap
        self._password_wrap = wrap_data_key(
            self.data_key,
            new,
            self._aad(PASSWORD_WRAP_AAD, self.key_id),
            PBKDF2_ITERATIONS,
        )
        try:
            self.save(vault)
        except Exception:
            self._password_wrap = previous_wrap
            raise

    def protect_for_device(self, data_key: bytes | None = None) -> bytes:
        return self.protector.protect(data_key or self.data_key)

    def unprotect_for_device(self, protected_key: bytes) -> bytes:
        data_key = self.protector.unprotect(protected_key)
        if len(data_key) != 32:
            raise VaultError("设备密钥长度无效")
        return data_key

    def _decrypt_v2(self, vault: Any, data_key: bytes) -> None:
        if self._document is None:
            raise VaultError("尚未加载安全数据")
        try:
            payload = decrypt_json_with_key(
                self._document["cipher"],
                data_key,
                self._aad(LOCAL_PAYLOAD_AAD, self.key_id),
            )
            vault._load_payload(payload)
        except (KeyError, VaultCryptoError) as error:
            raise VaultError("无法解密本地安全数据") from error

    def _load_v2_metadata(self, document: dict[str, Any]) -> None:
        key_id = document.get("key_id")
        password_envelope = document.get("password_wrap")
        cipher = document.get("cipher")
        if not isinstance(key_id, str) or not key_id:
            raise VaultError("本地安全数据缺少密钥标识")
        if not isinstance(password_envelope, dict) or not isinstance(cipher, dict):
            raise VaultError("本地安全数据的加密信封不完整")
        self._key_id = key_id
        self._password_wrap = password_envelope
        self._document = document

    def _read_device_key(self, expected_key_id: str) -> bytes:
        document = self._read_document(self.device_key_path)
        if (
            document.get("format") != DEVICE_KEY_FORMAT
            or document.get("version") != 1
            or document.get("key_id") != expected_key_id
        ):
            raise VaultError("本机自动解锁凭据不匹配")
        try:
            protected_key = base64.b64decode(document["protected_key"], validate=True)
        except Exception as error:
            raise VaultError("本机自动解锁凭据已损坏") from error
        return self.unprotect_for_device(protected_key)

    def _write_device_key(self, key_id: str, protected_key: bytes) -> None:
        self._write_document(
            self.device_key_path,
            {
                "format": DEVICE_KEY_FORMAT,
                "version": 1,
                "key_id": key_id,
                "protected_key": base64.b64encode(protected_key).decode("ascii"),
            },
        )

    @staticmethod
    def _read_document(path: Path) -> dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise VaultError(f"无法读取数据文件：{path.name}") from error
        if not isinstance(document, dict):
            raise VaultError(f"数据文件格式不正确：{path.name}")
        return document

    @staticmethod
    def _write_document(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError as error:
            raise VaultError(f"无法保存数据文件：{path.name}") from error

    @staticmethod
    def _aad(prefix: bytes, key_id: str) -> bytes:
        return prefix + b":" + key_id.encode("ascii")

    @staticmethod
    def _reset_vault(vault: Any) -> None:
        vault.entries = []
        vault.groups = [default_account_group()]
        vault.password_entries = []
        vault.password_groups = [default_password_group()]
        vault.server_profiles = []
        vault.secure_settings = {}
        vault.migration_pending = False

    def _clear_crypto_state(self) -> None:
        self._data_key = None
        self._key_id = None
        self._password_wrap = None
        self._document = None
        self._legacy_document = None
