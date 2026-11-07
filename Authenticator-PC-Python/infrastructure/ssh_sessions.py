"""Background Paramiko sessions with no UI, filesystem, or vault ownership."""

from __future__ import annotations

import base64
import io
import json
import queue
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from domain.servers import ServerAuthKind, ServerProfile, TrustedHostKey

MAX_SESSIONS = 8
CONNECT_TIMEOUT_SECONDS = 15
HOST_KEY_DECISION_TIMEOUT_SECONDS = 120
TERMINAL_PUMP_INTERVAL_SECONDS = 0.005
TERMINAL_EVENT_BATCH_LIMIT = 256
# A terminal tab is opened by the renderer just after ``connect`` returns.  Keep a
# completed session briefly so a fast connection failure can still be rendered.
COMPLETED_SESSION_RETENTION_SECONDS = 60
FINAL_SESSION_STATES = frozenset({"closed", "error", "host_key_changed"})


class SshSessionError(RuntimeError):
    """Safe error text suitable for the local UI."""


@dataclass
class SshTerminalSession:
    id: str
    profile_id: str
    profile_name: str
    host: str
    port: int
    username: str
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    input_events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    state: str = "connecting"
    pending_host_key: TrustedHostKey | None = None
    _host_key_decision: threading.Event = field(default_factory=threading.Event, repr=False)
    _host_key_approved: bool = False
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _socket: Any = field(default=None, repr=False)
    _transport: Any = field(default=None, repr=False)
    _channel: Any = field(default=None, repr=False)
    finished_at: float | None = field(default=None, repr=False)

    def emit(self, payload: dict[str, Any]) -> None:
        self.events.put(payload)

    def set_state(self, state: str, message: str = "", **details: str) -> None:
        self.state = state
        self.emit({"type": "status", "status": state, "message": message, **details})

    def approve_host_key(self) -> None:
        self._host_key_approved = True
        self._host_key_decision.set()

    def reject_host_key(self) -> None:
        self._host_key_approved = False
        self._host_key_decision.set()

    def close(self, *, notify: bool = True) -> None:
        """Close every transport layer without waiting for the worker thread."""

        already_stopped = self._stop.is_set()
        self._stop.set()
        self._host_key_decision.set()
        if notify and not already_stopped and self.state not in FINAL_SESSION_STATES:
            self.set_state("closed")
        # Paramiko normally closes its socket through Transport, but retaining
        # the socket separately also cancels a handshake that has not yet built
        # a complete Transport object.
        for resource in (self._channel, self._transport, self._socket):
            try:
                if resource is not None:
                    resource.close()
            except Exception:
                pass


