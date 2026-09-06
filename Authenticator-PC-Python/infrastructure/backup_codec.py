"""桌面版加密备份信封编解码。"""

from __future__ import annotations

import base64
import json
from copy import deepcopy
from typing import Any

from application.import_export import BackupPasswordRequiredError
from infrastructure.crypto import (
    VaultCryptoError,
    decrypt_json_with_key,
    encrypt_json_with_key,
    unwrap_data_key,
)
from infrastructure.errors import VaultError
from infrastructure.key_protection import DeviceKeyProtector

BACKUP_FORMAT = "authenticator-desktop/backup-v1"
BACKUP_PAYLOAD_AAD = b"authenticator-desktop/backup-v1/payload"
BACKUP_PASSWORD_WRAP_AAD = b"authenticator-desktop/v2/password-wrap"


class BackupCodec:
    """使用设备凭据无感解密，并保留主密码跨机恢复能力。"""

    def __init__(self, protector: DeviceKeyProtector) -> None:
        self.protector = protector

    def encrypt(
        self,
        payload: dict[str, Any],
        *,
        key_id: str,
        data_key: bytes,
        password_wrap: dict[str, Any],
    ) -> dict[str, Any]:
        if len(data_key) != 32:
            raise VaultError("备份数据密钥长度无效")
        protected_key = self.protector.protect(data_key)
        return {
            "format": BACKUP_FORMAT,
            "version": 1,
            "encrypted": True,
            "key_id": key_id,
            "password_wrap": deepcopy(password_wrap),
            "device_wrap": base64.b64encode(protected_key).decode("ascii"),
            "cipher": encrypt_json_with_key(payload, data_key, self._payload_aad(key_id)),
        }

    def decrypt(self, document: dict[str, Any], passphrase: str | None = None) -> dict[str, Any]:
        key_id = document.get("key_id")
        if (
            document.get("format") != BACKUP_FORMAT
            or document.get("version") != 1
            or document.get("encrypted") is not True
            or not isinstance(key_id, str)
        ):
            raise VaultError("这不是受支持的加密备份")
        data_key: bytes
        if passphrase is None:
            try:
                protected_key = base64.b64decode(document["device_wrap"], validate=True)
                data_key = self.protector.unprotect(protected_key)
                if len(data_key) != 32:
                    raise ValueError("设备密钥长度无效")
            except Exception as error:
                raise BackupPasswordRequiredError("请输入生成该备份时的主密码") from error
        else:
            password_wrap = document.get("password_wrap")
            if not isinstance(password_wrap, dict):
                raise VaultError("加密备份缺少主密码恢复信息")
            try:
                data_key = unwrap_data_key(
                    password_wrap,
                    passphrase,
                    self._password_wrap_aad(key_id),
                )
            except VaultCryptoError as error:
                raise VaultError("备份主密码不正确，或备份已损坏") from error
        cipher = document.get("cipher")
        if not isinstance(cipher, dict):
            raise VaultError("加密备份缺少数据密文")
        try:
            return decrypt_json_with_key(cipher, data_key, self._payload_aad(key_id))
        except VaultCryptoError as error:
            raise VaultError("无法解密备份，文件可能已损坏") from error

    @staticmethod
    def is_encrypted_document(document: Any) -> bool:
        return (
            isinstance(document, dict)
            and document.get("format") == BACKUP_FORMAT
            and document.get("encrypted") is True
        )

    @staticmethod
    def loads(text: str) -> dict[str, Any]:
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise VaultError("加密备份不是有效的 JSON 文件") from error
        if not isinstance(document, dict):
            raise VaultError("加密备份格式不正确")
        return document

    @staticmethod
    def _payload_aad(key_id: str) -> bytes:
        return BACKUP_PAYLOAD_AAD + b":" + key_id.encode("ascii")

    @staticmethod
    def _password_wrap_aad(key_id: str) -> bytes:
        return BACKUP_PASSWORD_WRAP_AAD + b":" + key_id.encode("ascii")
