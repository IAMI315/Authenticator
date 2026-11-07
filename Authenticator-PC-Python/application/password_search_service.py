"""Password-book search and deterministic sorting."""

from __future__ import annotations

from collections.abc import Iterable

from application.sorting import PasswordSortSpec, sort_password_entries
from domain.passwords import PasswordEntry
from domain.validators import created_at_timestamp


def _normalise(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


class PasswordSearchService:
    def search(
        self,
        entries: Iterable[PasswordEntry],
        query: str = "",
        sort_spec: PasswordSortSpec | None = None,
    ) -> list[PasswordEntry]:
        terms = tuple(_normalise(query).split())
        matched = []
        for entry in entries:
            # A multi-word query must not repeatedly normalize potentially
            # large notes for the same record during interactive searching.
            haystack = _normalise(" ".join((entry.name, entry.username, entry.url, entry.notes)))
            if not terms or all(term in haystack for term in terms):
                matched.append(entry)
        if sort_spec is not None:
            return sort_password_entries(matched, sort_spec)
        return sorted(
            matched,
            key=lambda entry: (
                not entry.pinned,
                -created_at_timestamp(entry.created_at),
                _normalise(entry.name),
                _normalise(entry.username),
            ),
        )
