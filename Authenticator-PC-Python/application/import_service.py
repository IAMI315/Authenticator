"""Atomic import orchestration for OTP and password-book data."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from application.import_export import ImportBundle
from domain.entities import AccountGroup, OTPEntry
from domain.identifiers import account_identity
from domain.passwords import PasswordEntry, PasswordGroup, password_identity


@dataclass(frozen=True)
class ImportResult:
    accounts_added: int
    groups_added: int
    duplicates_skipped: int
    passwords_added: int = 0
    password_groups_added: int = 0
    password_duplicates_skipped: int = 0


class ImportService:
    def __init__(
        self,
        vault: Any,
        save: Callable[[], None],
        now_factory: Callable[[], str],
    ) -> None:
        self.vault = vault
        self._save = save
        self._now_factory = now_factory

    def import_items(
        self,
        entries: Sequence[OTPEntry],
        groups: Sequence[AccountGroup],
        password_entries: Sequence[PasswordEntry] = (),
        password_groups: Sequence[PasswordGroup] = (),
    ) -> ImportResult:
        original_entries = deepcopy(self.vault.entries)
        original_groups = deepcopy(self.vault.groups)
        original_password_entries = deepcopy(self.vault.password_entries)
        original_password_groups = deepcopy(self.vault.password_groups)
        imported_at = self._now_factory()
        existing_accounts = {account_identity(entry) for entry in self.vault.entries}
        existing_passwords = {password_identity(entry) for entry in self.vault.password_entries}
        used_account_ids = {entry.id for entry in self.vault.entries}
        used_password_ids = {entry.id for entry in self.vault.password_entries}
        account_duplicates = 0
        password_duplicates = 0
        try:
            group_mapping = self.vault.merge_imported_groups(deepcopy(list(groups)))
            password_group_mapping = self.vault.merge_imported_password_groups(
                deepcopy(list(password_groups))
            )
            accepted_accounts: list[OTPEntry] = []
            for entry in deepcopy(list(entries)):
                identity = account_identity(entry)
                if identity in existing_accounts:
                    account_duplicates += 1
                    continue
                if entry.id in used_account_ids:
                    entry.id = str(uuid.uuid4())
                if not entry.created_at:
                    entry.created_at = imported_at
                entry.group_ids = self.vault.normalise_entry_group_ids(
                    [group_mapping.get(group_id, group_id) for group_id in entry.group_ids]
                )
                entry.validate()
                accepted_accounts.append(entry)
                existing_accounts.add(identity)
                used_account_ids.add(entry.id)

            accepted_passwords: list[PasswordEntry] = []
            for password_entry in deepcopy(list(password_entries)):
                password_key = password_identity(password_entry)
                if password_key in existing_passwords:
                    password_duplicates += 1
                    continue
                if password_entry.id in used_password_ids:
                    password_entry.id = str(uuid.uuid4())
                if not password_entry.created_at:
                    password_entry.created_at = imported_at
                password_entry.group_ids = self.vault.normalise_password_entry_group_ids(
                    [
                        password_group_mapping.get(group_id, group_id)
                        for group_id in password_entry.group_ids
                    ]
                )
                password_entry.validate()
                accepted_passwords.append(password_entry)
                existing_passwords.add(password_key)
                used_password_ids.add(password_entry.id)

            groups_added = len(self.vault.groups) - len(original_groups)
            password_groups_added = len(self.vault.password_groups) - len(original_password_groups)
            self.vault.entries.extend(accepted_accounts)
            self.vault.password_entries.extend(accepted_passwords)
            if accepted_accounts or groups_added or accepted_passwords or password_groups_added:
                self._save()
            return ImportResult(
                len(accepted_accounts),
                groups_added,
                account_duplicates,
                len(accepted_passwords),
                password_groups_added,
                password_duplicates,
            )
        except Exception:
            self.vault.entries = original_entries
            self.vault.groups = original_groups
            self.vault.password_entries = original_password_entries
            self.vault.password_groups = original_password_groups
            raise

    def import_bundle(self, bundle: ImportBundle) -> ImportResult:
        return self.import_items(
            bundle.otp_entries,
            bundle.otp_groups,
            bundle.password_entries,
            bundle.password_groups,
        )
