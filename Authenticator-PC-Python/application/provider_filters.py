"""Provider-derived navigation filters shared by desktop-compatible clients."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderFilter:
    """A display-safe, virtual provider filter.

    Provider filters are derived from account metadata. They intentionally do
    not become persisted account groups or change a backup payload.
    """

    key: str
    label: str
    count: int


@dataclass(frozen=True)
class ProviderFilterCatalog:
    """The most-used providers plus the complement used by an "other" filter."""

    providers: tuple[ProviderFilter, ...]
    other_count: int
    top_keys: tuple[str, ...]


def normalise_provider_key(value: str) -> str:
    """Return the stable, case-insensitive key used for provider matching."""

    return " ".join(str(value or "").casefold().split())


def build_provider_filter_catalog(
    entries: Iterable[Any],
    label_for: Callable[[Any], str],
    *,
    limit: int = 6,
) -> ProviderFilterCatalog:
    """Build the same top-provider and "other providers" partition as the PC UI."""

    materialised = tuple(entries)
    labels: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for entry in materialised:
        label = str(label_for(entry) or "").strip()
        key = normalise_provider_key(label)
        if not key:
            continue
        counts[key] += 1
        labels.setdefault(key, label)

    top_keys = tuple(
        key
        for key, _count in sorted(
            counts.items(),
            key=lambda item: (-item[1], labels[item[0]].casefold()),
        )[: max(0, limit)]
    )
    providers = tuple(
        ProviderFilter(key=key, label=labels[key], count=counts[key])
        for key in top_keys
    )
    other_count = sum(
        1
        for entry in materialised
        if normalise_provider_key(str(label_for(entry) or "")) not in top_keys
    )
    return ProviderFilterCatalog(providers, other_count, top_keys)

