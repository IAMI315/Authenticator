"""Navigation scopes and dashboard statistics for both full-window modules."""

from application.password_search_service import PasswordSearchService
from application.password_service import PasswordService
from application.search_service import SearchService
from domain.entities import AccountGroup, OTPEntry
from domain.passwords import PasswordEntry, PasswordGroup
from infrastructure.vault_store import Vault
from presentation.view_models import (
    FavoriteScope,
    GroupScope,
    MainViewModel,
    OtherProvidersScope,
    PasswordViewModel,
    ProviderScope,
)

SECRET = "JBSWY3DPEHPK3PXP"


def _otp(identifier: str, issuer: str, *, otp_type: str = "totp", favorite: bool = False) -> OTPEntry:
    return OTPEntry(
        identifier,
        issuer,
        f"{identifier}@example.com",
        SECRET,
        otp_type=otp_type,
        favorite=favorite,
        created_at="2026-01-01T00:00:00Z",
    )


def test_otp_navigation_scopes_top_providers_and_other_bucket(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    vault.groups.append(AccountGroup("work", "工作"))
    providers = ("OpenAI", "Google", "Microsoft", "GitHub", "Amazon", "Discord", "Steam")
    vault.entries = [_otp(str(index), provider, favorite=index == 0) for index, provider in enumerate(providers)]
    vault.entries[1].group_ids.append("work")
    model = MainViewModel(vault, SearchService(), "全部账号")

    items = model.navigation_items(provider_limit=6)
    assert [item.id for item in items[:3]] == ["all", "favorites", "group:work"]
    assert sum(isinstance(item.scope, ProviderScope) for item in items) == 6
    other = next(item for item in items if isinstance(item.scope, OtherProvidersScope))
    assert other.count == 1

    model.set_scope(FavoriteScope())
    assert [entry.id for entry in model.visible_entries()] == ["0"]
    vault.entries[0].pinned = True
    model.set_show_pinned(False)
    assert model.visible_entries() == []
    model.set_show_pinned(True)
    model.set_scope(GroupScope("work", "工作"))
    model.query = "google"
    assert [entry.id for entry in model.visible_entries()] == ["1"]
    model.set_scope(other.scope)
    model.query = ""
    assert len(model.visible_entries()) == 1


def test_otp_dashboard_handles_invalid_hotp_and_mixed_types(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    vault.entries = [
        _otp("totp", "OpenAI"),
        _otp("hotp", "GitHub", otp_type="hotp"),
        OTPEntry("invalid", "Broken", "bad@example.com", "not-base32!", created_at="2026-01-01T00:00:00Z"),
    ]
    model = MainViewModel(vault, SearchService(), "全部账号")
    model.update_state(query="", active_group_id=None, locked=False)
    stats = model.dashboard_stats(now=29)
    assert (stats.total, stats.valid, stats.expiring) == (3, 2, 1)
    assert stats.mode_title == "2 种类型"
    model.update_state(query="", active_group_id=None, locked=True)
    assert model.dashboard_stats(now=29).locked is True


def test_password_navigation_stats_and_module_state_are_isolated(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    vault.password_groups.append(PasswordGroup("work-passwords", "工作密码"))
    vault.password_entries = [
        PasswordEntry.from_dict(
            {"id": "one", "name": "OpenAI", "username": "alice", "password": "secret", "url": "openai.com", "pinned": True, "favorite": True}
        ),
        PasswordEntry.from_dict(
            {"id": "two", "name": "GitHub", "username": "bob", "password": "secret"}
        ),
        PasswordEntry.from_dict(
            {"id": "three", "name": "", "username": "local", "password": "secret"}
        ),
    ]
    service = PasswordService(vault, lambda: None, PasswordSearchService())
    passwords = PasswordViewModel(vault, service)
    accounts = MainViewModel(vault, SearchService(), "全部账号")
    passwords.query = "alice"
    passwords.set_scope(FavoriteScope())
    accounts.query = "github"

    assert passwords.query == "alice"
    assert accounts.query == "github"
    assert [entry.id for entry in passwords.visible_entries()] == ["one"]
    passwords.set_show_pinned(False)
    assert passwords.visible_entries() == []
    passwords.set_show_pinned(True)
    assert passwords.dashboard_stats() == passwords.dashboard_stats().__class__(3, 1, 1, 1)
    other = next(item for item in passwords.navigation_items(provider_limit=1) if isinstance(item.scope, OtherProvidersScope))
    passwords.set_scope(other.scope)
    passwords.query = ""
    assert {entry.id for entry in passwords.visible_entries()} == {"one", "three"}
