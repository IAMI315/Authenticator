"""验证 JSON 仓储、设置容错、加密保险库往返和损坏文件拒绝。"""

import json

import pytest

from domain.entities import OTPEntry, default_account_group
from infrastructure.errors import VaultError
from infrastructure.secure_storage import StorageLoadKind
from infrastructure.settings_repository import JsonSettingsRepository
from infrastructure.settings_store import SettingsStore
from infrastructure.vault_repository import JsonVaultRepository
from infrastructure.vault_store import Vault

SECRET = "JBSWY3DPEHPK3PXP"


class FakeProtector:
    def protect(self, value: bytes) -> bytes:
        return b"device:" + value

    def unprotect(self, value: bytes) -> bytes:
        if not value.startswith(b"device:"):
            raise VaultError("wrong device")
        return value.removeprefix(b"device:")


def make_entry() -> OTPEntry:
    """构造可保存到 JSON 保险库的固定账号。"""

    return OTPEntry(
        id="account-1",
        issuer="Example",
        account="alice@example.com",
        secret=SECRET,
        created_at="2025-01-01T00:00:00Z",
    )


def test_json_vault_repository_requires_encryption_and_round_trips(tmp_path):
    """仓储必须初始化主密码后保存，并可由设备凭据自动解锁。"""

    repository = JsonVaultRepository(tmp_path / "vault.json", Vault, FakeProtector())
    vault = repository.create()
    vault.entries.append(make_entry())
    with pytest.raises(VaultError):
        repository.save(vault)
    repository.initialize(vault, "correct-password")
    repository.save(vault)

    loaded = repository.create()
    assert repository.load(loaded).kind == StorageLoadKind.AUTO_UNLOCKED
    assert len(loaded.entries) == 1
    assert loaded.entries[0].account == "alice@example.com"
    assert loaded.groups[0] == default_account_group()


def test_json_settings_repository_excludes_secure_settings(tmp_path):
    """设置仓储不得把服务商、剪贴板或 API 令牌写入明文文件。"""

    repository = JsonSettingsRepository(tmp_path / "settings.json", SettingsStore)
    settings = repository.create()
    settings.last_issuer = '"xAI"'
    settings.compact_clipboard = "temporary note"
    token = settings.api_token
    repository.save(settings)
    plaintext = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "xAI" not in plaintext
    assert "temporary note" not in plaintext
    assert token not in plaintext

    loaded = repository.create()
    repository.load(loaded)
    assert loaded.last_issuer == ""
    assert loaded.compact_clipboard == ""


def test_json_settings_repository_recovers_defaults_from_corrupt_file(tmp_path):
    """损坏设置不能阻止启动，应退回默认值。"""

    path = tmp_path / "settings.json"
    path.write_text("{not-json", encoding="utf-8")
    repository = JsonSettingsRepository(path, SettingsStore)
    settings = repository.create()
    repository.load(settings)
    assert settings.window_size == "960x640"
    assert settings.always_on_top is False
    assert settings.compact_clipboard == ""


def test_json_settings_repository_round_trips_valid_sorting_and_rejects_unknown_values(tmp_path):
    path = tmp_path / "settings.json"
    repository = JsonSettingsRepository(path, SettingsStore)
    settings = repository.create()
    settings.otp_sort_field = "service"
    settings.otp_sort_direction = "ascending"
    settings.password_sort_field = "url"
    settings.password_sort_direction = "descending"
    settings.otp_show_pinned = False
    settings.password_show_pinned = True
    repository.save(settings)

    loaded = repository.create()
    repository.load(loaded)
    assert (loaded.otp_sort_field, loaded.otp_sort_direction) == ("service", "ascending")
    assert (loaded.password_sort_field, loaded.password_sort_direction) == ("url", "descending")
    assert loaded.otp_show_pinned is False
    assert loaded.password_show_pinned is True

    document = json.loads(path.read_text(encoding="utf-8"))
    document["otp_sort_field"] = "code"
    document["password_sort_direction"] = "sideways"
    path.write_text(json.dumps(document), encoding="utf-8")
    repository.load(loaded)
    assert (loaded.otp_sort_field, loaded.otp_sort_direction) == ("created", "ascending")
    assert (loaded.password_sort_field, loaded.password_sort_direction) == ("url", "descending")


def test_legacy_sensitive_settings_are_loaded_for_migration_then_scrubbed(tmp_path):
    path = tmp_path / "settings.json"
    token = "legacy-api-token-value-that-is-long-enough"
    path.write_text(
        json.dumps(
            {
                "window_size": "960x640",
                "api_token": token,
                "compact_clipboard": "legacy private note",
                "last_issuer": "Example",
            }
        ),
        encoding="utf-8",
    )
    repository = JsonSettingsRepository(path, SettingsStore)
    settings = repository.create()
    repository.load(settings)
    assert settings.secure_dirty is True
    assert settings.secure_values()["api_token"] == token
    repository.save(settings)
    plaintext = path.read_text(encoding="utf-8")
    assert token not in plaintext
    assert "legacy private note" not in plaintext
    assert "Example" not in plaintext


def test_json_vault_repository_supports_encryption_and_rejects_corrupt_documents(tmp_path):
    """加密保险库可用正确密码读回，并拒绝错误密码和错误格式文件。"""

    legacy_vault = Vault(tmp_path / "vault.json")
    legacy_vault.entries.append(make_entry())
    legacy_vault.set_passphrase("correct-password")
    repository = JsonVaultRepository(tmp_path / "vault.json", Vault, FakeProtector())

    loaded = repository.create()
    assert repository.load(loaded).kind == StorageLoadKind.NEEDS_LEGACY_PASSWORD
    with pytest.raises(VaultError):
        repository.unlock(loaded, "wrong-password")
    repository.unlock(loaded, "correct-password")
    assert loaded.entries[0].issuer == "Example"

    (tmp_path / "vault.json").write_text(json.dumps({"format": "invalid"}), encoding="utf-8")
    broken = repository.create()
    with pytest.raises(VaultError):
        repository.load(broken)
