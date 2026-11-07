"""Single structured bridge between the Android UI and shared Python services."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from application.account_service import AccountService
from application.backup_service import BackupService
from application.group_service import GroupService
from application.import_export import (
    BackupPasswordRequiredError,
    parse_import_text,
    parse_qr_content,
)
from application.import_service import ImportService
from application.password_commands import CreatePasswordCommand, UpdatePasswordCommand
from application.password_group_service import PasswordGroupService
from application.password_search_service import PasswordSearchService
from application.password_service import PasswordService
from application.provider_filters import (
    build_provider_filter_catalog,
    normalise_provider_key,
)
from application.search_service import SearchService
from application.server_commands import CreateServerCommand, UpdateServerCommand
from application.server_service import ServerService
from application.sorting import parse_otp_sort, parse_password_sort
from application.storage_service import StorageService
from domain.entities import DEFAULT_GROUP_ID, DEFAULT_GROUP_NAME, OTPEntry
from domain.google_authenticator import export_google_authenticator_migration
from domain.passwords import (
    PASSWORD_DEFAULT_GROUP_ID,
    PasswordGeneratorOptions,
    generate_password,
)
from domain.servers import ServerAuthKind, ServerProfile, TrustedHostKey
from domain.validators import utc_now_iso
from infrastructure.backup_codec import BackupCodec
from infrastructure.vault_repository import JsonVaultRepository
from infrastructure.vault_store import Vault


class JavaKeyProtector:
    """Adapt Kotlin byte-array methods to the shared Python protocol."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def protect(self, value: bytes) -> bytes:
        return bytes(self._bridge.protect(value))

    def unprotect(self, value: bytes) -> bytes:
        return bytes(self._bridge.unprotect(value))


class MemoryBackupStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def read_text(self, path: str) -> str:
        return self.values[path]

    def write_document(self, path: str, document: dict[str, Any]) -> None:
        self.values[path] = json.dumps(document, ensure_ascii=False, indent=2)

    def write_text(self, path: str, content: str) -> None:
        self.values[path] = content


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, dict):
        raise ValueError("请求内容必须是对象")
    return value


