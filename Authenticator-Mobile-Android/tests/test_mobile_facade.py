from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT.parent / "Authenticator-PC-Python"
MOBILE_PYTHON = ROOT / "app" / "src" / "main" / "python"
sys.path[:0] = [str(DESKTOP), str(MOBILE_PYTHON)]

from domain.google_authenticator import parse_google_authenticator_migration
from mobile_facade import MobileFacade


class FakeKeyBridge:
    def protect(self, value: bytes) -> bytes:
        return b"mobile:" + bytes(value)

    def unprotect(self, value: bytes) -> bytes:
        data = bytes(value)
        if not data.startswith(b"mobile:"):
            raise ValueError("wrong device")
        return data[7:]


def _varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _field(number: int, value: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(value)) + value


def _migration_uri() -> str:
    account = b"".join((
        _field(1, b"synthetic-secret"),
        _field(2, b"Example:mobile@example.com"),
        _field(3, b"Example"),
        _varint(4 << 3) + _varint(1),
        _varint(5 << 3) + _varint(1),
        _varint(6 << 3) + _varint(2),
    ))
    payload = _field(1, account) + _varint(2 << 3) + _varint(1)
    return "otpauth-migration://offline?data=" + quote(base64.b64encode(payload).decode(), safe="")


def test_mobile_facade_round_trip_and_restart(tmp_path):
    facade = MobileFacade(str(tmp_path), FakeKeyBridge())
    assert json.loads(facade.startup())["status"] == "needs_setup"
    facade.initialize("master-password")
    facade.create_account(json.dumps({
        "issuer": "OpenAI",
        "account": "mobile@example.com",
        "secret": "JBSWY3DPEHPK3PXP",
    }))
    facade.create_password(json.dumps({"username": "alice", "password": "correct horse"}))
    snapshot = json.loads(facade.snapshot())
    assert snapshot["accounts"][0]["code"].isdigit()
    assert "JBSWY3DPEHPK3PXP" not in facade.snapshot()
    assert snapshot["passwords"][0]["username"] == "alice"
    assert "correct horse" not in facade.snapshot()

    restarted = MobileFacade(str(tmp_path), FakeKeyBridge())
    assert json.loads(restarted.startup())["unlocked"] is True
    assert len(json.loads(restarted.snapshot())["accounts"]) == 1

    account = snapshot["accounts"][0]
    assert json.loads(restarted.get_account(account["id"]))["secret"] == "JBSWY3DPEHPK3PXP"
    assert restarted.export_account_uri(account["id"]).startswith("otpauth://totp/")


def test_mobile_facade_returns_dynamic_otp_values_without_sensitive_material(tmp_path):
    facade = MobileFacade(str(tmp_path), FakeKeyBridge())
    facade.startup()
    facade.initialize("master-password")
    created = json.loads(facade.create_account(json.dumps({
        "issuer": "OpenAI",
        "account": "dynamic@example.com",
        "secret": "JBSWY3DPEHPK3PXP",
    })))

    dynamic = json.loads(facade.otp_dynamic_values())

    assert dynamic["locked"] is False
    assert dynamic["values"] == [{
        "id": created["id"],
        "code": dynamic["values"][0]["code"],
        "remaining": dynamic["values"][0]["remaining"],
        "error": "",
    }]
    assert dynamic["values"][0]["code"].isdigit()
    assert "JBSWY3DPEHPK3PXP" not in json.dumps(dynamic)

    facade.lock()
    assert json.loads(facade.otp_dynamic_values()) == {"locked": True, "values": []}


def test_mobile_facade_encrypted_backup_requires_source_password_on_other_device(tmp_path):
    source = MobileFacade(str(tmp_path / "source"), FakeKeyBridge())
    source.startup()
    source.initialize("master-password")
    source_group = json.loads(source.create_group("跨设备分组"))
    source.create_account(json.dumps({
        "issuer": "GitHub",
        "account": "alice@example.com",
        "secret": "JBSWY3DPEHPK3PXP",
        "group_ids": ["default", source_group["id"]],
    }))
    encrypted = source.export_backup(True)

    class OtherBridge(FakeKeyBridge):
        def unprotect(self, value: bytes) -> bytes:
            raise ValueError("different device")

    target = MobileFacade(str(tmp_path / "target"), OtherBridge())
    target.startup()
    target.initialize("target-password")
    assert json.loads(target.import_backup(encrypted))["password_required"] is True
    result = json.loads(target.import_backup(encrypted, "master-password"))
    assert result["accounts_added"] == 1
    assert result["groups_added"] == 1
    restored = json.loads(target.snapshot())
    assert any(group["id"] == source_group["id"] for group in restored["groups"])
    assert source_group["id"] in restored["accounts"][0]["group_ids"]


def test_mobile_facade_exposes_and_filters_virtual_provider_categories(tmp_path):
    facade = MobileFacade(str(tmp_path), FakeKeyBridge())
    facade.startup()
    facade.initialize("master-password")
    for issuer, account in (
        ("OpenAI", "one@example.com"),
        (" openai ", "two@example.com"),
        ("GitHub", "three@example.com"),
        ("", "four@example.com"),
        ("Provider-0", "provider-0@example.com"),
        ("Provider-1", "provider-1@example.com"),
        ("Provider-2", "provider-2@example.com"),
        ("Provider-3", "provider-3@example.com"),
        ("Provider-4", "provider-4@example.com"),
        ("Provider-5", "provider-5@example.com"),
        ("Provider-6", "provider-6@example.com"),
    ):
        facade.create_account(json.dumps({
            "issuer": issuer,
            "account": account,
            "secret": "JBSWY3DPEHPK3PXP",
        }))

    snapshot = json.loads(facade.snapshot())
    provider_counts = {item["key"]: item["count"] for item in snapshot["account_providers"]}
    assert provider_counts["openai"] == 2
    assert provider_counts["github"] == 1
    assert len(snapshot["account_providers"]) == 6
    assert snapshot["other_provider_count"] == 4
    openai = json.loads(facade.snapshot(account_provider_key="OPENAI"))
    assert [entry["account"] for entry in openai["accounts"]] == [
        "two@example.com",
        "one@example.com",
    ]
    other = json.loads(facade.snapshot(account_other_providers_only=True))
    assert len(other["accounts"]) == 4
    assert "four@example.com" in {entry["account"] for entry in other["accounts"]}


