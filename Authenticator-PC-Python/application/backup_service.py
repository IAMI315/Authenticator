"""备份文件、格式识别和业务数据快照的应用服务。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from application.import_export import ImportBundle, parse_import_text


class BackupCodecPort(Protocol):
    def encrypt(
        self,
        payload: dict[str, Any],
        *,
        key_id: str,
        data_key: bytes,
        password_wrap: dict[str, Any],
    ) -> dict[str, Any]: ...

    def decrypt(self, document: dict[str, Any], passphrase: str | None = None) -> dict[str, Any]: ...

    def is_encrypted_document(self, document: Any) -> bool: ...


class BackupFilePort(Protocol):
    def read_text(self, path: str) -> str: ...

    def write_document(self, path: str, document: dict[str, Any]) -> None: ...

    def write_text(self, path: str, content: str) -> None: ...


class BackupKeySource(Protocol):
    @property
    def key_id(self) -> str: ...

    @property
    def data_key(self) -> bytes: ...

    @property
    def password_wrap(self) -> dict[str, Any]: ...


class BackupService:
    """向 UI 提供不暴露文件和加密细节的备份用例。"""

    def __init__(
        self,
        codec: BackupCodecPort,
        files: BackupFilePort,
        key_source: BackupKeySource,
        exported_at_factory: Callable[[], str],
    ) -> None:
        self.codec = codec
        self.files = files
        self.key_source = key_source
        self.exported_at_factory = exported_at_factory

    def load(self, path: str, passphrase: str | None = None) -> ImportBundle:
        content = self.files.read_text(path)
        try:
            document = json.loads(content)
        except json.JSONDecodeError:
            document = None
        if self.codec.is_encrypted_document(document):
            payload = self.codec.decrypt(document, passphrase)
            return parse_import_text(json.dumps(payload, ensure_ascii=False))
        return parse_import_text(content)

    def export_encrypted(self, path: str, vault: Any) -> None:
        payload = self._payload(vault, include_server_secrets=True)
        document = self.codec.encrypt(
            payload,
            key_id=self.key_source.key_id,
            data_key=self.key_source.data_key,
            password_wrap=self.key_source.password_wrap,
        )
        self.files.write_document(path, document)

    def export_plain(self, path: str, vault: Any) -> None:
        self.files.write_document(path, {**self._payload(vault, include_server_secrets=False), "encrypted": False})

    def export_uris(self, path: str, entries: Any) -> None:
        content = "\n".join(entry.to_uri() for entry in entries) + "\n"
        self.files.write_text(path, content)

    def _payload(self, vault: Any, *, include_server_secrets: bool) -> dict[str, Any]:
        return {
            "format": "authenticator-desktop/v1",
            "version": 1,
            "exported_at": self.exported_at_factory(),
            "entries": [entry.to_dict() for entry in vault.entries],
            "groups": [group.to_dict() for group in vault.groups],
            "password_entries": [entry.to_dict() for entry in vault.password_entries],
            "password_groups": [group.to_dict() for group in vault.password_groups],
            "server_profiles": [
                profile.to_dict() if include_server_secrets else profile.to_plain_backup_dict()
                for profile in vault.server_profiles
            ],
        }