class MobileFacade:
    """Stateful mobile application service with JSON-only public results."""

    def __init__(self, data_directory: str, key_bridge: Any) -> None:
        directory = Path(data_directory)
        directory.mkdir(parents=True, exist_ok=True)
        protector = JavaKeyProtector(key_bridge)
        self.repository = JsonVaultRepository(directory / "vault.json", Vault, protector)
        self.vault = self.repository.create()
        self.storage = StorageService(self.vault, self.repository)
        self.accounts = AccountService(self.vault, self._save)
        self.search = SearchService()
        self.groups = GroupService(
            self.vault,
            self._save,
            default_group_name=DEFAULT_GROUP_NAME,
            all_accounts_label="全部账号",
            max_name_length=60,
        )
        self.password_search = PasswordSearchService()
        self.passwords = PasswordService(self.vault, self._save, self.password_search)
        self.password_groups = PasswordGroupService(self.vault, self._save)
        self.servers = ServerService(self.vault, self._save)
        self.importer = ImportService(self.vault, self._save, utc_now_iso)
        self.backup_files = MemoryBackupStore()
        self.backup = BackupService(
            BackupCodec(protector),
            self.backup_files,
            self.repository.store,
            utc_now_iso,
        )
        self._loaded = False
        self._locked = True

    def _save(self) -> None:
        self.repository.save(self.vault)

    def startup(self) -> str:
        result = self.storage.load()
        self._loaded = True
        self._locked = not result.unlocked
        return _json({"status": result.kind.value, "unlocked": result.unlocked})

    def initialize(self, passphrase: str) -> str:
        self.storage.initialize(passphrase)
        self._locked = False
        return self.snapshot()

    def unlock(self, passphrase: str) -> str:
        self.storage.unlock(passphrase)
        self._locked = False
        return self.snapshot()

    def lock(self) -> str:
        self.storage.lock()
        self._locked = True
        return _json({"locked": True})

    def change_master_password(self, current: str, new: str) -> str:
        self.storage.change_master_password(current, new)
        return _json({"changed": True})

    def snapshot(
        self,
        account_query: str = "",
        password_query: str = "",
        account_group_id: str = "",
        password_group_id: str = "",
        pinned_only: bool = False,
        account_sort_field: str = "created",
        account_sort_direction: str = "descending",
        password_sort_field: str = "created",
        password_sort_direction: str = "descending",
        account_favorite_only: bool = False,
        password_favorite_only: bool = False,
        account_show_pinned: bool = True,
        password_show_pinned: bool = True,
        account_provider_key: str = "",
        account_other_providers_only: bool = False,
    ) -> str:
        if self._locked:
            return _json({"locked": True, "accounts": [], "passwords": []})
        entries = list(self.vault.entries)
        provider_catalog = build_provider_filter_catalog(entries, lambda entry: entry.title)
        if account_group_id:
            entries = [entry for entry in entries if account_group_id in entry.group_ids]
        selected_provider_key = normalise_provider_key(account_provider_key)
        if selected_provider_key:
            entries = [
                entry
                for entry in entries
                if normalise_provider_key(entry.title) == selected_provider_key
            ]
        elif account_other_providers_only:
            entries = [
                entry
                for entry in entries
                if normalise_provider_key(entry.title) not in provider_catalog.top_keys
            ]
        if pinned_only:
            entries = [entry for entry in entries if entry.pinned]
        if account_favorite_only:
            entries = [entry for entry in entries if entry.favorite]
        if not account_show_pinned:
            entries = [entry for entry in entries if not entry.pinned]
        entries = self.search.search(
            entries,
            account_query,
            parse_otp_sort(account_sort_field, account_sort_direction),
        )

        password_entries = self.passwords.list(
            password_query,
            password_group_id or None,
            parse_password_sort(password_sort_field, password_sort_direction),
        )
        if pinned_only:
            password_entries = [entry for entry in password_entries if entry.pinned]
        if password_favorite_only:
            password_entries = [entry for entry in password_entries if entry.favorite]
        if not password_show_pinned:
            password_entries = [entry for entry in password_entries if not entry.pinned]
        return _json(
            {
                "locked": False,
                "accounts": [self._account_row(entry) for entry in entries],
                "groups": [group.to_dict() for group in self.vault.groups],
                "account_providers": [
                    {"key": provider.key, "label": provider.label, "count": provider.count}
                    for provider in provider_catalog.providers
                ],
                "other_provider_count": provider_catalog.other_count,
                "passwords": [self._password_row(entry) for entry in password_entries],
                "password_groups": [group.to_dict() for group in self.vault.password_groups],
                "servers": [self._server_row(profile) for profile in self.servers.list()],
            }
        )

    @staticmethod
    def _account_row(entry: OTPEntry) -> dict[str, Any]:
        try:
            code = entry.code()
            error = ""
        except ValueError as exc:
            code = "------"
            error = str(exc)
        return {
            "id": entry.id,
            "issuer": entry.issuer,
            "account": entry.account,
            "otp_type": entry.otp_type,
            "counter": entry.counter,
            "period": entry.period,
            "digits": entry.digits,
            "algorithm": entry.algorithm,
            "secret_encoding": entry.secret_encoding,
            "favorite": entry.favorite,
            "pinned": entry.pinned,
            "created_at": entry.created_at,
            "group_ids": list(entry.group_ids),
            "code": code,
            "remaining": entry.remaining_seconds(),
            "type_label": entry.type_label,
            "error": error,
        }

    @staticmethod
    def _password_row(entry: Any) -> dict[str, Any]:
        return {
            "id": entry.id,
            "name": entry.name,
            "title": entry.title,
            "username": entry.username,
            "url": entry.url,
            "favorite": entry.favorite,
            "pinned": entry.pinned,
            "created_at": entry.created_at,
            "group_ids": list(entry.group_ids),
        }

    @staticmethod
    def _server_row(profile: ServerProfile) -> dict[str, Any]:
        """Return only metadata that is safe to render in the Android UI."""

        trusted_key = profile.trusted_host_key
        return {
            "id": profile.id,
            "name": profile.name,
            "host": profile.host,
            "port": profile.port,
            "username": profile.username,
            "auth_kind": profile.auth_kind.value,
            "credentials_configured": profile.credentials_configured,
            "notes": profile.notes,
            "trusted_fingerprint": trusted_key.fingerprint if trusted_key else "",
            "trusted_algorithm": trusted_key.algorithm if trusted_key else "",
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    def _require_unlocked(self) -> None:
        if self._locked:
            raise ValueError("请先解锁保险库")

    @staticmethod
    def _server_command(data: dict[str, Any], *, update: bool) -> CreateServerCommand | UpdateServerCommand:
        try:
            auth_kind = ServerAuthKind(str(data.get("auth_kind", ServerAuthKind.PASSWORD)))
        except ValueError as error:
            raise ValueError("不支持的 SSH 认证方式") from error
        values = {
            "name": str(data.get("name") or ""),
            "host": str(data.get("host", data.get("ip", "")) or ""),
            "port": data.get("port", 22),
            "username": str(data.get("username") or ""),
            "auth_kind": auth_kind,
            "password": str(data.get("password") or ""),
            "private_key": str(data.get("private_key") or ""),
            "private_key_passphrase": str(data.get("private_key_passphrase") or ""),
            "notes": str(data.get("notes") or ""),
        }
        if update:
            return UpdateServerCommand(
                **values,
                replace_credentials=bool(data.get("replace_credentials", False)),
            )
        return CreateServerCommand(**values)

    def get_server(self, profile_id: str) -> str:
        self._require_unlocked()
        return _json(self._server_row(self.servers.get(profile_id)))

    def get_server_connection(self, profile_id: str) -> str:
        """Provide one profile to the native SSH worker only when connecting.

        This is deliberately separate from ``snapshot`` and never saved by the
        Kotlin UI. The response includes credentials only for the short-lived
        background connection setup.
        """

        self._require_unlocked()
        profile = self.servers.get(profile_id)
        profile.require_credentials()
        return _json(profile.to_dict())

    def create_server(self, raw: str) -> str:
        self._require_unlocked()
        profile = self.servers.create(self._server_command(_payload(raw), update=False))
        return _json(self._server_row(profile))

    def update_server(self, raw: str) -> str:
        self._require_unlocked()
        data = _payload(raw)
        profile_id = str(data.get("id") or "")
        if not profile_id:
            raise ValueError("服务器标识无效")
        profile = self.servers.update(profile_id, self._server_command(data, update=True))
        return _json(self._server_row(profile))

    def delete_server(self, profile_id: str) -> str:
        self._require_unlocked()
        self.servers.delete(profile_id)
        return _json({"deleted": True})

    def trust_server_host_key(self, raw: str) -> str:
        self._require_unlocked()
        data = _payload(raw)
        profile_id = str(data.get("profile_id") or "")
        trusted_key = TrustedHostKey(
            str(data.get("algorithm") or ""),
            str(data.get("key_data") or ""),
        )
        return _json(self._server_row(self.servers.set_trusted_host_key(profile_id, trusted_key)))

    def reset_server_host_key(self, profile_id: str) -> str:
        self._require_unlocked()
        return _json(self._server_row(self.servers.reset_trusted_host_key(profile_id)))

    def otp_dynamic_values(self) -> str:
        """Return only fields which change as a TOTP period advances.

        The Compose client calls this once per second.  Keeping this payload
        separate from ``snapshot`` avoids rebuilding password rows, group
        lists, and static account metadata on every tick.
        """

        if self._locked:
            return _json({"locked": True, "values": []})

        values: list[dict[str, Any]] = []
        for entry in self.vault.entries:
            try:
                code = entry.code()
                error = ""
            except ValueError as exc:
                code = "------"
                error = str(exc)
            values.append(
                {
                    "id": entry.id,
                    "code": code,
                    "remaining": entry.remaining_seconds(),
                    "error": error,
                }
            )
        return _json({"locked": False, "values": values})

    def get_account(self, entry_id: str) -> str:
        entry = next((item for item in self.vault.entries if item.id == entry_id), None)
        if entry is None:
            raise ValueError("验证码账号不存在")
        return _json(entry.to_dict())

    def export_account_uri(self, entry_id: str) -> str:
        entry = next((item for item in self.vault.entries if item.id == entry_id), None)
        if entry is None:
            raise ValueError("验证码账号不存在")
        return entry.to_uri()

    def get_password(self, entry_id: str) -> str:
        entry = next((item for item in self.vault.password_entries if item.id == entry_id), None)
        if entry is None:
            raise ValueError("密码记录不存在")
        return _json(entry.to_dict())

    def process_qr_payload(self, uri: str) -> str:
        """Preview one OTP account or atomically import a Google migration batch."""

        payload = parse_qr_content(uri)
        if payload.source == "otpauth":
            return _json({"kind": "single", "entry": payload.bundle.otp_entries[0].to_dict()})
        result = self.importer.import_bundle(payload.bundle)
        return _json(
            {
                "kind": "migration",
                "accounts_added": result.accounts_added,
                "duplicates_skipped": result.duplicates_skipped,
                "warnings": len(payload.bundle.warnings),
                "batch_size": payload.batch_size,
                "batch_index": payload.batch_index,
                "batch_id": payload.batch_id,
            }
        )

    def create_account(self, raw: str) -> str:
        data = _payload(raw)
        data.setdefault("id", str(uuid.uuid4()))
        data.setdefault("created_at", utc_now_iso())
        data.setdefault("group_ids", [DEFAULT_GROUP_ID])
        entry = self.accounts.create(OTPEntry.from_dict(data), data.get("active_group_id"))
        return _json(self._account_row(entry))

    def update_account(self, raw: str) -> str:
        entry = self.accounts.update(OTPEntry.from_dict(_payload(raw)))
        return _json(self._account_row(entry))

    def delete_accounts(self, raw_ids: str) -> str:
        count = self.accounts.delete(json.loads(raw_ids))
        return _json({"deleted": count})

    def toggle_account_pinned(self, entry_id: str) -> str:
        return _json(self._account_row(self.accounts.toggle_pinned(entry_id)))

    def set_account_pinned(self, raw_ids: str, pinned: bool) -> str:
        return _json({"changed": self.accounts.set_pinned(json.loads(raw_ids), pinned)})

    def set_account_favorite(self, raw_ids: str, favorite: bool) -> str:
        return _json({"changed": self.accounts.set_favorite(json.loads(raw_ids), favorite)})

    def increment_hotp(self, entry_id: str) -> str:
        return _json(self._account_row(self.accounts.increment_hotp(entry_id)))

    def create_group(self, name: str) -> str:
        return _json(self.groups.create(name).to_dict())

    def rename_group(self, group_id: str, name: str) -> str:
        return _json(self.groups.rename(group_id, name).to_dict())

    def delete_group(self, group_id: str) -> str:
        return _json(self.groups.delete(group_id).to_dict())

    def assign_account_groups(self, raw_ids: str, raw_groups: str) -> str:
        ids = json.loads(raw_ids)
        groups = json.loads(raw_groups)
        return _json({"changed": self.groups.assign(ids, groups)})

    def create_password(self, raw: str) -> str:
        data = _payload(raw)
        command = CreatePasswordCommand(
            username=str(data.get("username", "")),
            password=str(data.get("password", "")),
            name=str(data.get("name", "")),
            url=str(data.get("url", "")),
            notes=str(data.get("notes", "")),
            pinned=bool(data.get("pinned", False)),
            group_ids=tuple(data.get("group_ids") or [PASSWORD_DEFAULT_GROUP_ID]),
            favorite=bool(data.get("favorite", False)),
        )
        return _json(self.passwords.create(command).to_dict())

    def update_password(self, entry_id: str, raw: str) -> str:
        data = _payload(raw)
        command = UpdatePasswordCommand(
            username=str(data.get("username", "")),
            password=str(data.get("password", "")),
            name=str(data.get("name", "")),
            url=str(data.get("url", "")),
            notes=str(data.get("notes", "")),
            pinned=bool(data.get("pinned", False)),
            group_ids=tuple(data.get("group_ids") or [PASSWORD_DEFAULT_GROUP_ID]),
            favorite=bool(data.get("favorite", False)),
        )
        return _json(self.passwords.update(entry_id, command).to_dict())

    def delete_passwords(self, raw_ids: str) -> str:
        return _json({"deleted": self.passwords.delete(json.loads(raw_ids))})

    def set_password_pinned(self, raw_ids: str, pinned: bool) -> str:
        return _json({"changed": self.passwords.set_pinned(json.loads(raw_ids), pinned)})

    def set_password_favorite(self, raw_ids: str, favorite: bool) -> str:
        return _json({"changed": self.passwords.set_favorite(json.loads(raw_ids), favorite)})

    def create_password_group(self, name: str) -> str:
        return _json(self.password_groups.create(name).to_dict())

    def rename_password_group(self, group_id: str, name: str) -> str:
        return _json(self.password_groups.rename(group_id, name).to_dict())

    def delete_password_group(self, group_id: str) -> str:
        return _json(self.password_groups.delete(group_id).to_dict())

    def assign_password_groups(self, raw_ids: str, raw_groups: str) -> str:
        return _json({"changed": self.password_groups.assign(json.loads(raw_ids), json.loads(raw_groups))})

    def generate_password(self, raw: str) -> str:
        data = _payload(raw)
        options = PasswordGeneratorOptions(
            length=int(data.get("length", 20)),
            lowercase=bool(data.get("lowercase", True)),
            uppercase=bool(data.get("uppercase", True)),
            digits=bool(data.get("digits", True)),
            symbols=bool(data.get("symbols", True)),
            exclude_ambiguous=bool(data.get("exclude_ambiguous", True)),
        )
        return generate_password(options)

    def export_backup(self, encrypted: bool) -> str:
        key = "backup"
        if encrypted:
            self.backup.export_encrypted(key, self.vault)
        else:
            self.backup.export_plain(key, self.vault)
        return self.backup_files.values[key]

    def export_google_authenticator(self) -> str:
        """Return Google-compatible migration QR payloads without writing plaintext files."""

        exported = export_google_authenticator_migration(list(self.vault.entries))
        return _json(
            {
                "uris": list(exported.uris),
                "accounts_exported": exported.accounts_exported,
                "warnings": list(exported.warnings),
            }
        )

    def import_backup(self, content: str, passphrase: str = "") -> str:
        try:
            document = json.loads(content)
        except json.JSONDecodeError:
            document = None
        if self.backup.codec.is_encrypted_document(document):
            try:
                payload = self.backup.codec.decrypt(document, passphrase or None)
            except BackupPasswordRequiredError:
                return _json({"password_required": True})
            bundle = parse_import_text(json.dumps(payload, ensure_ascii=False))
        else:
            bundle = parse_import_text(content)
        result = self.importer.import_bundle(bundle)
        return _json({**result.__dict__, "warnings": bundle.warnings, "password_required": False})


def create_facade(data_directory: str, key_bridge: Any) -> MobileFacade:
    return MobileFacade(data_directory, key_bridge)
