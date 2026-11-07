"""SSH server profile entities kept entirely independent from UI and transport."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from domain.validators import normalise_created_at, utc_now_iso


class ServerAuthKind(StrEnum):
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"


def normalise_ssh_host(value: Any) -> str:
    """Validate a hostname, IPv4 address, or IPv6 address without resolving it."""

    host = str(value or "").strip().removeprefix("[").removesuffix("]")
    if not host or len(host) > 253 or any(character.isspace() for character in host):
        raise ValueError("请输入有效的 IP 或域名")
    if any(character in host for character in "/\\@") or "://" in host:
        raise ValueError("IP 或域名不能包含协议、路径或用户名")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if host.startswith(".") or host.endswith(".") or ".." in host:
        raise ValueError("请输入有效的 IP 或域名")
    labels = host.split(".")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        raise ValueError("请输入有效的 IP 或域名")
    if not all(character.isalnum() or character in "-." for character in host):
        raise ValueError("IP 或域名只能包含字母、数字、连字符和点")
    return host.casefold()


@dataclass
class TrustedHostKey:
    """The exact host public key required for later SSH verification."""

    algorithm: str
    key_data: str

    def validate(self) -> None:
        self.algorithm = str(self.algorithm or "").strip()
        self.key_data = str(self.key_data or "").strip()
        if not self.algorithm or len(self.algorithm) > 128:
            raise ValueError("服务器主机密钥算法无效")
        if not self.key_data or len(self.key_data) > 16_384:
            raise ValueError("服务器主机密钥无效")
        try:
            base64.b64decode(self.key_data.encode("ascii"), validate=True)
        except Exception as error:
            raise ValueError("服务器主机密钥编码无效") from error

    @property
    def fingerprint(self) -> str:
        raw = base64.b64decode(self.key_data.encode("ascii"))
        digest = base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
        return f"SHA256:{digest}"

    def to_dict(self) -> dict[str, str]:
        return {"algorithm": self.algorithm, "key_data": self.key_data}

    @classmethod
    def from_dict(cls, value: Any) -> TrustedHostKey:
        if not isinstance(value, dict):
            raise ValueError("服务器主机密钥格式无效")
        result = cls(str(value.get("algorithm") or ""), str(value.get("key_data") or ""))
        result.validate()
        return result


@dataclass
class ServerProfile:
    id: str
    name: str
    host: str
    port: int = 22
    username: str = ""
    auth_kind: ServerAuthKind = ServerAuthKind.PASSWORD
    password: str = ""
    private_key: str = ""
    private_key_passphrase: str = ""
    notes: str = ""
    trusted_host_key: TrustedHostKey | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def credentials_configured(self) -> bool:
        return bool(self.password) if self.auth_kind is ServerAuthKind.PASSWORD else bool(self.private_key)

    @property
    def connection_identity(self) -> tuple[str, str, int, str]:
        return self.name.casefold(), self.host, self.port, self.username.casefold()

    def validate(self) -> None:
        self.id = str(self.id or "").strip()
        self.name = " ".join(str(self.name or "").split())
        self.host = normalise_ssh_host(self.host)
        self.username = str(self.username or "").strip()
        self.notes = str(self.notes or "").strip()
        self.password = str(self.password or "")
        self.private_key = str(self.private_key or "")
        self.private_key_passphrase = str(self.private_key_passphrase or "")
        if not self.id or len(self.id) > 128:
            raise ValueError("服务器标识无效")
        if not self.name:
            raise ValueError("请输入服务器名称")
        if len(self.name) > 200:
            raise ValueError("服务器名称不能超过 200 个字符")
        if not self.username or len(self.username) > 320:
            raise ValueError("请输入有效的用户名")
        try:
            self.port = int(self.port)
        except (TypeError, ValueError) as error:
            raise ValueError("SSH 端口必须是 1 到 65535 的整数") from error
        if not 1 <= self.port <= 65_535:
            raise ValueError("SSH 端口必须是 1 到 65535 的整数")
        try:
            self.auth_kind = ServerAuthKind(str(self.auth_kind))
        except ValueError as error:
            raise ValueError("不支持的 SSH 认证方式") from error
        if len(self.password) > 4096 or len(self.private_key_passphrase) > 4096:
            raise ValueError("SSH 凭据不能超过 4096 个字符")
        if len(self.private_key) > 65_536:
            raise ValueError("私钥文件过大")
        if len(self.notes) > 10_000:
            raise ValueError("备注不能超过 10000 个字符")
        if self.trusted_host_key is not None:
            self.trusted_host_key.validate()
        self.created_at = normalise_created_at(self.created_at) or utc_now_iso()
        self.updated_at = normalise_created_at(self.updated_at) or self.created_at

    def require_credentials(self) -> None:
        if not self.credentials_configured:
            message = "请先设置 SSH 密码" if self.auth_kind is ServerAuthKind.PASSWORD else "请先导入 SSH 私钥"
            raise ValueError(message)

    def to_dict(self, *, include_secrets: bool = True) -> dict[str, Any]:
        document: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth_kind": self.auth_kind.value,
            "notes": self.notes,
            "trusted_host_key": self.trusted_host_key.to_dict() if self.trusted_host_key else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_secrets:
            document.update(
                {
                    "password": self.password,
                    "private_key": self.private_key,
                    "private_key_passphrase": self.private_key_passphrase,
                }
            )
        return document

    def to_plain_backup_dict(self) -> dict[str, Any]:
        """Return only the server metadata allowed in a readable backup."""

        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, value: Any) -> ServerProfile:
        if not isinstance(value, dict):
            raise ValueError("服务器记录必须是对象")
        raw_trusted_key = value.get("trusted_host_key", value.get("trustedHostKey"))
        profile = cls(
            id=str(value.get("id") or uuid.uuid4()),
            name=str(value.get("name") or ""),
            host=str(value.get("host", value.get("ip", "")) or ""),
            port=value.get("port", 22),
            username=str(value.get("username") or ""),
            auth_kind=ServerAuthKind(str(value.get("auth_kind", value.get("authKind", ServerAuthKind.PASSWORD)))),
            password=str(value.get("password") or ""),
            private_key=str(value.get("private_key", value.get("privateKey", "")) or ""),
            private_key_passphrase=str(
                value.get("private_key_passphrase", value.get("privateKeyPassphrase", "")) or ""
            ),
            notes=str(value.get("notes") or ""),
            trusted_host_key=TrustedHostKey.from_dict(raw_trusted_key) if raw_trusted_key else None,
            created_at=value.get("created_at", value.get("createdAt")),
            updated_at=value.get("updated_at", value.get("updatedAt")),
        )
        profile.validate()
        return profile
