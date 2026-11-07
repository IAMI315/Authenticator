"""扫码导入应用服务的事务、分组和去重测试。"""

from application.import_export import ImportBundle, QrImportPayload
from application.import_service import ImportService
from application.qr_import_service import QrImportService
from domain.entities import OTPEntry, default_account_group


def _entry(entry_id: str = "entry-1") -> OTPEntry:
    return OTPEntry(
        id=entry_id,
        issuer="Example",
        account="alice@example.com",
        secret="JBSWY3DPEHPK3PXP",
        created_at="2026-01-01T00:00:00Z",
    )


class Vault:
    def __init__(self) -> None:
        self.entries = []
        self.groups = [default_account_group()]
        self.password_entries = []
        self.password_groups = []
        self.server_profiles = []

    def merge_imported_groups(self, groups):
        return {group.id: group.id for group in groups}

    def merge_imported_password_groups(self, groups):
        return {group.id: group.id for group in groups}

    @staticmethod
    def normalise_entry_group_ids(group_ids):
        return list(group_ids)

    @staticmethod
    def normalise_password_entry_group_ids(group_ids):
        return list(group_ids)


def test_qr_import_service_uses_atomic_import_and_returns_non_sensitive_result():
    vault = Vault()
    importer = QrImportService(vault, ImportService(vault, lambda: None, lambda: "2026-01-01T00:00:00Z"))
    payload = QrImportPayload(ImportBundle(otp_entries=[_entry()]), "otpauth")

    result = importer.import_payload(payload)

    assert result.accounts_added == 1
    assert result.account_ids == ("entry-1",)
    assert result.group_ids == ("default",)
    assert vault.entries[0].secret == "JBSWY3DPEHPK3PXP"

    duplicate = importer.import_payload(payload)
    assert duplicate.accounts_added == 0
    assert duplicate.duplicates_skipped == 1


def test_qr_import_service_rejects_unknown_target_group():
    vault = Vault()
    importer = QrImportService(vault, ImportService(vault, lambda: None, lambda: "2026-01-01T00:00:00Z"))
    payload = QrImportPayload(ImportBundle(otp_entries=[_entry()]), "otpauth")

    try:
        importer.import_payload(payload, ["missing"])
    except ValueError as error:
        assert str(error) == "未知分组：missing"
    else:
        raise AssertionError("未知分组必须被拒绝")
