import json

from application.password_commands import CreatePasswordCommand
from application.password_search_service import PasswordSearchService
from application.password_service import PasswordService
from infrastructure.vault_store import VAULT_FORMAT, Vault


def test_old_vault_without_password_fields_loads_empty_password_book(tmp_path):
    path = tmp_path / "vault.json"
    path.write_text(
        json.dumps({"format": VAULT_FORMAT, "version": 1, "encrypted": False, "entries": [], "groups": []}),
        encoding="utf-8",
    )
    vault = Vault(path)
    assert vault.load() is False
    assert vault.password_entries == []
    assert [group.id for group in vault.password_groups] == ["password-default"]


def test_encrypted_vault_round_trips_and_lock_clears_passwords(tmp_path):
    path = tmp_path / "vault.json"
    vault = Vault(path)
    service = PasswordService(vault, vault.save, PasswordSearchService())
    service.create(CreatePasswordCommand("alice", "very-secret", name="Example"))
    vault.set_passphrase("master-password")

    loaded = Vault(path)
    assert loaded.load() is True
    assert loaded.password_entries == []
    loaded.unlock("master-password")
    assert loaded.password_entries[0].password == "very-secret"
    loaded.lock()
    assert loaded.password_entries == []
    assert [group.id for group in loaded.password_groups] == ["password-default"]
