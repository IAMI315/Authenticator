"""Regression coverage for the local MUI bridge boundary."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from application.password_search_service import PasswordSearchService
from application.password_service import PasswordService
from application.search_service import SearchService
from domain.entities import OTPEntry
from domain.passwords import PasswordEntry
from infrastructure.vault_store import Vault
from presentation.mui.bridge import MuiBridge, MuiBridgeError
from presentation.view_models import MainViewModel, PasswordViewModel


def _bridge_app(tmp_path: Path) -> SimpleNamespace:
    vault = Vault(tmp_path / "vault.json")
    vault.entries.append(
        OTPEntry(id="otp-1", issuer="Example", account="alice@example.com", secret="JBSWY3DPEHPK3PXP")
    )
    vault.password_entries.append(
        PasswordEntry(id="password-1", name="Example", username="alice", password="not-for-snapshot")
    )
    password_service = PasswordService(vault, lambda: None, PasswordSearchService())
    settings = SimpleNamespace(
        autolock_minutes=0,
        compact_clipboard="small private note",
        otp_sort_field="created",
        otp_sort_direction="descending",
        password_sort_field="created",
        password_sort_direction="descending",
        otp_show_pinned=True,
        password_show_pinned=True,
        otp_codes_visible=True,
        passwords_visible=True,
    )
    return SimpleNamespace(
        vault=vault,
        main_view_model=MainViewModel(vault, SearchService(), "全部账号"),
        search_service=SearchService(),
        password_view_model=PasswordViewModel(vault, password_service),
        password_service=password_service,
        settings=settings,
        settings_repository=SimpleNamespace(save=lambda _settings: None),
        locked=False,
        _busy=False,
        _vault_loaded=True,
        window_on_top=False,
        api_endpoint="http://127.0.0.1:8765/v1",
        status_var=SimpleNamespace(get=lambda: "就绪"),
    )


def test_mui_snapshot_never_returns_otp_secret_or_password_body(tmp_path):
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = _bridge_app(tmp_path)

    otp_snapshot = bridge._snapshot(
        {"module": "otp", "query": "", "scope": "all", "showPinned": True, "sort": {}}
    )
    password_snapshot = bridge._snapshot(
        {"module": "passwords", "query": "", "scope": "all", "showPinned": True, "sort": {}}
    )

    public_text = json.dumps({"otp": otp_snapshot, "password": password_snapshot}, ensure_ascii=False)
    assert "JBSWY3DPEHPK3PXP" not in public_text
    assert "not-for-snapshot" not in public_text
    assert password_snapshot["rows"][0]["password"] == "••••••••••••"
    assert otp_snapshot["otpCodesVisible"] is True
    assert password_snapshot["passwordsVisible"] is True


def test_visible_passwords_returns_only_requested_rows_and_rejects_locked_vault(tmp_path):
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = _bridge_app(tmp_path)
    bridge.app.vault.password_entries.append(
        PasswordEntry(id="password-2", name="Other", username="bob", password="another-secret")
    )

    assert bridge._dispatch("visible_passwords", {"ids": ["password-1"]}) == {
        "passwords": {"password-1": "not-for-snapshot"}
    }
    with pytest.raises(MuiBridgeError):
        bridge._dispatch("visible_passwords", {"ids": ["password-1"] * 65})
    bridge.app.locked = True
    with pytest.raises(MuiBridgeError):
        bridge._dispatch("visible_passwords", {"ids": ["password-1"]})


def test_display_preferences_save_together_and_roll_back_on_failure(tmp_path):
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = _bridge_app(tmp_path)
    bridge.app._persist_settings = lambda: None
    payload = {"autolockMinutes": 5, "otpCodesVisible": False, "passwordsVisible": False}

    bridge._dispatch("save_settings", payload)
    assert bridge.app.settings.autolock_minutes == 5
    assert bridge.app.settings.otp_codes_visible is False
    assert bridge.app.settings.passwords_visible is False

    def fail_save() -> None:
        raise OSError("disk unavailable")

    bridge.app._persist_settings = fail_save
    with pytest.raises(OSError):
        bridge._dispatch("save_settings", {"autolockMinutes": 7, "otpCodesVisible": True, "passwordsVisible": True})
    assert bridge.app.settings.autolock_minutes == 5
    assert bridge.app.settings.otp_codes_visible is False
    assert bridge.app.settings.passwords_visible is False


def test_mui_compact_snapshot_keeps_clipboard_local_to_compact_mode(tmp_path):
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = _bridge_app(tmp_path)

    compact_snapshot = bridge._snapshot({"compact": True, "query": "alice"})
    full_snapshot = bridge._snapshot(
        {"module": "otp", "query": "", "scope": "all", "showPinned": True, "sort": {}}
    )

    assert compact_snapshot["compactClipboard"] == "small private note"
    assert [row["id"] for row in compact_snapshot["rows"]] == ["otp-1"]
    assert "compactClipboard" not in full_snapshot


def test_compact_passwords_filter_without_changing_full_view_or_exposing_secrets(tmp_path):
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = _bridge_app(tmp_path)
    bridge.app._mui_active_module = "passwords"
    bridge.app.password_view_model.query = "full-view-query"
    bridge.app.vault.password_entries.append(
        PasswordEntry(id="password-2", username="bob", password="second-private-password")
    )

    compact = bridge._snapshot({"compact": True, "query": "alice"})

    assert compact["module"] == "passwords"
    assert [row["id"] for row in compact["rows"]] == ["password-1"]
    assert compact["rows"][0]["username"] == "alice"
    assert compact["rows"][0]["password"] == "••••••••••••"
    assert compact["groups"][0]["id"] == "password-default"
    assert bridge.app.password_view_model.query == "full-view-query"
    assert "not-for-snapshot" not in json.dumps(compact)
    assert "second-private-password" not in json.dumps(compact)
    assert bridge._dynamic_snapshot({"compact": True, "module": "passwords"})["rows"] == []

    bridge.app.locked = True
    assert bridge._snapshot({"compact": True, "module": "passwords"})["rows"] == []
    assert bridge._snapshot({"compact": True, "module": "otp"})["rows"] == []


def test_two_renderers_share_module_across_mode_switches(tmp_path):
    app = _bridge_app(tmp_path)
    scheduled = []
    app.after_idle = scheduled.append
    mode_changes = []
    app.set_compact_mode = mode_changes.append
    full = MuiBridge.__new__(MuiBridge)
    compact = MuiBridge.__new__(MuiBridge)
    full.app = compact.app = app
    full.page_mode, compact.page_mode = "full", "compact"

    assert full._dispatch("active_module", {}) == {"module": "otp"}
    assert full._dispatch("compact", {"module": "passwords"}) == {}
    assert compact._dispatch("active_module", {}) == {"module": "passwords"}
    assert mode_changes == []
    scheduled.pop(0)()
    assert mode_changes == [True]
    assert compact._dispatch("set_module", {"module": "otp"}) == {"module": "otp"}
    assert compact._dispatch("return_full", {"module": "otp"}) == {}
    scheduled.pop(0)()
    assert mode_changes == [True, False]
    assert full._dispatch("active_module", {}) == {"module": "otp"}
    assert full._dispatch("set_module", {"module": "passwords"}) == {"module": "passwords"}
    assert compact._snapshot({"compact": True})["module"] == "passwords"

    with pytest.raises(MuiBridgeError):
        compact._dispatch("set_module", {"module": "servers"})
    with pytest.raises(MuiBridgeError):
        full._dispatch("compact", {"module": "servers"})
    with pytest.raises(MuiBridgeError):
        full._dispatch("set_module", {"module": "unknown"})


def test_mui_dynamic_snapshot_only_returns_timer_fields(tmp_path):
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = _bridge_app(tmp_path)
    bridge._snapshot({"module": "otp", "query": "", "scope": "all", "showPinned": True, "sort": {}})

    dynamic = bridge._dynamic_snapshot({"module": "otp", "rowIds": ["otp-1"]})

    assert dynamic["structureChanged"] is False
    assert dynamic["rows"] == [
        {
            "id": "otp-1",
            "code": dynamic["rows"][0]["code"],
            "remaining": dynamic["rows"][0]["remaining"],
            "invalid": False,
            "highlighted": False,
        }
    ]
    assert "JBSWY3DPEHPK3PXP" not in json.dumps(dynamic, ensure_ascii=False)


def test_mui_dynamic_snapshot_requests_a_structural_refresh_after_lock(tmp_path):
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = _bridge_app(tmp_path)
    bridge.app.locked = True

    dynamic = bridge._dynamic_snapshot({"module": "otp", "rowIds": ["otp-1"]})

    assert dynamic["locked"] is True
    assert dynamic["structureChanged"] is True
    assert dynamic["rows"] == []


def test_mui_mode_switches_are_silent_and_deferred_until_after_response():
    bridge = MuiBridge.__new__(MuiBridge)
    scheduled: list[object] = []
    app = SimpleNamespace(
        _busy=False,
        locked=False,
        after_idle=scheduled.append,
        set_compact_mode=lambda _enabled: None,
    )
    bridge.app = app

    assert bridge._dispatch("compact", {}) == {}
    assert bridge._dispatch("return_full", {}) == {}
    assert len(scheduled) == 2


def test_mui_account_copy_uses_full_account_value_and_feedback(tmp_path):
    bridge = MuiBridge.__new__(MuiBridge)
    app = _bridge_app(tmp_path)
    copied: list[str] = []
    statuses: list[str] = []
    app.clipboard_clear = lambda: copied.clear()
    app.clipboard_append = copied.append
    app._show_status = statuses.append
    bridge.app = app

    result = bridge._copy({"id": "otp-1"}, "account")

    assert copied == ["alice@example.com"]
    assert result["message"] == "已复制 Example 的账号。"
    assert statuses == ["已复制 Example 的账号。"]


def test_mui_loopback_server_rejects_unauthenticated_api_and_path_escape(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<main>safe</main>", encoding="utf-8")
    bridge = MuiBridge(SimpleNamespace(), static)
    try:
        with urllib.request.urlopen(f"{bridge.origin}/") as response:
            assert response.status == 200
            assert response.headers["Cache-Control"].startswith("no-store")

        with urllib.request.urlopen(f"{bridge.origin}/brand-icons/openai.png") as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/png"
            assert response.read().startswith(b"\x89PNG\r\n\x1a\n")

        request = urllib.request.Request(
            f"{bridge.origin}/api", data=b'{"action":"snapshot","payload":{}}', method="POST"
        )
        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen(request)
        assert unauthorized.value.code == 403

        with pytest.raises(urllib.error.HTTPError) as traversal:
            urllib.request.urlopen(f"{bridge.origin}/%2e%2e/secret.txt")
        assert traversal.value.code == 404
    finally:
        bridge.close()
