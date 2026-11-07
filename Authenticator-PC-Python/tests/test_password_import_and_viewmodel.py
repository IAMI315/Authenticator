import json

from application.import_export import parse_import_text
from application.import_service import ImportService
from application.password_commands import CreatePasswordCommand
from application.password_search_service import PasswordSearchService
from application.password_service import PasswordService
from domain.passwords import MASKED_PASSWORD
from infrastructure.vault_store import Vault
from presentation.view_models import PasswordViewModel


def test_mixed_backup_parses_and_imports_passwords_atomically(tmp_path):
    document = {
        "format": "authenticator-desktop/v1",
        "version": 1,
        "entries": [],
        "groups": [],
        "password_entries": [
            {"id": "pw-1", "name": "Example", "username": "alice", "password": "secret", "group_ids": ["work"]}
        ],
        "password_groups": [{"id": "work", "name": "工作密码"}],
    }
    bundle = parse_import_text(json.dumps(document))
    assert bundle.password_entries[0].username == "alice"
    vault = Vault(tmp_path / "vault.json")
    service = ImportService(vault, vault.save, lambda: "2025-01-01T00:00:00Z")
    result = service.import_bundle(bundle)
    assert result.passwords_added == 1
    assert result.password_groups_added == 1
    assert vault.password_entries[0].group_ids == ["password-default", "work"]


def test_password_only_backup_is_supported():
    bundle = parse_import_text(
        json.dumps(
            {
                "password_entries": [
                    {"id": "pw-1", "username": "alice", "password": "secret"}
                ]
            }
        )
    )
    assert [entry.username for entry in bundle.password_entries] == ["alice"]


def test_password_view_model_masks_reveals_searches_and_conceals_on_lock(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    service = PasswordService(vault, lambda: None, PasswordSearchService())
    entry = service.create(CreatePasswordCommand("alice", "secret", name="Example", notes="team login"))
    model = PasswordViewModel(vault, service)
    model.update_state(query="team", active_group_id=None, locked=False)
    assert model.visible_entries() == [entry]
    assert model.row(entry).password == MASKED_PASSWORD
    model.toggle_reveal(entry.id)
    assert model.row(entry).password == "secret"
    model.set_passwords_visible(True)
    assert model.row(entry).password == "secret"
    model.toggle_reveal(entry.id)
    assert model.row(entry).password == MASKED_PASSWORD
    model.update_state(query="", active_group_id=None, locked=True)
    assert model.revealed_entry_id is None
    assert model.visible_entries() == []
