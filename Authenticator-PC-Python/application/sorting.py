"""Typed, deterministic list sorting shared by desktop and mobile clients."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from domain.entities import OTPEntry
from domain.passwords import PasswordEntry
from domain.validators import created_at_timestamp


class SortDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


class OtpSortField(StrEnum):
    SERVICE = "service"
    ACCOUNT = "account"
    TYPE = "type"
    CREATED = "created"


class PasswordSortField(StrEnum):
    NAME = "name"
    USERNAME = "username"
    URL = "url"
    CREATED = "created"


@dataclass(frozen=True)
class OtpSortSpec:
    field: OtpSortField = OtpSortField.CREATED
    direction: SortDirection = SortDirection.DESCENDING


@dataclass(frozen=True)
class PasswordSortSpec:
    field: PasswordSortField = PasswordSortField.CREATED
    direction: SortDirection = SortDirection.DESCENDING


DEFAULT_OTP_SORT = OtpSortSpec()
DEFAULT_PASSWORD_SORT = PasswordSortSpec()
EntryT = TypeVar("EntryT", OTPEntry, PasswordEntry)


def parse_otp_sort(field: object, direction: object) -> OtpSortSpec:
    try:
        parsed_field = OtpSortField(str(field))
        parsed_direction = SortDirection(str(direction))
    except ValueError:
        return DEFAULT_OTP_SORT
    return OtpSortSpec(parsed_field, parsed_direction)


def parse_password_sort(field: object, direction: object) -> PasswordSortSpec:
    try:
        parsed_field = PasswordSortField(str(field))
        parsed_direction = SortDirection(str(direction))
    except ValueError:
        return DEFAULT_PASSWORD_SORT
    return PasswordSortSpec(parsed_field, parsed_direction)


def _text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _ordered_partition(
    items: list[EntryT], key: Callable[[EntryT], Any], descending: bool
) -> list[EntryT]:
    # Start with deterministic tie breakers. Stable sorts below retain this order.
    ordered = sorted(items, key=lambda item: str(getattr(item, "id", "")))
    ordered.sort(key=lambda item: created_at_timestamp(getattr(item, "created_at", None)), reverse=True)
    ordered.sort(key=key, reverse=descending)
    return ordered


def _text_partition(
    items: list[EntryT], key: Callable[[EntryT], str], descending: bool
) -> list[EntryT]:
    non_empty = [item for item in items if key(item)]
    empty = [item for item in items if not key(item)]
    return _ordered_partition(non_empty, key, descending) + _ordered_partition(
        empty, key, False
    )


def _with_pinned_first(
    items: list[EntryT], sorter: Callable[[list[EntryT]], list[EntryT]]
) -> list[EntryT]:
    pinned = [item for item in items if bool(getattr(item, "pinned", False))]
    regular = [item for item in items if not bool(getattr(item, "pinned", False))]
    return sorter(pinned) + sorter(regular)


def sort_otp_entries(entries: list[OTPEntry], spec: OtpSortSpec) -> list[OTPEntry]:
    descending = spec.direction is SortDirection.DESCENDING

    def sort_partition(items: list[OTPEntry]) -> list[OTPEntry]:
        if spec.field is OtpSortField.CREATED:
            return _ordered_partition(items, lambda entry: created_at_timestamp(entry.created_at), descending)
        getters = {
            OtpSortField.SERVICE: lambda entry: _text(entry.title),
            OtpSortField.ACCOUNT: lambda entry: _text(entry.account),
            OtpSortField.TYPE: lambda entry: _text(entry.type_label),
        }
        return _text_partition(items, getters[spec.field], descending)

    return _with_pinned_first(list(entries), sort_partition)


def sort_password_entries(
    entries: list[PasswordEntry], spec: PasswordSortSpec
) -> list[PasswordEntry]:
    descending = spec.direction is SortDirection.DESCENDING

    def sort_partition(items: list[PasswordEntry]) -> list[PasswordEntry]:
        if spec.field is PasswordSortField.CREATED:
            return _ordered_partition(items, lambda entry: created_at_timestamp(entry.created_at), descending)
        getters = {
            PasswordSortField.NAME: lambda entry: _text(entry.title),
            PasswordSortField.USERNAME: lambda entry: _text(entry.username),
            PasswordSortField.URL: lambda entry: _text(entry.url),
        }
        return _text_partition(items, getters[spec.field], descending)

    return _with_pinned_first(list(entries), sort_partition)
