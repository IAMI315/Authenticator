"""保险库 AES-256-GCM 加密信封编解码。

本模块只处理字节和 JSON 对象，不了解 Tkinter 或磁盘路径。保险库格式兼容性由
``Vault`` 负责，密码派生参数和认证附加数据由调用方显式传入。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class VaultCryptoError(ValueError):
    """加密信封字段、密码或认证标签无效时抛出的安全边界异常。"""


def derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    """使用 PBKDF2-HMAC-SHA256 派生固定 32 字节（AES-256）密钥。"""

    return hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32
    )


def encrypt_payload(
    payload: dict[str, Any],
    passphrase: str,
    aad: bytes,
    iterations: int,
) -> tuple[dict[str, Any], bytes, bytes]:
    """随机生成盐和派生密钥，返回加密信封及供当前会话缓存的密钥材料。"""

    salt = os.urandom(16)
    key = derive_key(passphrase, salt, iterations)
    envelope = encrypt_payload_with_key(payload, key, salt, aad, iterations)
    return envelope, key, salt


def encrypt_payload_with_key(
    payload: dict[str, Any],
    key: bytes,
    salt: bytes,
    aad: bytes,
    iterations: int,
) -> dict[str, Any]:
    """使用现有密钥加密 JSON 负载，生成可写入保险库的 KDF/cipher 信封。"""

    # nonce 必须对同一 AES-GCM 密钥唯一；每次保存都生成新的 96 位随机 nonce。
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        aad,
    )
    envelope = {
        "kdf": {
            "name": "PBKDF2-HMAC-SHA256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode("ascii"),
        },
        "cipher": {
            "name": "AES-256-GCM",
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "data": base64.b64encode(ciphertext).decode("ascii"),
        },
    }
    return envelope


def decrypt_payload(
    envelope: dict[str, Any],
    passphrase: str,
    aad: bytes,
    minimum_iterations: int = 100_000,
) -> tuple[dict[str, Any], bytes, bytes, int]:
    """验证信封并解密 JSON，返回负载、派生密钥、盐和实际迭代次数。

    所有可预期的解码/认证失败都折叠为 ``VaultCryptoError``，避免向上层泄露
    密码或底层密码学细节。
    """

    try:
        kdf = envelope["kdf"]
        cipher = envelope["cipher"]
        salt = base64.b64decode(kdf["salt"], validate=True)
        nonce = base64.b64decode(cipher["nonce"], validate=True)
        ciphertext = base64.b64decode(cipher["data"], validate=True)
        iterations = int(kdf["iterations"])
        if len(salt) < 16 or len(nonce) != 12 or iterations < minimum_iterations:
            raise ValueError("保险库加密参数无效")
        key = derive_key(passphrase, salt, iterations)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("保险库内容不是对象")
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        binascii.Error,
        InvalidTag,
        json.JSONDecodeError,
    ) as error:
        raise VaultCryptoError("密码不正确，或保险库文件已损坏") from error
    return payload, key, salt, iterations


def encrypt_json_with_key(payload: dict[str, Any], key: bytes, aad: bytes) -> dict[str, str]:
    """使用给定 AES-256 密钥加密 JSON，并返回不含密钥派生信息的信封。"""

    if len(key) != 32:
        raise VaultCryptoError("数据加密密钥长度无效")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        aad,
    )
    return {
        "name": "AES-256-GCM",
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "data": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_json_with_key(
    cipher: dict[str, Any],
    key: bytes,
    aad: bytes,
) -> dict[str, Any]:
    """解密并验证 JSON 信封；认证失败统一转换为 ``VaultCryptoError``。"""

    try:
        if len(key) != 32 or cipher.get("name") != "AES-256-GCM":
            raise ValueError("加密参数无效")
        nonce = base64.b64decode(cipher["nonce"], validate=True)
        ciphertext = base64.b64decode(cipher["data"], validate=True)
        if len(nonce) != 12:
            raise ValueError("nonce 长度无效")
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("解密内容不是对象")
        return payload
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        binascii.Error,
        InvalidTag,
        json.JSONDecodeError,
    ) as error:
        raise VaultCryptoError("密码或设备凭据不正确，或加密数据已损坏") from error


def wrap_data_key(
    data_key: bytes,
    passphrase: str,
    aad: bytes,
    iterations: int,
) -> dict[str, Any]:
    """用主密码派生的密钥包装随机数据密钥。"""

    if len(data_key) != 32:
        raise VaultCryptoError("数据加密密钥长度无效")
    salt = os.urandom(16)
    wrapping_key = derive_key(passphrase, salt, iterations)
    nonce = os.urandom(12)
    ciphertext = AESGCM(wrapping_key).encrypt(nonce, data_key, aad)
    return {
        "kdf": {
            "name": "PBKDF2-HMAC-SHA256",
            "iterations": iterations,
            "salt": base64.b64encode(salt).decode("ascii"),
        },
        "cipher": {
            "name": "AES-256-GCM",
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "data": base64.b64encode(ciphertext).decode("ascii"),
        },
    }


def unwrap_data_key(
    envelope: dict[str, Any],
    passphrase: str,
    aad: bytes,
    minimum_iterations: int = 100_000,
) -> bytes:
    """验证主密码包装信封并返回 256 位数据密钥。"""

    try:
        kdf = envelope["kdf"]
        cipher = envelope["cipher"]
        if kdf.get("name") != "PBKDF2-HMAC-SHA256" or cipher.get("name") != "AES-256-GCM":
            raise ValueError("密钥包装参数无效")
        iterations = int(kdf["iterations"])
        salt = base64.b64decode(kdf["salt"], validate=True)
        nonce = base64.b64decode(cipher["nonce"], validate=True)
        ciphertext = base64.b64decode(cipher["data"], validate=True)
        if iterations < minimum_iterations or len(salt) < 16 or len(nonce) != 12:
            raise ValueError("密钥包装参数无效")
        wrapping_key = derive_key(passphrase, salt, iterations)
        data_key = AESGCM(wrapping_key).decrypt(nonce, ciphertext, aad)
        if len(data_key) != 32:
            raise ValueError("数据密钥长度无效")
        return data_key
    except (
        KeyError,
        TypeError,
        ValueError,
        binascii.Error,
        InvalidTag,
    ) as error:
        raise VaultCryptoError("主密码不正确，或密钥包装数据已损坏") from error
