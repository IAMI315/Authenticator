"""Google Authenticator migration QR parsing.

The export format is a URL-encoded protobuf payload.  This module implements
only the stable wire fields used by Google Authenticator and has no UI, file or
platform dependencies, so desktop and Android builds can share it.
"""

from __future__ import annotations

import base64
import binascii
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote, urlparse

from domain.entities import OTPEntry
from domain.identifiers import normalise_issuer_name
from domain.validators import utc_now_iso

MAX_MIGRATION_PAYLOAD_BYTES = 1_048_576
MAX_MIGRATION_ACCOUNTS = 1_000
MAX_GOOGLE_ACCOUNTS_PER_QR = 10
MAX_GOOGLE_MIGRATION_URI_CHARS = 2_200

_ALGORITHMS = {0: "SHA1", 1: "SHA1", 2: "SHA256", 3: "SHA512"}
_DIGITS = {0: 6, 1: 6, 2: 8}
_OTP_TYPES = {1: "hotp", 2: "totp"}


@dataclass(frozen=True)
class GoogleAuthenticatorMigration:
    """Accounts and batch metadata decoded from one migration QR code."""

    entries: tuple[OTPEntry, ...]
    version: int = 1
    batch_size: int = 1
    batch_index: int = 0
    batch_id: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GoogleAuthenticatorExport:
    """Google-compatible migration QR payloads and skipped-account warnings."""

    uris: tuple[str, ...]
    accounts_exported: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


def is_google_authenticator_migration_uri(value: str) -> bool:
    """Return whether *value* uses Google Authenticator's migration scheme."""

    parsed = urlparse(str(value or "").strip())
    return parsed.scheme.casefold() == "otpauth-migration" and parsed.netloc.casefold() == "offline"


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("Google 身份验证器迁移数据不完整")
        current = data[offset]
        offset += 1
        value |= (current & 0x7F) << shift
        if not current & 0x80:
            return value, offset
    raise ValueError("Google 身份验证器迁移数据包含无效整数")


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("Google 身份验证器迁移字段不能为负数")
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _integer_field(field_number: int, value: int) -> bytes:
    return _encode_varint(field_number << 3) + _encode_varint(value)


def _bytes_field(field_number: int, value: bytes) -> bytes:
    return _encode_varint((field_number << 3) | 2) + _encode_varint(len(value)) + value


def _protobuf_fields(data: bytes) -> list[tuple[int, int, int | bytes]]:
    fields: list[tuple[int, int, int | bytes]] = []
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if field_number == 0:
            raise ValueError("Google 身份验证器迁移数据包含无效字段")
        if wire_type == 0:
            integer, offset = _read_varint(data, offset)
            field_value: int | bytes = integer
        elif wire_type == 1:
            end = offset + 8
            if end > len(data):
                raise ValueError("Google 身份验证器迁移数据不完整")
            field_value, offset = data[offset:end], end
        elif wire_type == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if length > MAX_MIGRATION_PAYLOAD_BYTES or end > len(data):
                raise ValueError("Google 身份验证器迁移数据长度无效")
            field_value, offset = data[offset:end], end
        elif wire_type == 5:
            end = offset + 4
            if end > len(data):
                raise ValueError("Google 身份验证器迁移数据不完整")
            field_value, offset = data[offset:end], end
        else:
            raise ValueError("Google 身份验证器迁移数据使用了不支持的字段类型")
        fields.append((field_number, wire_type, field_value))
    return fields


def _text(value: bytes, field_name: str) -> str:
    try:
        return value.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise ValueError(f"Google 身份验证器账号的{field_name}不是有效文本") from error


def _split_label(name: str, issuer: str) -> tuple[str, str]:
    issuer = normalise_issuer_name(issuer)
    account = name.strip()
    if ":" not in account:
        return issuer, account
    label_issuer, label_account = account.split(":", 1)
    label_issuer = normalise_issuer_name(label_issuer)
    if not issuer:
        return label_issuer, label_account.strip()
    if label_issuer.casefold() == issuer.casefold():
        return issuer, label_account.strip()
    return issuer, account


