"""Known service metadata used by desktop provider navigation.

The vault deliberately stores only user-owned account fields.  Provider names
in the sidebar are virtual groupings, so their public website and logo metadata
lives in this curated catalog instead of being duplicated beside every account.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceMetadata:
    """Public, non-sensitive information for a recognised service provider."""

    key: str
    official_url: str
    favicon_url: str
    local_icon_name: str
    aliases: tuple[str, ...]


_SERVICES: tuple[ServiceMetadata, ...] = (
    ServiceMetadata(
        "openai", "https://openai.com", "https://openai.com/favicon.ico", "openai",
        ("openai", "chatgpt", "chat gpt"),
    ),
    ServiceMetadata("xai", "https://x.ai", "https://x.ai/favicon.ico", "xai", ("xai", "x.ai")),
    ServiceMetadata(
        "google", "https://www.google.com", "https://www.google.com/favicon.ico", "google",
        ("google", "gmail"),
    ),
    ServiceMetadata(
        "microsoft", "https://www.microsoft.com", "https://www.microsoft.com/favicon.ico", "microsoft",
        ("microsoft", "office", "m365"),
    ),
    ServiceMetadata(
        "microsoftoutlook", "https://outlook.live.com", "https://outlook.live.com/favicon.ico", "microsoftoutlook",
        ("outlook",),
    ),
    ServiceMetadata("github", "https://github.com", "https://github.com/favicon.ico", "github", ("github",)),
    ServiceMetadata("amazon", "https://www.amazon.com", "https://www.amazon.com/favicon.ico", "amazon", ("amazon", "aws")),
    ServiceMetadata("discord", "https://discord.com", "https://discord.com/favicon.ico", "discord", ("discord",)),
    ServiceMetadata("steam", "https://store.steampowered.com", "https://store.steampowered.com/favicon.ico", "steam", ("steam",)),
    ServiceMetadata(
        "battledotnet", "https://battle.net", "https://battle.net/favicon.ico", "battledotnet",
        ("battle.net", "battlenet"),
    ),
)

_BY_KEY = {service.key: service for service in _SERVICES}


def normalise_service_name(value: str) -> str:
    """Return a stable label form shared by service lookups and aliases."""

    return " ".join(str(value or "").casefold().split())


def service_metadata_for(value: str) -> ServiceMetadata | None:
    """Resolve a displayed provider name to its explicit public metadata."""

    name = normalise_service_name(value)
    if not name:
        return None
    for service in _SERVICES:
        if any(alias == name or alias in name for alias in service.aliases):
            return service
    return None


def service_metadata_by_key(key: str) -> ServiceMetadata | None:
    """Return a catalog item only for a curated canonical key."""

    return _BY_KEY.get(str(key or "").casefold())
