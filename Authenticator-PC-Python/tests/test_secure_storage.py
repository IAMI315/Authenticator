import json

import pytest

from domain.entities import OTPEntry
from infrastructure.errors import VaultError
from infrastructure.secure_storage import StorageLoadKind
from infrastructure.vault_repository import JsonVaultRepository
from infrastructure.vault_store import Vault

SECRET = "JBSWY3DPEHPK3PXP"


class FakeProtector:
    def __init__(self, identity: bytes = b"device-a") -> None:
        self.identity = identity

    def protect(self, value: bytes) -> bytes:
        return self.identity + b":" + value

    def unprotect(self, value: bytes) -> bytes:
        prefix = self.identity + b":"
        if not value.startswith(prefix):
            raise VaultError("different Windows user")
        return value.removeprefix(prefix)


def account() -> OTPEntry:
    return OTPEntry(id="otp-1", issuer="Example", account="alice@example.com", secret=SECRET)


def test_v2_storage_contains_no_plaintext_and_auto_unlocks(tmp_path):
    repository = JsonVaultRepository(tmp_path / "vault.json", Vault, FakeProtector())
    vault = repository.create()
    vault.entries.append(account())
    vault.secure_settings = {
        "api_token": "api-token-that-must-not-be-visible-123456",
        "compact_clipboard": "private clipboard",
        "last_issuer": "Example",
    }
    repository.initialize(vault, "master-password")

    vault_text = (tmp_path / "vault.json").read_text(encoding="utf-8")
    device_text = (tmp_path / "device.key").read_text(encoding="utf-8")
    for secret in (SECRET, "alice@example.com", "private clipboard", "api-token-that-must-not-be-visible"):
        assert secret not in vault_text
        assert secret not in device_text
    assert json.loads(vault_text)["version"] == 2
    assert json.loads(vault_text)["encrypted"] is True
    first_nonce = json.loads(vault_text)["cipher"]["nonce"]
    repository.save(vault)
    second_nonce = json.loads((tmp_path / "vault.json").read_text(encoding="utf-8"))["cipher"]["nonce"]
    assert second_nonce != first_nonce

    loaded = repository.create()
    assert repository.load(loaded).kind == StorageLoadKind.AUTO_UNLOCKED
    assert loaded.entries[0].secret == SECRET
    assert loaded.secure_settings["compact_clipboard"] == "private clipboard"
    repository.lock(loaded)
    with pytest.raises(VaultError):
        _ = repository.store.data_key
    with pytest.raises(VaultError):
        repository.unlock(loaded, "wrong-password")
    repository.unlock(loaded, "master-password")
    assert loaded.entries[0].secret == SECRET


def test_device_failure_requires_password_and_rebinds(tmp_path):
    first = JsonVaultRepository(tmp_path / "vault.json", Vault, FakeProtector(b"device-a"))
    vault = first.create()
    vault.entries.append(account())
    first.initialize(vault, "master-password")

    moved = JsonVaultRepository(tmp_path / "vault.json", Vault, FakeProtector(b"device-b"))
    loaded = moved.create()
    assert moved.load(loaded).kind == StorageLoadKind.NEEDS_PASSWORD
    with pytest.raises(VaultError):
        moved.unlock(loaded, "wrong-password")
    moved.unlock(loaded, "master-password")
    assert loaded.entries[0].account == "alice@example.com"

    reopened = JsonVaultRepository(tmp_path / "vault.json", Vault, FakeProtector(b"device-b"))
    assert reopened.load(reopened.create()).kind == StorageLoadKind.AUTO_UNLOCKED


def test_plaintext_and_legacy_encrypted_vaults_migrate_to_v2(tmp_path):
    plain_path = tmp_path / "plain" / "vault.json"
    plain = Vault(plain_path)
    plain.entries.append(account())
    plain.save()
    plain_repository = JsonVaultRepository(plain_path, Vault, FakeProtector())
    plain_loaded = plain_repository.create()
    assert plain_repository.load(plain_loaded).kind == StorageLoadKind.NEEDS_SETUP
    plain_repository.initialize(plain_loaded, "master-password")
    assert json.loads(plain_path.read_text(encoding="utf-8"))["version"] == 2

    legacy_path = tmp_path / "legacy" / "vault.json"
    legacy = Vault(legacy_path)
    legacy.entries.append(account())
    legacy.set_passphrase("legacy-password")
    legacy_repository = JsonVaultRepository(legacy_path, Vault, FakeProtector())
    legacy_loaded = legacy_repository.create()
    assert legacy_repository.load(legacy_loaded).kind == StorageLoadKind.NEEDS_LEGACY_PASSWORD
    legacy_loaded.secure_settings = {"last_issuer": "Example"}
    legacy_repository.unlock(legacy_loaded, "legacy-password")
    assert legacy_loaded.entries[0].secret == SECRET
    assert legacy_loaded.secure_settings["last_issuer"] == "Example"
    assert json.loads(legacy_path.read_text(encoding="utf-8"))["version"] == 2


def test_legacy_star_state_migrates_once_to_favorite(tmp_path):
    path = tmp_path / "vault.json"
    legacy = Vault(path)
    entry = account()
    entry.pinned = True
    legacy.entries.append(entry)
    legacy.save()
    plaintext = json.loads(path.read_text(encoding="utf-8"))
    plaintext["entries"][0].pop("favorite")
    path.write_text(json.dumps(plaintext), encoding="utf-8")

    repository = JsonVaultRepository(path, Vault, FakeProtector())
    loaded = repository.create()
    assert repository.load(loaded).kind == StorageLoadKind.NEEDS_SETUP
    assert loaded.entries[0].favorite is True
    assert loaded.entries[0].pinned is False
    repository.initialize(loaded, "master-password")

    reopened = repository.create()
    assert repository.load(reopened).kind == StorageLoadKind.AUTO_UNLOCKED
    assert reopened.entries[0].favorite is True
    assert reopened.entries[0].pinned is False


def test_change_master_password_keeps_data_key_and_rejects_old_password(tmp_path):
    repository = JsonVaultRepository(tmp_path / "vault.json", Vault, FakeProtector())
    vault = repository.create()
    vault.entries.append(account())
    repository.initialize(vault, "master-password")
    data_key = repository.store.data_key
    repository.change_master_password(vault, "master-password", "new-master-password")
    assert repository.store.data_key == data_key

    moved = JsonVaultRepository(tmp_path / "vault.json", Vault, FakeProtector(b"other"))
    locked = moved.create()
    assert moved.load(locked).kind == StorageLoadKind.NEEDS_PASSWORD
    with pytest.raises(VaultError):
        moved.unlock(locked, "master-password")
    moved.unlock(locked, "new-master-password")


def test_failed_plaintext_migration_does_not_replace_original_vault(tmp_path, monkeypatch):
    path = tmp_path / "vault.json"
    legacy = Vault(path)
    legacy.entries.append(account())
    legacy.save()
    original = path.read_bytes()
    repository = JsonVaultRepository(path, Vault, FakeProtector())
    loaded = repository.create()
    assert repository.load(loaded).kind == StorageLoadKind.NEEDS_SETUP
    original_writer = repository.store._write_document

    def fail_vault_write(target, document):
        if target == path:
            raise VaultError("disk full")
        original_writer(target, document)

    monkeypatch.setattr(repository.store, "_write_document", fail_vault_write)
    with pytest.raises(VaultError):
        repository.initialize(loaded, "master-password")
    assert path.read_bytes() == original
    assert json.loads(path.read_text(encoding="utf-8"))["encrypted"] is False