def _parse_account(data: bytes) -> OTPEntry:
    secret = b""
    name = ""
    issuer = ""
    algorithm = 0
    digits = 0
    otp_type = 0
    counter = 0
    for field_number, wire_type, value in _protobuf_fields(data):
        if field_number == 1 and wire_type == 2:
            secret = bytes(value)
        elif field_number == 2 and wire_type == 2:
            name = _text(bytes(value), "名称")
        elif field_number == 3 and wire_type == 2:
            issuer = _text(bytes(value), "服务商")
        elif field_number == 4 and wire_type == 0:
            algorithm = int(value)
        elif field_number == 5 and wire_type == 0:
            digits = int(value)
        elif field_number == 6 and wire_type == 0:
            otp_type = int(value)
        elif field_number == 7 and wire_type == 0:
            counter = int(value)

    if not secret:
        raise ValueError("账号缺少密钥")
    if algorithm not in _ALGORITHMS:
        raise ValueError("账号使用了不支持的摘要算法")
    if digits not in _DIGITS:
        raise ValueError("账号使用了不支持的验证码位数")
    if otp_type not in _OTP_TYPES:
        raise ValueError("账号使用了不支持的验证码类型")
    issuer, account = _split_label(name, issuer)
    entry = OTPEntry(
        id=str(uuid.uuid4()),
        issuer=issuer,
        account=account,
        secret=base64.b32encode(secret).decode("ascii").rstrip("="),
        otp_type=_OTP_TYPES[otp_type],
        counter=counter,
        period=30,
        digits=_DIGITS[digits],
        algorithm=_ALGORITHMS[algorithm],
        secret_encoding="base32",
        created_at=utc_now_iso(),
    )
    entry.validate()
    return entry


def _encode_account(entry: OTPEntry) -> bytes:
    type_value = {"hotp": 1, "totp": 2}.get(entry.otp_type)
    algorithm_value = {"SHA1": 1, "SHA256": 2, "SHA512": 3}.get(entry.algorithm)
    digits_value = {6: 1, 8: 2}.get(entry.digits)
    if type_value is None:
        raise ValueError("Google 仅支持 TOTP 和 HOTP")
    if algorithm_value is None:
        raise ValueError("Google 不支持此摘要算法")
    if digits_value is None:
        raise ValueError("Google 仅支持 6 位或 8 位验证码")
    issuer = normalise_issuer_name(entry.issuer)
    account = str(entry.account or "").strip()
    label = f"{issuer}:{account}" if issuer and account else issuer or account
    fields = [
        _bytes_field(1, entry.secret_bytes()),
        _bytes_field(2, label.encode("utf-8")),
    ]
    if issuer:
        fields.append(_bytes_field(3, issuer.encode("utf-8")))
    fields.extend(
        (
            _integer_field(4, algorithm_value),
            _integer_field(5, digits_value),
            _integer_field(6, type_value),
        )
    )
    if entry.otp_type == "hotp":
        fields.append(_integer_field(7, entry.counter))
    return b"".join(fields)


def _migration_uri(
    accounts: Sequence[bytes],
    batch_size: int,
    batch_index: int,
    batch_id: int,
) -> str:
    payload = b"".join(_bytes_field(1, account) for account in accounts)
    payload += b"".join(
        (
            _integer_field(2, 1),
            _integer_field(3, batch_size),
            _integer_field(4, batch_index),
            _integer_field(5, batch_id),
        )
    )
    encoded = quote(base64.b64encode(payload).decode("ascii"), safe="")
    return f"otpauth-migration://offline?data={encoded}"