class SshSessionManager:
    """Own live SSH session threads and expose message queues to a local terminal transport."""

    def __init__(self) -> None:
        self._sessions: dict[str, SshTerminalSession] = {}
        self._lock = threading.RLock()

    def connect(self, profile: ServerProfile, *, cols: int = 100, rows: int = 28) -> SshTerminalSession:
        profile.validate()
        profile.require_credentials()
        with self._lock:
            self._prune_completed_locked()
            active_sessions = sum(session.finished_at is None for session in self._sessions.values())
            if active_sessions >= MAX_SESSIONS:
                raise SshSessionError(f"最多可同时打开 {MAX_SESSIONS} 个 SSH 终端")
            session = SshTerminalSession(
                id=str(uuid.uuid4()),
                profile_id=profile.id,
                profile_name=profile.name,
                host=profile.host,
                port=profile.port,
                username=profile.username,
            )
            self._sessions[session.id] = session
        session.set_state("connecting", "正在连接服务器…")
        snapshot = ServerProfile.from_dict(profile.to_dict())
        threading.Thread(
            target=self._run_session,
            args=(session, snapshot, max(20, cols), max(8, rows)),
            name=f"ssh-{session.id[:8]}",
            daemon=True,
        ).start()
        return session

    def get(self, session_id: str) -> SshTerminalSession | None:
        with self._lock:
            self._prune_completed_locked()
            return self._sessions.get(session_id)

    def sessions_for_profile(self, profile_id: str) -> list[SshTerminalSession]:
        with self._lock:
            return [item for item in self._sessions.values() if item.profile_id == profile_id]

    def list_sessions(self) -> list[SshTerminalSession]:
        """Return only live sessions that can be restored after a UI refresh."""

        with self._lock:
            self._prune_completed_locked()
            return [session for session in self._sessions.values() if session.finished_at is None]

    def drain_events(
        self,
        session_id: str,
        *,
        limit: int = TERMINAL_EVENT_BATCH_LIMIT,
        wait_seconds: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Return terminal events, waiting for the first item when requested.

        This method is deliberately safe to call from the loopback transport
        thread. Terminal queues belong to the SSH worker, so output delivery
        does not need to wait for Tk's UI command queue.
        """

        session = self.get(session_id)
        if session is None:
            raise SshSessionError("终端会话已结束，请重新连接。")
        bounded_limit = max(1, min(int(limit), TERMINAL_EVENT_BATCH_LIMIT))
        timeout = max(0.0, min(float(wait_seconds), 25.0))
        events: list[dict[str, Any]] = []
        try:
            events.append(session.events.get(timeout=timeout) if timeout else session.events.get_nowait())
        except queue.Empty:
            return events
        for _index in range(bounded_limit - 1):
            try:
                events.append(session.events.get_nowait())
            except queue.Empty:
                break
        return events

    def approve_host_key(self, session_id: str) -> None:
        session = self.get(session_id)
        if session is None or session.pending_host_key is None:
            raise SshSessionError("当前终端没有等待确认的主机指纹")
        session.approve_host_key()

    def reject_host_key(self, session_id: str) -> None:
        session = self.get(session_id)
        if session is not None:
            session.reject_host_key()

    def write(self, session_id: str, data: str) -> None:
        session = self.get(session_id)
        if session is None:
            raise SshSessionError("终端会话已关闭")
        if len(data.encode("utf-8", errors="replace")) > 32_768:
            raise SshSessionError("单次终端输入过长")
        session.input_events.put({"type": "input", "data": data})

    def resize(self, session_id: str, cols: int, rows: int) -> None:
        session = self.get(session_id)
        if session is None:
            return
        session.input_events.put(
            {"type": "resize", "cols": max(20, min(int(cols), 500)), "rows": max(8, min(int(rows), 200))}
        )

    def close(self, session_id: str) -> None:
        session = self.get(session_id)
        if session is not None:
            session.close()

    def close_profile(self, profile_id: str) -> None:
        for session in self.sessions_for_profile(profile_id):
            session.close()

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.close()

    def _prune_completed_locked(self) -> None:
        expires_before = time.monotonic() - COMPLETED_SESSION_RETENTION_SECONDS
        stale_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if session.finished_at is not None and session.finished_at <= expires_before
        ]
        for session_id in stale_ids:
            self._sessions.pop(session_id, None)

    def _run_session(self, session: SshTerminalSession, profile: ServerProfile, cols: int, rows: int) -> None:
        try:
            import paramiko

            # Paramiko's tuple constructor does not give us a reliable socket
            # connect timeout.  Establish it explicitly so failure is observable.
            client_socket = socket.create_connection((profile.host, profile.port), timeout=CONNECT_TIMEOUT_SECONDS)
            session._socket = client_socket
            if session._stop.is_set():
                return
            transport = paramiko.Transport(client_socket)
            session._transport = transport
            transport.banner_timeout = CONNECT_TIMEOUT_SECONDS
            transport.auth_timeout = CONNECT_TIMEOUT_SECONDS
            transport.start_client(timeout=CONNECT_TIMEOUT_SECONDS)
            if session._stop.is_set():
                return
            remote_key = transport.get_remote_server_key()
            received = TrustedHostKey(remote_key.get_name(), base64.b64encode(remote_key.asbytes()).decode("ascii"))
            received.validate()
            if profile.trusted_host_key is None:
                session.pending_host_key = received
                session.set_state("awaiting_host_key", received.fingerprint, algorithm=received.algorithm)
                if not session._host_key_decision.wait(HOST_KEY_DECISION_TIMEOUT_SECONDS) or not session._host_key_approved:
                    raise SshSessionError("未确认服务器主机指纹")
            elif (
                profile.trusted_host_key.algorithm != received.algorithm
                or profile.trusted_host_key.key_data != received.key_data
            ):
                session.pending_host_key = received
                session.set_state("host_key_changed", received.fingerprint, algorithm=received.algorithm)
                raise SshSessionError("服务器主机指纹已变化，请重置信任记录后再连接")
            if session._stop.is_set():
                return
            if profile.auth_kind is ServerAuthKind.PASSWORD:
                # OpenSSH deployments often expose password login only through
                # keyboard-interactive.  Paramiko's fallback safely answers the
                # server password prompt with the already selected credential.
                transport.auth_password(profile.username, profile.password, fallback=True)
            else:
                transport.auth_publickey(profile.username, self._load_private_key(profile))
            if not transport.is_authenticated():
                raise SshSessionError("SSH 身份验证失败")
            channel = transport.open_session(timeout=CONNECT_TIMEOUT_SECONDS)
            session._channel = channel
            channel.get_pty(term="xterm-256color", width=cols, height=rows)
            channel.invoke_shell()
            channel.settimeout(0.1)
            session.pending_host_key = None
            session.set_state("connected")
            self._pump_terminal(session, channel)
        except SshSessionError as error:
            if not session._stop.is_set() and session.state != "host_key_changed":
                session.set_state("error", str(error))
        except Exception as error:
            if session._stop.is_set():
                return
            if isinstance(error, socket.timeout):
                message = f"连接超时（{CONNECT_TIMEOUT_SECONDS} 秒），请检查地址、端口和网络。"
            elif isinstance(error, ConnectionRefusedError):
                message = "目标主机拒绝连接，请确认 SSH 服务已启动且端口正确。"
            elif isinstance(error, socket.gaierror):
                message = "无法解析服务器地址，请检查 IP 或域名。"
            elif error.__class__.__name__ == "AuthenticationException":
                message = "SSH 身份验证失败，请检查用户名、密码或私钥。"
            elif isinstance(error, OSError):
                message = f"网络连接失败：{str(error).strip() or '无法建立 TCP 连接'}"
            else:
                message = str(error).strip() or "SSH 连接失败"
            session.set_state("error", message[:500])
        finally:
            session.close(notify=False)
            if session.state not in FINAL_SESSION_STATES:
                session.set_state("closed")
            with self._lock:
                # Let the terminal bridge drain the final status even when the
                # handshake fails before the WebSocket tab has connected.
                session.finished_at = time.monotonic()
                self._prune_completed_locked()

    @staticmethod
    def _load_private_key(profile: ServerProfile) -> Any:
        import paramiko

        source = io.StringIO(profile.private_key)
        password = profile.private_key_passphrase or None
        errors: list[Exception] = []
        for key_type in (paramiko.RSAKey, paramiko.ECDSAKey, paramiko.Ed25519Key, paramiko.DSSKey):
            source.seek(0)
            try:
                return key_type.from_private_key(source, password=password)
            except Exception as error:
                errors.append(error)
        raise SshSessionError("无法读取 SSH 私钥或私钥口令不正确") from errors[-1]

    def _pump_terminal(self, session: SshTerminalSession, channel: Any) -> None:
        while not session._stop.is_set() and not channel.closed:
            try:
                if channel.recv_ready():
                    output = channel.recv(65_536)
                    if not output:
                        break
                    session.emit({"type": "output", "data": output.decode("utf-8", errors="replace")})
                if channel.recv_stderr_ready():
                    output = channel.recv_stderr(16_384)
                    if output:
                        session.emit({"type": "output", "data": output.decode("utf-8", errors="replace")})
            except Exception:
                if session._stop.is_set():
                    break
            self._drain_input(session, channel)
            if not channel.active and channel.exit_status_ready():
                break
            # The MUI terminal consumes events through a direct loopback
            # transport. Keep the remaining Paramiko-side scheduling jitter
            # below a frame without needlessly busy-spinning idle sessions.
            time.sleep(TERMINAL_PUMP_INTERVAL_SECONDS)

    @staticmethod
    def _drain_input(session: SshTerminalSession, channel: Any) -> None:
        while True:
            try:
                event = session.input_events.get_nowait()
            except queue.Empty:
                return
            try:
                if event["type"] == "input":
                    channel.send(event["data"])
                elif event["type"] == "resize":
                    channel.resize_pty(width=event["cols"], height=event["rows"])
            except Exception:
                return

    @staticmethod
    def encode_event(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
