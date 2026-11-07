"""Server-profile privacy, transactions, backup, and MUI DTO regression tests."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from application.backup_service import BackupService
from application.import_export import parse_import_text
from application.server_commands import CreateServerCommand, UpdateServerCommand
from application.server_service import ServerService
from domain.servers import ServerProfile, TrustedHostKey
from infrastructure.backup_codec import BackupCodec
from infrastructure.backup_files import JsonBackupFileStore
from infrastructure.errors import VaultError
from infrastructure.ssh_sessions import SshSessionManager, SshTerminalSession
from infrastructure.vault_repository import JsonVaultRepository
from infrastructure.vault_store import Vault
from presentation.mui.bridge import MuiBridge


class FakeProtector:
    def __init__(self, prefix: bytes = b"device") -> None:
        self.prefix = prefix

    def protect(self, value: bytes) -> bytes:
        return self.prefix + b":" + value

    def unprotect(self, value: bytes) -> bytes:
        expected = self.prefix + b":"
        if not value.startswith(expected):
            raise VaultError("different device")
        return value.removeprefix(expected)


def make_profile(**changes: object) -> ServerProfile:
    document: dict[str, object] = {
        "id": "server-1",
        "name": "Production",
        "host": "192.0.2.10",
        "port": 22,
        "username": "deploy",
        "auth_kind": "password",
        "password": "ssh-password-secret",
        "notes": "private note",
    }
    document.update(changes)
    return ServerProfile.from_dict(document)


def test_server_profile_validates_hosts_auth_and_does_not_expose_secret_in_public_document():
    profile = make_profile()
    public = profile.to_dict(include_secrets=False)
    assert profile.credentials_configured is True
    assert "password" not in public
    assert "private_key" not in public
    with pytest.raises(ValueError, match="端口"):
        ServerProfile.from_dict({**profile.to_dict(), "port": 65536})
    with pytest.raises(ValueError, match="IP 或域名"):
        ServerProfile.from_dict({**profile.to_dict(), "host": "https://example.com"})


def test_terminal_close_releases_channel_transport_and_socket_immediately():
    class CloseSpy:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    channel, transport, client_socket = CloseSpy(), CloseSpy(), CloseSpy()
    session = SshTerminalSession(
        id="terminal-1",
        profile_id="server-1",
        profile_name="Production",
        host="192.0.2.10",
        port=22,
        username="deploy",
        state="connected",
        _channel=channel,
        _transport=transport,
        _socket=client_socket,
    )

    session.close()

    assert session.state == "closed"
    assert session._stop.is_set()
    assert [channel.close_calls, transport.close_calls, client_socket.close_calls] == [1, 1, 1]
    assert session.events.get_nowait() == {"type": "status", "status": "closed", "message": ""}


def test_terminal_event_drain_waits_without_busy_polling_and_preserves_batches():
    manager = SshSessionManager()
    session = SshTerminalSession(
        id="terminal-events",
        profile_id="server-1",
        profile_name="Production",
        host="192.0.2.10",
        port=22,
        username="deploy",
    )
    manager._sessions[session.id] = session
    assert manager.drain_events(session.id) == []

    timer = threading.Timer(0.02, lambda: (session.emit({"type": "output", "data": "first"}), session.emit({"type": "output", "data": "second"})))
    timer.start()
    started = time.monotonic()
    try:
        events = manager.drain_events(session.id, wait_seconds=1)
    finally:
        timer.cancel()

    assert time.monotonic() - started < 0.5
    assert events == [{"type": "output", "data": "first"}, {"type": "output", "data": "second"}]


def test_terminal_transport_bypasses_tk_request_queue():
    manager = SshSessionManager()
    session = SshTerminalSession(
        id="terminal-direct",
        profile_id="server-1",
        profile_name="Production",
        host="192.0.2.10",
        port=22,
        username="deploy",
    )
    manager._sessions[session.id] = session
    session.emit({"type": "output", "data": "ready"})
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = SimpleNamespace(locked=False, ssh_sessions=manager)

    result = bridge._dispatch_terminal_transport("terminal_events", {"sessionId": session.id, "waitMs": 20_000})

    assert result == {"events": [{"type": "output", "data": "ready"}]}
    assert manager.drain_events(session.id) == []


def test_server_service_rolls_back_and_clears_trust_on_connection_change(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    saves: list[bool] = []
    service = ServerService(vault, lambda: saves.append(True), now_factory=lambda: "2026-09-06T00:00:00Z")
    created = service.create(CreateServerCommand("Production", "192.0.2.10", "deploy", password="secret"))
    assert created.credentials_configured and len(saves) == 1
    service.set_trusted_host_key(created.id, TrustedHostKey("ssh-ed25519", "c2FmZS1rZXk="))
    changed = service.update(
        created.id,
        UpdateServerCommand("Production", "192.0.2.11", "deploy", password="", replace_credentials=False),
    )
    assert changed.trusted_host_key is None

    failing = ServerService(vault, lambda: (_ for _ in ()).throw(VaultError("write failed")))
    with pytest.raises(VaultError):
        failing.delete(created.id)
    assert vault.server_profiles[0].id == created.id


def test_server_profiles_are_encrypted_and_plain_backup_strips_credentials(tmp_path):
    protector = FakeProtector()
    repository = JsonVaultRepository(tmp_path / "vault.json", Vault, protector)
    vault = repository.create()
    profile = make_profile(
        auth_kind="private_key",
        password="",
        private_key="-----BEGIN OPENSSH PRIVATE KEY-----\nprivate-material\n-----END OPENSSH PRIVATE KEY-----",
        private_key_passphrase="key-passphrase",
        trusted_host_key={"algorithm": "ssh-ed25519", "key_data": "c2FmZS1rZXk="},
    )
    vault.server_profiles.append(profile)
    repository.initialize(vault, "master-password")
    backup = BackupService(BackupCodec(protector), JsonBackupFileStore(), repository.store, lambda: "2026-09-06T00:00:00Z")
    plain_path = tmp_path / "backup.json"
    encrypted_path = tmp_path / "backup.authbak"
    backup.export_plain(str(plain_path), vault)
    backup.export_encrypted(str(encrypted_path), vault)

    plain_text = plain_path.read_text(encoding="utf-8")
    encrypted_text = encrypted_path.read_text(encoding="utf-8")
    for secret in ("private-material", "key-passphrase"):
        assert secret not in plain_text
        assert secret not in encrypted_text
    plain_bundle = backup.load(str(plain_path))
    encrypted_bundle = backup.load(str(encrypted_path))
    plain_document = json.loads(plain_text)
    assert set(plain_document["server_profiles"][0]) == {"name", "host", "port", "username", "notes"}
    assert plain_bundle.server_profiles[0].credentials_configured is False
    assert encrypted_bundle.server_profiles[0].private_key == profile.private_key
    assert encrypted_bundle.server_profiles[0].trusted_host_key is not None


def test_server_import_accepts_plain_metadata_without_credentials():
    bundle = parse_import_text(
        json.dumps(
            {
                "format": "authenticator-desktop/v1",
                "server_profiles": [
                    {
                        "id": "remote-1",
                        "name": "Remote",
                        "host": "example.com",
                        "port": 22,
                        "username": "root",
                        "auth_kind": "password",
                        "notes": "metadata only",
                    }
                ],
            }
        )
    )
    assert len(bundle.server_profiles) == 1
    assert bundle.server_profiles[0].credentials_configured is False


def test_mui_server_snapshot_never_returns_password_or_private_key(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    vault.server_profiles.append(make_profile(private_key="super-private-key", private_key_passphrase="passphrase"))
    service = ServerService(vault, lambda: None)
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = SimpleNamespace(
        vault=vault,
        server_service=service,
        locked=False,
        _busy=False,
        _vault_loaded=True,
        window_on_top=False,
        settings=SimpleNamespace(autolock_minutes=0, otp_codes_visible=True, passwords_visible=True),
        status_var=SimpleNamespace(get=lambda: "就绪"),
    )
    bridge.app.ssh_sessions = SimpleNamespace(
        list_sessions=lambda: [
            SimpleNamespace(id="terminal-1", profile_id="server-1", profile_name="Production", state="connected")
        ]
    )
    payload = bridge._snapshot({"module": "servers"})
    visible = json.dumps(payload, ensure_ascii=False)
    assert "ssh-password-secret" not in visible
    assert "super-private-key" not in visible
    assert "passphrase" not in visible
    assert payload["servers"][0]["credentialsConfigured"] is True
    assert payload["terminalTabs"] == [
        {
            "id": "terminal-1",
            "profileId": "server-1",
            "name": "Production",
            "status": "connected",
        }
    ]


def test_ssh_session_manager_requires_host_key_confirmation_and_blocks_key_changes(monkeypatch):
    class FakeKey:
        def get_name(self):
            return "ssh-ed25519"

        def asbytes(self):
            return b"safe-key"

    class FakeChannel:
        closed = False
        active = False

        def get_pty(self, **_kwargs):
            return None

        def invoke_shell(self):
            return None

        def settimeout(self, _value):
            return None

        def recv_ready(self):
            return False

        def recv_stderr_ready(self):
            return False

        def exit_status_ready(self):
            return True

        def close(self):
            self.closed = True

    class FakeTransport:
        authenticated = False
        passwords: list[str] = []

        def __init__(self, _socket):
            return None

        def start_client(self, **_kwargs):
            return None

        def get_remote_server_key(self):
            return FakeKey()

        def auth_password(self, _username, password, **_kwargs):
            self.passwords.append(password)
            self.authenticated = True

        def is_authenticated(self):
            return self.authenticated

        def open_session(self, **_kwargs):
            return FakeChannel()

        def close(self):
            return None

    class FakeSocket:
        def close(self):
            return None

    monkeypatch.setitem(sys.modules, "paramiko", SimpleNamespace(Transport=FakeTransport))
    monkeypatch.setattr("infrastructure.ssh_sessions.socket.create_connection", lambda *_args, **_kwargs: FakeSocket())
    manager = SshSessionManager()
    profile = make_profile()
    session = manager.connect(profile)
    deadline = time.monotonic() + 1
    while session.state != "awaiting_host_key" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert session.pending_host_key is not None
    assert session.pending_host_key.fingerprint.startswith("SHA256:")
    first_event = session.events.get_nowait()
    awaiting_event = session.events.get_nowait()
    assert first_event["status"] == "connecting"
    assert awaiting_event["algorithm"] == "ssh-ed25519"
    manager.approve_host_key(session.id)
    deadline = time.monotonic() + 1
    while session.state != "closed" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert FakeTransport.passwords == ["ssh-password-secret"]
    assert manager.get(session.id) is session
    assert session.finished_at is not None

    profile.trusted_host_key = TrustedHostKey("ssh-ed25519", "b2xkLWtleQ==")
    changed = manager.connect(profile)
    deadline = time.monotonic() + 1
    while changed.state not in {"host_key_changed", "error"} and time.monotonic() < deadline:
        time.sleep(0.01)
    assert changed.state == "host_key_changed"


def test_ssh_session_manager_retains_fast_connection_error_for_terminal(monkeypatch):
    class FakeSocket:
        def close(self):
            return None

    class FailingTransport:
        def __init__(self, _socket):
            return None

        def start_client(self, **_kwargs):
            raise OSError("连接被目标主机拒绝")

        def close(self):
            return None

    monkeypatch.setitem(sys.modules, "paramiko", SimpleNamespace(Transport=FailingTransport))
    monkeypatch.setattr("infrastructure.ssh_sessions.socket.create_connection", lambda *_args, **_kwargs: FakeSocket())
    manager = SshSessionManager()
    session = manager.connect(make_profile())
    deadline = time.monotonic() + 1
    while session.state != "error" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert session.state == "error"
    assert manager.get(session.id) is session
    events = [session.events.get_nowait(), session.events.get_nowait()]
    assert events[0] == {"type": "status", "status": "connecting", "message": "正在连接服务器…"}
    assert events[1]["status"] == "error"
    assert "拒绝" in events[1]["message"]


def test_ssh_session_manager_supports_keyboard_interactive_password_authentication():
    """Exercise a real Paramiko handshake used by common OpenSSH password setups."""

    import paramiko

    class KeyboardInteractiveServer(paramiko.ServerInterface):
        def get_allowed_auths(self, _username):
            return "keyboard-interactive"

        def check_auth_password(self, _username, _password):
            return paramiko.AUTH_FAILED

        def check_auth_interactive(self, _username, _submethods):
            return paramiko.InteractiveQuery("Password", "", ("Password: ", False))

        def check_auth_interactive_response(self, responses):
            return paramiko.AUTH_SUCCESSFUL if responses == ["ssh-password-secret"] else paramiko.AUTH_FAILED

        def check_channel_request(self, kind, _channel_id):
            return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_pty_request(self, _channel, _term, _width, _height, _pixel_width, _pixel_height, _modes):
            return True

        def check_channel_shell_request(self, _channel):
            return True

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = int(listener.getsockname()[1])
    server_finished = threading.Event()

    def serve_once() -> None:
        client, _address = listener.accept()
        transport = paramiko.Transport(client)
        transport.add_server_key(paramiko.RSAKey.generate(1024))
        try:
            transport.start_server(server=KeyboardInteractiveServer())
            channel = transport.accept(timeout=5)
            if channel is not None:
                channel.send(b"ready\r\n")
                server_finished.wait(timeout=5)
                try:
                    channel.close()
                except EOFError:
                    # The client closing first is an expected test shutdown path.
                    pass
        finally:
            transport.close()
            listener.close()

    server_thread = threading.Thread(target=serve_once, daemon=True)
    server_thread.start()
    manager = SshSessionManager()
    profile = make_profile(host="127.0.0.1", port=port)
    session = manager.connect(profile)
    try:
        deadline = time.monotonic() + 5
        while session.state == "connecting" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert session.state == "awaiting_host_key"
        manager.approve_host_key(session.id)
        while session.state not in {"connected", "error"} and time.monotonic() < deadline:
            time.sleep(0.01)
        assert session.state == "connected"
    finally:
        manager.close(session.id)
        server_finished.set()
        server_thread.join(timeout=5)


def test_mui_terminal_bridge_replays_real_keyboard_interactive_session_statuses():
    """Verify the MUI terminal HTTP bridge receives real SSH state changes."""

    import paramiko

    class KeyboardInteractiveServer(paramiko.ServerInterface):
        def get_allowed_auths(self, _username):
            return "keyboard-interactive"

        def check_auth_password(self, _username, _password):
            return paramiko.AUTH_FAILED

        def check_auth_interactive(self, _username, _submethods):
            return paramiko.InteractiveQuery("Password", "", ("Password: ", False))

        def check_auth_interactive_response(self, responses):
            return paramiko.AUTH_SUCCESSFUL if responses == ["ssh-password-secret"] else paramiko.AUTH_FAILED

        def check_channel_request(self, kind, _channel_id):
            return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_pty_request(self, _channel, _term, _width, _height, _pixel_width, _pixel_height, _modes):
            return True

        def check_channel_shell_request(self, _channel):
            return True

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = int(listener.getsockname()[1])
    server_finished = threading.Event()

    def serve_once() -> None:
        client, _address = listener.accept()
        transport = paramiko.Transport(client)
        transport.add_server_key(paramiko.RSAKey.generate(1024))
        try:
            transport.start_server(server=KeyboardInteractiveServer())
            channel = transport.accept(timeout=5)
            if channel is not None:
                channel.send(b"ready\r\n")
                server_finished.wait(timeout=5)
                try:
                    channel.close()
                except EOFError:
                    # The client closing first is an expected test shutdown path.
                    pass
        finally:
            transport.close()
            listener.close()

    server_thread = threading.Thread(target=serve_once, daemon=True)
    server_thread.start()
    manager = SshSessionManager()
    bridge = MuiBridge.__new__(MuiBridge)
    bridge.app = SimpleNamespace(locked=False, _busy=False, ssh_sessions=manager)
    session = manager.connect(make_profile(host="127.0.0.1", port=port))
    try:
        deadline = time.monotonic() + 5
        while session.state == "connecting" and time.monotonic() < deadline:
            time.sleep(0.01)
        first_batch = bridge._terminal_events({"sessionId": session.id})["events"]
        assert [event["status"] for event in first_batch] == ["connecting", "awaiting_host_key"]
        manager.approve_host_key(session.id)
        while session.state not in {"connected", "error"} and time.monotonic() < deadline:
            time.sleep(0.01)
        second_batch = bridge._terminal_events({"sessionId": session.id})["events"]
        assert second_batch[0]["status"] == "connected"
    finally:
        manager.close(session.id)
        server_finished.set()
        server_thread.join(timeout=5)


def test_legacy_server_url_is_removed_on_the_next_encrypted_migration_write(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    vault._load_payload(
        {
            "entries": [],
            "groups": [],
            "password_entries": [],
            "password_groups": [],
            "secure_settings": {"server_url": "https://monitor.example", "api_token": "safe-token"},
        }
    )
    assert "server_url" not in vault.secure_settings
    assert vault.secure_settings["api_token"] == "safe-token"
    assert vault.migration_pending is True
