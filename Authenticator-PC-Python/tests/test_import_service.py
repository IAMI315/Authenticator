"""验证混合账号/分组导入的映射、ID 冲突、去重和整体回滚。"""

import pytest

from application.import_service import ImportService
from domain.entities import AccountGroup, OTPEntry, default_account_group
from infrastructure.vault_store import Vault

SECRET = "JBSWY3DPEHPK3PXP"


def make_entry(entry_id: str, account: str, group_ids: list[str] | None = None) -> OTPEntry:
    """构造可按测试场景指定 ID、账号和分组归属的领域实体。"""

    return OTPEntry(
        id=entry_id,
        issuer="Example",
        account=account,
        secret=SECRET,
        group_ids=group_ids or ["default"],
    )


def test_import_service_maps_groups_skips_duplicates_and_resolves_id_conflicts(tmp_path):
    """导入应复用/新增分组、跳过重复账号并为 ID 冲突生成新 ID。"""

    vault = Vault(tmp_path / "vault.json")
    existing = make_entry("shared-id", "existing@example.com")
    vault.entries.append(existing)
    saves = []
    service = ImportService(vault, lambda: saves.append(True), lambda: "2025-01-01T00:00:00Z")
    result = service.import_items(
        [
            make_entry("duplicate-id", "existing@example.com"),
            make_entry("shared-id", "new@example.com", ["imported-work"]),
        ],
        [AccountGroup("imported-work", "工作")],
    )

    assert result.accounts_added == 1
    assert result.groups_added == 1
    assert result.duplicates_skipped == 1
    assert vault.entries[1].id != "shared-id"
    assert vault.entries[1].created_at == "2025-01-01T00:00:00Z"
    assert vault.entries[1].group_ids == ["default", "imported-work"]
    assert len(saves) == 1


def test_import_service_restores_accounts_and_groups_when_save_fails(tmp_path):
    """导入保存失败时账号和分组都必须回到导入前快照。"""

    vault = Vault(tmp_path / "vault.json")
    original = make_entry("existing", "existing@example.com")
    vault.entries.append(original)

    def fail_save() -> None:
        """模拟磁盘写入失败。"""

        raise OSError("disk full")

    service = ImportService(vault, fail_save, lambda: "2025-01-01T00:00:00Z")
    with pytest.raises(OSError):
        service.import_items(
            [make_entry("new", "new@example.com", ["work"])],
            [AccountGroup("work", "工作")],
        )

    assert [entry.id for entry in vault.entries] == ["existing"]
    assert vault.groups == [default_account_group()]