def test_mobile_facade_imports_google_authenticator_qr_atomically(tmp_path):
    facade = MobileFacade(str(tmp_path), FakeKeyBridge())
    facade.startup()
    facade.initialize("master-password")

    result = json.loads(facade.process_qr_payload(_migration_uri()))

    assert result["kind"] == "migration"
    assert result["accounts_added"] == 1
    assert json.loads(facade.snapshot())["accounts"][0]["account"] == "mobile@example.com"


def test_mobile_facade_exports_google_authenticator_qr_batches(tmp_path):
    facade = MobileFacade(str(tmp_path), FakeKeyBridge())
    facade.startup()
    facade.initialize("master-password")
    for index in range(12):
        facade.create_account(json.dumps({
            "issuer": "Example",
            "account": f"user-{index}@example.com",
            "secret": "JBSWY3DPEHPK3PXP",
        }))

    exported = json.loads(facade.export_google_authenticator())
    decoded = [parse_google_authenticator_migration(uri) for uri in exported["uris"]]

    assert exported["accounts_exported"] == 12
    assert len(exported["uris"]) == 2
    assert sum(len(batch.entries) for batch in decoded) == 12


def test_mobile_facade_applies_independent_account_and_password_sorting(tmp_path):
    facade = MobileFacade(str(tmp_path), FakeKeyBridge())
    facade.startup()
    facade.initialize("master-password")
    for issuer, account, created_at in (
        ("Zulu", "z@example.com", "2025-01-01T00:00:00Z"),
        ("Alpha", "a@example.com", "2026-01-01T00:00:00Z"),
    ):
        facade.create_account(json.dumps({
            "issuer": issuer,
            "account": account,
            "secret": "JBSWY3DPEHPK3PXP",
            "created_at": created_at,
        }))
    facade.create_password(json.dumps({"name": "Zulu", "username": "zoe", "password": "secret"}))
    facade.create_password(json.dumps({"name": "Alpha", "username": "alice", "password": "secret"}))

    snapshot = json.loads(
        facade.snapshot(
            account_sort_field="service",
            account_sort_direction="ascending",
            password_sort_field="username",
            password_sort_direction="descending",
        )
    )

    assert [entry["issuer"] for entry in snapshot["accounts"]] == ["Alpha", "Zulu"]
    assert [entry["username"] for entry in snapshot["passwords"]] == ["zoe", "alice"]


def test_mobile_facade_filters_favorites_and_hidden_pinned_independently(tmp_path):
    facade = MobileFacade(str(tmp_path), FakeKeyBridge())
    facade.startup()
    facade.initialize("master-password")
    account = json.loads(facade.create_account(json.dumps({
        "issuer": "OpenAI",
        "account": "favorite@example.com",
        "secret": "JBSWY3DPEHPK3PXP",
    })))
    password = json.loads(facade.create_password(json.dumps({
        "name": "Example",
        "username": "alice",
        "password": "secret",
    })))
    facade.set_account_favorite(json.dumps([account["id"]]), True)
    facade.set_account_pinned(json.dumps([account["id"]]), True)
    facade.set_password_favorite(json.dumps([password["id"]]), True)

    favorites = json.loads(facade.snapshot(account_favorite_only=True, password_favorite_only=True))
    assert [entry["id"] for entry in favorites["accounts"]] == [account["id"]]
    assert [entry["id"] for entry in favorites["passwords"]] == [password["id"]]
    hidden = json.loads(facade.snapshot(account_show_pinned=False))
    assert hidden["accounts"] == []


def test_mobile_facade_exposes_server_metadata_without_credentials(tmp_path):
    facade = MobileFacade(str(tmp_path), FakeKeyBridge())
    facade.startup()
    facade.initialize("master-password")

    created = json.loads(
        facade.create_server(
            json.dumps(
                {
                    "name": "Production",
                    "host": "203.0.113.8",
                    "port": 2222,
                    "username": "deploy",
                    "auth_kind": "password",
                    "password": "server-password",
                    "notes": "Primary node",
                },
            ),
        ),
    )

    snapshot = json.loads(facade.snapshot())
    assert snapshot["servers"] == [created]
    assert "server-password" not in facade.snapshot()
    connection = json.loads(facade.get_server_connection(created["id"]))
    assert connection["password"] == "server-password"

    trusted = json.loads(
        facade.trust_server_host_key(
            json.dumps(
                {
                    "profile_id": created["id"],
                    "algorithm": "ssh-ed25519",
                    "key_data": base64.b64encode(b"example-host-key").decode(),
                },
            ),
        ),
    )
    assert trusted["trusted_fingerprint"].startswith("SHA256:")
    facade.lock()
    try:
        facade.get_server_connection(created["id"])
    except ValueError as error:
        assert "解锁" in str(error)
    else:
        raise AssertionError("locked vault exposed server credentials")
