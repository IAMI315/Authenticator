"""Typed commands for SSH server profile writes."""

from __future__ import annotations

from dataclasses import dataclass

from domain.servers import ServerAuthKind


@dataclass(frozen=True)
class CreateServerCommand:
    name: str
    host: str
    username: str
    port: int = 22
    auth_kind: ServerAuthKind = ServerAuthKind.PASSWORD
    password: str = ""
    private_key: str = ""
    private_key_passphrase: str = ""
    notes: str = ""


@dataclass(frozen=True)
class UpdateServerCommand(CreateServerCommand):
    replace_credentials: bool = False
