import pytest

from application.password_commands import CreatePasswordCommand, UpdatePasswordCommand
from application.password_group_service import PasswordGroupService
from application.password_search_service import PasswordSearchService
from application.password_service import PasswordService
from domain.errors import DuplicatePasswordError
from infrastructure.vault_store import Vault


def make_service(vault, save=lambda: None):
    return PasswordService(
        vault,
        save,
        PasswordSearchService(),
        lambda: "2025-01-01T00:00:00Z",
    )


def test_password_service_crud_search_and_duplicate_rules(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    service = make_service(vault)
    first = service.create(CreatePasswordCommand("alice", "one", name="Example", url="example.com"))
    second = service.create(CreatePasswordCommand("alice", "two", name="Example", url="other.example"))
    assert [entry.id for entry in service.list("other")] == [second.id]
    with pytest.raises(DuplicatePasswordError):
        service.create(CreatePasswordCommand("alice", "different", name="Example", url="example.com"))
    updated = service.update(
        first.id,
        UpdatePasswordCommand("alice-new", "changed", name="Example", url="example.com"),
    )
    assert updated.username == "alice-new"
    assert service.set_pinned([first.id, second.id], True) == 2
    assert service.set_favorite([first.id, second.id], True) == 2
    assert all(entry.favorite for entry in vault.password_entries)
    assert service.delete([second.id]) == 1


def test_password_service_rejects_unknown_group_and_rolls_back_save_failure(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    with pytest.raises(ValueError, match="未知密码分组"):
        make_service(vault).create(CreatePasswordCommand("alice", "secret", group_ids=("missing",)))

    def fail_save():
        raise OSError("disk full")

    with pytest.raises(OSError):
        make_service(vault, fail_save).create(CreatePasswordCommand("alice", "secret"))
    assert vault.password_entries == []


def test_password_group_service_is_independent_and_transactional(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    password_service = make_service(vault)
    entry = password_service.create(CreatePasswordCommand("alice", "secret"))
    groups = PasswordGroupService(vault, lambda: None)
    group = groups.create("工作密码")
    assert groups.assign([entry.id], [group.id]) == 1
    assert entry.group_ids == ["password-default", group.id]
    second = password_service.create(CreatePasswordCommand("bob", "secret"))
    assert groups.assign_many({entry.id: [group.id], second.id: ["password-default", group.id]}) == 1
    assert second.group_ids == ["password-default", group.id]
    groups.rename(group.id, "团队密码")
    groups.delete(group.id)
    assert vault.password_entries[0].group_ids == ["password-default"]

    failing_group = PasswordGroupService(vault, lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        failing_group.create("失败分组")
    assert [candidate.name for candidate in vault.password_groups] == ["默认分组"]
