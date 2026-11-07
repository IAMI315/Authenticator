"""Transactional use cases for encrypted SSH server profiles."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from copy import deepcopy
from typing import Any

from application.server_commands import CreateServerCommand, UpdateServerCommand
from domain.servers import ServerAuthKind, ServerProfile, TrustedHostKey
from domain.validators import utc_now_iso


class ServerService:
    def __init__(
        self,
        vault: Any,
        save: Callable[[], None],
        now_factory: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.vault = vault
        self._save = save
        self._now_factory = now_factory

    def _transaction(self, operation: Callable[[], Any]) -> Any:
        profiles = deepcopy(self.vault.server_profiles)
        try:
            result = operation()
            self._save()
            return result
        except Exception:
            self.vault.server_profiles = profiles
            raise

    def _find(self, profile_id: str) -> ServerProfile:
        profile = next((item for item in self.vault.server_profiles if item.id == profile_id), None)
        if profile is None:
            raise ValueError("服务器不存在")
        return profile

    def list(self) -> list[ServerProfile]:
        return sorted(self.vault.server_profiles, key=lambda item: (item.name.casefold(), item.created_at or "", item.id))

    def get(self, profile_id: str) -> ServerProfile:
        return self._find(profile_id)

    def create(self, command: CreateServerCommand) -> ServerProfile:
        def operation() -> ServerProfile:
            now = self._now_factory()
            profile = ServerProfile(
                id=str(uuid.uuid4()),
                name=command.name,
                host=command.host,
                port=command.port,
                username=command.username,
                auth_kind=command.auth_kind,
                password=command.password,
                private_key=command.private_key,
                private_key_passphrase=command.private_key_passphrase,
                notes=command.notes,
                created_at=now,
                updated_at=now,
            )
            profile.validate()
            profile.require_credentials()
            self.vault.server_profiles.append(profile)
            return profile

        return self._transaction(operation)

    def update(self, profile_id: str, command: UpdateServerCommand) -> ServerProfile:
        def operation() -> ServerProfile:
            current = self._find(profile_id)
            requested_auth_kind = ServerAuthKind(command.auth_kind)
            credentials_changed = command.replace_credentials or requested_auth_kind != current.auth_kind
            profile = ServerProfile(
                id=current.id,
                name=command.name,
                host=command.host,
                port=command.port,
                username=command.username,
                auth_kind=requested_auth_kind,
                password=command.password if credentials_changed else current.password,
                private_key=command.private_key if credentials_changed else current.private_key,
                private_key_passphrase=(
                    command.private_key_passphrase if credentials_changed else current.private_key_passphrase
                ),
                notes=command.notes,
                trusted_host_key=(
                    None
                    if credentials_changed
                    or current.host != command.host
                    or current.port != int(command.port)
                    or current.username != command.username
                    else current.trusted_host_key
                ),
                created_at=current.created_at,
                updated_at=self._now_factory(),
            )
            profile.validate()
            profile.require_credentials()
            self.vault.server_profiles[self.vault.server_profiles.index(current)] = profile
            return profile

        return self._transaction(operation)

    def delete(self, profile_id: str) -> None:
        def operation() -> None:
            profile = self._find(profile_id)
            self.vault.server_profiles.remove(profile)

        self._transaction(operation)

    def set_trusted_host_key(self, profile_id: str, trusted_key: TrustedHostKey) -> ServerProfile:
        def operation() -> ServerProfile:
            profile = self._find(profile_id)
            trusted_key.validate()
            profile.trusted_host_key = deepcopy(trusted_key)
            profile.updated_at = self._now_factory()
            return profile

        return self._transaction(operation)

    def reset_trusted_host_key(self, profile_id: str) -> ServerProfile:
        def operation() -> ServerProfile:
            profile = self._find(profile_id)
            profile.trusted_host_key = None
            profile.updated_at = self._now_factory()
            return profile

        return self._transaction(operation)

    def import_profiles(self, profiles: Sequence[ServerProfile]) -> tuple[int, int]:
        """Merge backup profiles atomically while retaining existing credentials."""

        def operation() -> tuple[int, int]:
            original_ids = {item.id for item in self.vault.server_profiles}
            identities = {item.connection_identity for item in self.vault.server_profiles}
            added = 0
            duplicates = 0
            for imported in deepcopy(list(profiles)):
                imported.validate()
                if imported.connection_identity in identities:
                    duplicates += 1
                    continue
                if imported.id in original_ids:
                    imported.id = str(uuid.uuid4())
                imported.created_at = imported.created_at or self._now_factory()
                imported.updated_at = imported.updated_at or imported.created_at
                self.vault.server_profiles.append(imported)
                original_ids.add(imported.id)
                identities.add(imported.connection_identity)
                added += 1
            return added, duplicates

        return self._transaction(operation)
