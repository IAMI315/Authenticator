"""Platform-neutral device key protection boundary."""

from __future__ import annotations

from typing import Protocol


class DeviceKeyProtector(Protocol):
    """Protect and restore a vault data key using platform credentials."""

    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...
