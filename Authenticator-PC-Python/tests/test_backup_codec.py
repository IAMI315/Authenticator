import json

import pytest

from application.import_export import BackupPasswordRequiredError
from infrastructure.backup_codec import BackupCodec
from infrastructure.device_key import WindowsDpapiKeyProtector
from infrastructure.errors import VaultError
from infrastructure.secure_storage import validate_master_password
from infrastructure.vault_repository import JsonVaultRepository
from infrastructure.vault_store import Vault


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


def test_encrypted_backup_is_passwordless_on_same_device_and_portable_with_master_password(tmp_path):
    source_protector = FakeProtector(b"source-device")
    repository = JsonVaultRepository(tmp_path / "vault.json", Vault, source_protector)
    vault = repository.create()
    repository.initialize(vault, "master-password")
    payload = {
        "entries": [{"id": "otp-1", "account": "alice@example.com", "secret": "TOP-SECRET"}],
        "groups": [],
        "password_entries": [],
        "password_groups": [],
    }
    codec = BackupCodec(source_protector)
    document = codec.encrypt(
        payload,
        key_id=repository.store.key_id,
        data_key=repository.store.data_key,
        password_wrap=repository.store.password_wrap,
    )
    encoded = json.dumps(document)
    assert "TOP-SECRET" not in encoded
    assert "alice@example.com" not in encoded
    assert codec.decrypt(document) == payload

    moved_codec = BackupCodec(FakeProtector(b"other-device"))
    with pytest.raises(BackupPasswordRequiredError):
        moved_codec.decrypt(document)
    assert moved_codec.decrypt(document, "master-password") == payload
    with pytest.raises(VaultError):
        moved_codec.decrypt(document, "wrong-password")


def test_encrypted_backup_rejects_tampering(tmp_path):
    protector = FakeProtector(b"device")
    repository = JsonVaultRepository(tmp_path / "vault.json", Vault, protector)
    vault = repository.create()
    repository.initialize(vault, "master-password")
    codec = BackupCodec(protector)
    document = codec.encrypt(
        {"entries": [], "password_entries": []},
        key_id=repository.store.key_id,
        data_key=repository.store.data_key,
        password_wrap=repository.store.password_wrap,
    )
    document["cipher"]["data"] = document["cipher"]["data"][:-2] + "AA"
    with pytest.raises(VaultError):
        codec.decrypt(document)


def test_master_password_requires_eight_characters():
    with pytest.raises(VaultError):
        validate_master_password("short")
    validate_master_password("12345678")


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows DPAPI only")
def test_windows_dpapi_round_trip():
    protector = WindowsDpapiKeyProtector()
    secret = b"0123456789abcdef0123456789abcdef"
    protected = protector.protect(secret)
    assert protected != secret
    assert protector.unprotect(protected) == secret
