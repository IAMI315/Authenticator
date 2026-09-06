"""Cross-platform account and password sorting rules."""

from application.sorting import (
    DEFAULT_OTP_SORT,
    OtpSortField,
    OtpSortSpec,
    PasswordSortField,
    PasswordSortSpec,
    SortDirection,
    parse_otp_sort,
    parse_password_sort,
    sort_otp_entries,
    sort_password_entries,
)
from domain.entities import OTPEntry
from domain.passwords import PasswordEntry

SECRET = "JBSWY3DPEHPK3PXP"


def _otp(
    identifier: str,
    issuer: str,
    account: str,
    created_at: str | None,
    *,
    pinned: bool = False,
    otp_type: str = "totp",
) -> OTPEntry:
    return OTPEntry(
        identifier,
        issuer,
        account,
        SECRET,
        otp_type=otp_type,
        pinned=pinned,
        created_at=created_at,
    )


def _password(
    identifier: str,
    name: str,
    username: str,
    url: str,
    created_at: str,
    *,
    pinned: bool = False,
) -> PasswordEntry:
    return PasswordEntry(
        identifier,
        username,
        "secret",
        name=name,
        url=url,
        pinned=pinned,
        created_at=created_at,
    )


def test_default_otp_sort_is_newest_first_with_pinned_partition():
    entries = [
        _otp("old", "Zulu", "old", "2025-01-01T00:00:00Z"),
        _otp("new", "Alpha", "new", "2026-01-01T00:00:00Z"),
        _otp("pin", "Pinned", "pin", "2024-01-01T00:00:00Z", pinned=True),
        _otp("legacy", "Legacy", "legacy", None),
    ]

    assert [entry.id for entry in sort_otp_entries(entries, DEFAULT_OTP_SORT)] == [
        "pin",
        "new",
        "old",
        "legacy",
    ]


def test_otp_text_and_created_sort_directions_are_deterministic():
    entries = [
        _otp("b", " beta ", "z@example.com", "2025-01-01T00:00:00Z", otp_type="hotp"),
        _otp("a", "Alpha", "a@example.com", "2026-01-01T00:00:00Z"),
        _otp("c", "alpha", "m@example.com", "2024-01-01T00:00:00Z"),
    ]

    ascending = OtpSortSpec(OtpSortField.SERVICE, SortDirection.ASCENDING)
    descending = OtpSortSpec(OtpSortField.ACCOUNT, SortDirection.DESCENDING)
    oldest = OtpSortSpec(OtpSortField.CREATED, SortDirection.ASCENDING)
    assert [entry.id for entry in sort_otp_entries(entries, ascending)] == ["a", "c", "b"]
    assert [entry.id for entry in sort_otp_entries(entries, descending)] == ["b", "c", "a"]
    assert [entry.id for entry in sort_otp_entries(entries, oldest)] == ["c", "b", "a"]


def test_password_sort_keeps_empty_optional_values_last_in_both_directions():
    entries = [
        _password("empty", "", "local", "", "2026-01-01T00:00:00Z"),
        _password("alpha", "Alpha", "alice", "https://a.example", "2025-01-01T00:00:00Z"),
        _password("zulu", "Zulu", "zoe", "https://z.example", "2024-01-01T00:00:00Z"),
    ]

    ascending = PasswordSortSpec(PasswordSortField.URL, SortDirection.ASCENDING)
    descending = PasswordSortSpec(PasswordSortField.URL, SortDirection.DESCENDING)
    assert [entry.id for entry in sort_password_entries(entries, ascending)] == ["alpha", "zulu", "empty"]
    assert [entry.id for entry in sort_password_entries(entries, descending)] == ["zulu", "alpha", "empty"]


def test_sort_parsers_reject_mixed_or_unknown_values():
    assert parse_otp_sort("service", "ascending") == OtpSortSpec(
        OtpSortField.SERVICE, SortDirection.ASCENDING
    )
    assert parse_otp_sort("unknown", "ascending") == DEFAULT_OTP_SORT
    assert parse_password_sort("name", "bad") == PasswordSortSpec()
