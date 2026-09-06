import json

import pytest

from application.backup_service import BackupService
from application.import_export import BackupPasswordRequiredError
from domain.entities import OTPEntry
from infrastructure.backup_codec import BackupCodec
from infrastructure.backup_files import JsonBackupFileStore
from infrastructure.errors import VaultError
from infrastructure.vault_repository import JsonVaultRepository
from infrastructure.vault_store import Vault

SECRET = "JBSWY3DPEHPK3PXP"


class FakeProtector:
    def __init__(self, identity: bytes) -> None:
        self.identity = identity

    def protect(self, value: bytes) -> bytes:
        return self.identity + b":" + value

    def unprotect(self, value: bytes) -> bytes:
        prefix = self.identity + b":"
        if not value.startswith(prefix):
            raise VaultError("different device")
        return value.removeprefix(prefix)


def make_service(tmp_path, identity: bytes = b"device"):
    protector = FakeProtector(identity)
    repository = JsonVaultRepository(tmp_path / "vault.json", Vault, protector)
    return repository, BackupService(
        BackupCodec(protector),
        JsonBackupFileStore(),
        repository.store,
        lambda: "2026-08-29T00:00:00+00:00",
    )


def test_plain_and_encrypted_backup_service_round_trip(tmp_path):
    repository, service = make_service(tmp_path)
    vault = repository.create()
    vault.entries.append(
        OTPEntry(id="otp-1", issuer="Example", account="alice@example.com", secret=SECRET)
    )
    vault.secure_settings = {
        "api_token": "api-token-that-must-not-be-exported",
        "compact_clipboard": "private clipboard",
    }
    repository.initialize(vault, "master-password")

    plain_path = tmp_path / "backup.json"
    encrypted_path = tmp_path / "backup.authbak"
    service.export_plain(str(plain_path), vault)
    service.export_encrypted(str(encrypted_path), vault)

    plain_text = plain_path.read_text(encoding="utf-8")
    encrypted_text = encrypted_path.read_text(encoding="utf-8")
    assert SECRET in plain_text
    assert "alice@example.com" in plain_text
    assert SECRET not in encrypted_text
    for excluded in ("api-token-that-must-not-be-exported", "private clipboard"):
        assert excluded not in plain_text
        assert excluded not in encrypted_text
    assert json.loads(plain_text)["encrypted"] is False
    assert service.load(str(plain_path)).otp_entries[0].secret == SECRET
    assert service.load(str(encrypted_path)).otp_entries[0].secret == SECRET


def test_encrypted_backup_service_requests_password_only_after_device_failure(tmp_path):
    repository, service = make_service(tmp_path, b"source")
    vault = repository.create()
    vault.entries.append(OTPEntry(id="otp-1", issuer="Example", account="alice", secret=SECRET))
    repository.initialize(vault, "master-password")
    backup_path = tmp_path / "backup.authbak"
    service.export_encrypted(str(backup_path), vault)

    _moved_repository, moved_service = make_service(tmp_path / "moved", b"other")
    with pytest.raises(BackupPasswordRequiredError):
        moved_service.load(str(backup_path))
    bundle = moved_service.load(str(backup_path), "master-password")
    assert bundle.otp_entries[0].account == "alice"