def export_google_authenticator_migration(
    entries: Sequence[OTPEntry],
    *,
    batch_id: int | None = None,
) -> GoogleAuthenticatorExport:
    """Encode compatible accounts as one or more Google migration QR payloads."""

    encoded_accounts: list[bytes] = []
    warnings: list[str] = []
    for position, entry in enumerate(entries, start=1):
        try:
            encoded_accounts.append(_encode_account(entry))
        except (UnicodeEncodeError, ValueError) as error:
            label = entry.title
            if entry.account.strip():
                label += f" · {entry.account.strip()}"
            warnings.append(f"第 {position} 个账号（{label}）已跳过：{error}")
    if not encoded_accounts:
        raise ValueError("没有 Google Authenticator 可以导入的兼容账号")

    export_batch_id = batch_id if batch_id is not None else secrets.randbelow(2**31 - 1) + 1
    if export_batch_id < 0 or export_batch_id >= 2**31:
        raise ValueError("Google 身份验证器批次标识无效")

    chunks: list[list[bytes]] = []
    current: list[bytes] = []
    for account in encoded_accounts:
        candidate = [*current, account]
        candidate_uri = _migration_uri(candidate, 1, 0, export_batch_id)
        if current and (
            len(candidate) > MAX_GOOGLE_ACCOUNTS_PER_QR
            or len(candidate_uri) > MAX_GOOGLE_MIGRATION_URI_CHARS
        ):
            chunks.append(current)
            current = [account]
        else:
            current = candidate
    if current:
        chunks.append(current)

    batch_size = len(chunks)
    uris = tuple(
        _migration_uri(chunk, batch_size, batch_index, export_batch_id)
        for batch_index, chunk in enumerate(chunks)
    )
    if any(len(uri) > MAX_GOOGLE_MIGRATION_URI_CHARS for uri in uris):
        raise ValueError("单个账号数据过长，无法生成可靠的 Google 导入二维码")
    return GoogleAuthenticatorExport(tuple(uris), len(encoded_accounts), tuple(warnings))


def parse_google_authenticator_migration(uri: str) -> GoogleAuthenticatorMigration:
    """Decode one ``otpauth-migration://offline`` QR payload.

    Unsupported accounts are reported as warnings while valid siblings remain
    importable. Malformed envelopes fail before any account reaches storage.
    """

    parsed = urlparse(uri.strip())
    if parsed.scheme.casefold() != "otpauth-migration" or parsed.netloc.casefold() != "offline":
        raise ValueError("内容不是有效的 Google 身份验证器迁移二维码")
    encoded = parse_qs(parsed.query, keep_blank_values=True).get("data", [""])[0].replace(" ", "+")
    if not encoded:
        raise ValueError("Google 身份验证器迁移二维码缺少数据")
    if len(encoded) > MAX_MIGRATION_PAYLOAD_BYTES * 2:
        raise ValueError("Google 身份验证器迁移二维码数据过大")
    try:
        payload = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Google 身份验证器迁移二维码数据损坏") from error
    if not payload or len(payload) > MAX_MIGRATION_PAYLOAD_BYTES:
        raise ValueError("Google 身份验证器迁移二维码数据长度无效")

    raw_accounts: list[bytes] = []
    metadata = {2: 1, 3: 1, 4: 0, 5: 0}
    for field_number, wire_type, value in _protobuf_fields(payload):
        if field_number == 1 and wire_type == 2:
            raw_accounts.append(bytes(value))
        elif field_number in metadata and wire_type == 0:
            metadata[field_number] = int(value)
    if not raw_accounts:
        raise ValueError("Google 身份验证器迁移二维码中没有账号")
    if len(raw_accounts) > MAX_MIGRATION_ACCOUNTS:
        raise ValueError("Google 身份验证器迁移二维码中的账号数量过多")

    entries: list[OTPEntry] = []
    warnings: list[str] = []
    for position, raw_account in enumerate(raw_accounts, start=1):
        try:
            entries.append(_parse_account(raw_account))
        except ValueError as error:
            warnings.append(f"第 {position} 个账号未能导入：{error}")
    if not entries:
        raise ValueError("Google 身份验证器迁移二维码中没有可导入账号")

    batch_size = max(1, metadata[3])
    batch_index = metadata[4]
    if batch_index < 0 or batch_index >= batch_size:
        raise ValueError("Google 身份验证器迁移二维码批次信息无效")
    return GoogleAuthenticatorMigration(
        entries=tuple(entries),
        version=metadata[2],
        batch_size=batch_size,
        batch_index=batch_index,
        batch_id=metadata[5],
        warnings=tuple(warnings),
    )
