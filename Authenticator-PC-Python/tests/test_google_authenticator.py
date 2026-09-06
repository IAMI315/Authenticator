from __future__ import annotations

import base64
from urllib.parse import quote

import pytest
import zxingcpp
from PIL import Image, ImageOps

from application.import_export import parse_import_text, parse_qr_content
from domain.entities import OTPEntry
from domain.google_authenticator import (
    export_google_authenticator_migration,
    parse_google_authenticator_migration,
)
from infrastructure.qr_scanner import QrCodeNotFoundError, QrScanner


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _integer(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _bytes(field: int, value: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(value)) + value


def _account(
    secret: bytes,
    name: str,
    issuer: str,
    algorithm: int,
    digits: int,
    otp_type: int,
    counter: int = 0,
) -> bytes:
    return b"".join(
        (
            _bytes(1, secret),
            _bytes(2, name.encode()),
            _bytes(3, issuer.encode()),
            _integer(4, algorithm),
            _integer(5, digits),
            _integer(6, otp_type),
            _integer(7, counter),
            _bytes(99, b"ignored"),
        )
    )


def migration_uri(*accounts: bytes, batch_size: int = 1, batch_index: int = 0) -> str:
    payload = b"".join(_bytes(1, account) for account in accounts)
    payload += _integer(2, 1) + _integer(3, batch_size) + _integer(4, batch_index) + _integer(5, 2468)
    encoded = quote(base64.b64encode(payload).decode(), safe="")
    return f"otpauth-migration://offline?data={encoded}"


def test_google_migration_decodes_accounts_and_batch_metadata() -> None:
    uri = migration_uri(
        _account(b"12345678901234567890", "Example:alice@example.com", "Example", 1, 1, 2),
        _account(b"abcdefghij", "bob@example.com", "GitHub", 2, 2, 1, 42),
        batch_size=3,
        batch_index=1,
    )

    result = parse_google_authenticator_migration(uri)

    assert result.batch_size == 3 and result.batch_index == 1 and result.batch_id == 2468
    assert len(result.entries) == 2
    assert result.entries[0].issuer == "Example"
    assert result.entries[0].account == "alice@example.com"
    assert result.entries[0].algorithm == "SHA1" and result.entries[0].digits == 6
    assert result.entries[1].otp_type == "hotp" and result.entries[1].counter == 42
    assert result.entries[1].algorithm == "SHA256" and result.entries[1].digits == 8


def test_google_migration_skips_unsupported_sibling_and_works_in_shared_import_parsers() -> None:
    valid = _account(b"synthetic-secret", "alice@example.com", "Example", 3, 1, 2)
    unsupported = _account(b"other-secret", "invalid@example.com", "Example", 4, 1, 2)
    uri = migration_uri(valid, unsupported)

    qr_payload = parse_qr_content(uri)
    text_bundle = parse_import_text(uri)

    assert qr_payload.source == "google_authenticator"
    assert len(qr_payload.bundle.otp_entries) == 1
    assert len(qr_payload.bundle.warnings) == 1
    assert len(text_bundle.otp_entries) == 1


@pytest.mark.parametrize(
    "uri",
    (
        "otpauth-migration://offline?data=",
        "otpauth-migration://offline?data=not-base64",
        "otpauth-migration://offline?data=CA==",
    ),
)
def test_google_migration_rejects_missing_or_malformed_payload(uri: str) -> None:
    with pytest.raises(ValueError):
        parse_google_authenticator_migration(uri)


def test_qr_scanner_recovers_tightly_cropped_dense_migration_code() -> None:
    accounts = tuple(
        _account(
            f"synthetic-secret-{index:02d}".encode(),
            f"Example:user-{index:02d}@example.com",
            "Example",
            1,
            1,
            2,
        )
        for index in range(12)
    )
    uri = migration_uri(*accounts)
    generated = zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, uri, 900, 900)
    image = Image.fromarray(generated)
    black_bounds = ImageOps.invert(image).getbbox()
    assert black_bounds is not None
    left, top, right, bottom = black_bounds
    tightly_cropped = image.crop((left + 2, top + 2, right - 2, bottom - 2))

    result = QrScanner(parse_qr_content).decode(tightly_cropped)

    assert result.source == "google_authenticator"
    assert len(result.bundle.otp_entries) == 12


def test_qr_scanner_captures_complete_virtual_desktop(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = object()
    calls: list[bool] = []

    def fake_grab(*, all_screens: bool) -> object:
        calls.append(all_screens)
        return captured

    monkeypatch.setattr("PIL.ImageGrab.grab", fake_grab)

    assert QrScanner.capture_screen() is captured
    assert calls == [True]


def test_qr_scanner_uses_specific_not_found_error() -> None:
    blank = Image.new("RGB", (200, 200), "white")

    with pytest.raises(QrCodeNotFoundError):
        QrScanner(parse_qr_content).decode(blank)


def test_google_export_round_trip_preserves_supported_otp_fields() -> None:
    entries = [
        OTPEntry(
            id="totp",
            issuer="Example",
            account="alice@example.com",
            secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
            digits=8,
            algorithm="SHA512",
        ),
        OTPEntry(
            id="hotp",
            issuer="GitHub",
            account="bob@example.com",
            secret="MFRGGZDFMZTWQ2LK",
            otp_type="hotp",
            counter=42,
            algorithm="SHA256",
        ),
    ]

    exported = export_google_authenticator_migration(entries, batch_id=12345)
    decoded = parse_google_authenticator_migration(exported.uris[0])

    assert exported.accounts_exported == 2 and exported.warnings == ()
    assert decoded.entries[0].account == "alice@example.com"
    assert decoded.entries[0].digits == 8 and decoded.entries[0].algorithm == "SHA512"
    assert decoded.entries[1].otp_type == "hotp" and decoded.entries[1].counter == 42
    assert decoded.entries[1].algorithm == "SHA256"


def test_google_export_batches_accounts_and_reports_unsupported_entries() -> None:
    supported = [
        OTPEntry(
            id=str(index),
            issuer="Example",
            account=f"user-{index}@example.com",
            secret="JBSWY3DPEHPK3PXP",
        )
        for index in range(12)
    ]
    unsupported = OTPEntry(
        id="steam",
        issuer="Steam",
        account="player",
        secret="JBSWY3DPEHPK3PXP",
        otp_type="steam",
    )

    exported = export_google_authenticator_migration([*supported, unsupported], batch_id=67890)
    decoded_batches = [parse_google_authenticator_migration(uri) for uri in exported.uris]

    assert exported.accounts_exported == 12
    assert len(exported.uris) == 2 and len(exported.warnings) == 1
    assert [batch.batch_index for batch in decoded_batches] == [0, 1]
    assert all(batch.batch_size == 2 and batch.batch_id == 67890 for batch in decoded_batches)
    assert sum(len(batch.entries) for batch in decoded_batches) == 12
