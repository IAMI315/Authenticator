"""验证账号/分组服务的事务、去重、修改和保存失败回滚。"""

import pytest

from application.account_service import AccountService
from application.group_service import GroupService
from domain.entities import OTPEntry, default_account_group
from domain.errors import DuplicateAccountError

SECRET = "JBSWY3DPEHPK3PXP"


class FakeVault:
    """账号/分组服务使用的最小内存保险库替身。"""

    def __init__(self) -> None:
        """初始化空账号集合和不可删除的默认分组。"""

        self.entries = []
        self.groups = [default_account_group()]


def make_entry(account: str = "alice@example.com") -> OTPEntry:
    """构造有固定密钥和创建时间的有效账号实体。"""

    return OTPEntry(
        id=account,
        issuer="Example",
        account=account,
        secret=SECRET,
        created_at="2025-01-01T00:00:00Z",
    )


def test_account_service_rejects_duplicate_and_rolls_back():
    """重复创建应抛领域错误、保留已有账号且不再次保存。"""

    vault = FakeVault()
    saves = 0

    def save() -> None:
        """记录一次成功持久化调用。"""

        nonlocal saves
        saves += 1

    service = AccountService(vault, save)
    service.create(make_entry())
    with pytest.raises(DuplicateAccountError):
        service.create(make_entry())
    assert len(vault.entries) == 1
    assert saves == 1


def test_account_service_restores_state_when_save_fails():
    """新增账号后的保存失败必须使内存列表回到空状态。"""

    vault = FakeVault()

    def save() -> None:
        """模拟磁盘空间不足。"""

        raise OSError("disk full")

    service = AccountService(vault, save)
    with pytest.raises(OSError):
        service.create(make_entry())
    assert vault.entries == []


def test_account_service_rejects_unknown_group_references_without_persisting():
    """服务层必须拒绝悬空分组引用，不能仅依赖 UI/API 调用方预校验。"""

    vault = FakeVault()
    saves = []
    entry = make_entry()
    entry.group_ids = ["default", "missing-group"]

    with pytest.raises(ValueError, match="未知分组"):
        AccountService(vault, lambda: saves.append(True)).create(entry)

    assert vault.entries == []
    assert saves == []


def test_account_update_delete_and_hotp_increment_restore_when_save_fails():
    """编辑、HOTP 递增和删除在保存失败时都必须逐项恢复。"""

    vault = FakeVault()
    entry = make_entry()
    entry.otp_type = "hotp"
    vault.entries.append(entry)

    def fail_save() -> None:
        """模拟任何写入都失败的持久化回调。"""

        raise OSError("disk full")

    service = AccountService(vault, fail_save)
    updated = make_entry()
    updated.issuer = "Changed"
    updated.otp_type = "hotp"
    with pytest.raises(OSError):
        service.update(updated)
    assert vault.entries[0].issuer == "Example"

    with pytest.raises(OSError):
        service.increment_hotp(entry.id)
    assert vault.entries[0].counter == 0

    with pytest.raises(OSError):
        service.delete([entry.id])
    assert [candidate.id for candidate in vault.entries] == [entry.id]


def test_account_favorite_and_pinned_batch_updates_are_transactional():
    vault = FakeVault()
    first = make_entry("first@example.com")
    second = make_entry("second@example.com")
    vault.entries = [first, second]
    service = AccountService(vault, lambda: None)
    assert service.set_favorite([first.id, second.id], True) == 2
    assert service.set_pinned([first.id], True) == 1
    assert [entry.favorite for entry in vault.entries] == [True, True]
    assert [entry.pinned for entry in vault.entries] == [True, False]

    failing = AccountService(vault, lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        failing.set_favorite([first.id], False)
    with pytest.raises(OSError):
        failing.set_pinned([second.id], True)
    assert [entry.favorite for entry in vault.entries] == [True, True]
    assert [entry.pinned for entry in vault.entries] == [True, False]


def test_group_service_assigns_and_deletes_group():
    """分组分配后删除分组应保留账号并自动只剩默认归属。"""

    vault = FakeVault()
    persisted = []
    group_service = GroupService(vault, lambda: persisted.append(True))
    account_service = AccountService(vault, lambda: None)
    entry = account_service.create(make_entry())
    group = group_service.create("工作")
    group_service.assign([entry.id], ["default", group.id])
    assert entry.group_ids == ["default", group.id]
    group_service.delete(group.id)
    assert entry.group_ids == ["default"]
    assert len(persisted) == 3


def test_group_service_rolls_back_all_memberships_when_save_fails():
    """批量分组保存失败时，所有账号归属必须作为整体恢复。"""

    vault = FakeVault()
    account_service = AccountService(vault, lambda: None)
    first = account_service.create(make_entry("first@example.com"))
    second = account_service.create(make_entry("second@example.com"))
    group = GroupService(vault, lambda: None).create("工作")

    def fail_save() -> None:
        """模拟批量归属的最终保存失败。"""

        raise OSError("disk full")

    service = GroupService(vault, fail_save)
    before = [list(entry.group_ids) for entry in vault.entries]
    with pytest.raises(OSError):
        service.assign_many({first.id: ["default", group.id], second.id: [group.id]})
    assert [entry.group_ids for entry in vault.entries] == before


def test_group_rename_and_delete_restore_when_save_fails():
    """改名和删除在保存失败时均不能留下部分分组/归属修改。"""

    vault = FakeVault()
    group = GroupService(vault, lambda: None).create("工作")
    entry = make_entry()
    entry.group_ids.append(group.id)
    vault.entries.append(entry)

    def fail_save() -> None:
        """模拟改名和删除共享的保存失败。"""

        raise OSError("disk full")

    service = GroupService(vault, fail_save)
    with pytest.raises(OSError):
        service.rename(group.id, "新名称")
    assert vault.groups[1].name == "工作"

    with pytest.raises(OSError):
        service.delete(group.id)
    assert vault.groups[1].name == "工作"
    assert vault.entries[0].group_ids == ["default", group.id]
