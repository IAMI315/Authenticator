"""Loopback-only bridge between the local MUI page and desktop services.

The browser process never receives a filesystem path, vault payload, API token or
long-lived credential.  Every request is authenticated with an in-memory URL
fragment token and dispatched onto the Tk main thread before touching the app.
"""

from __future__ import annotations

import json
import queue
import re
import secrets
import threading
import time
import uuid
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from application.password_commands import CreatePasswordCommand, UpdatePasswordCommand
from application.server_commands import CreateServerCommand, UpdateServerCommand
from application.sorting import (
    OtpSortField,
    OtpSortSpec,
    PasswordSortField,
    PasswordSortSpec,
    SortDirection,
)
from domain.entities import OTPEntry
from domain.passwords import PasswordGeneratorOptions, generate_password
from domain.servers import ServerAuthKind
from domain.validators import format_created_at, integer_value, utc_now_iso
from infrastructure.brand_icon_cache import BrandIconCache, image_content_type
from infrastructure.paths import resource_path
from infrastructure.secure_storage import StorageLoadKind
from infrastructure.service_catalog import service_metadata_by_key
from infrastructure.ssh_sessions import SshSessionError
from presentation.qr_scan_flow import QrScanFlow
from presentation.view_models import NavigationItem

ModuleName = Literal["otp", "passwords", "servers"]
PageMode = Literal["full", "compact"]


class MuiBridgeError(RuntimeError):
    """A user-facing bridge request error that is safe to return to the UI."""


@dataclass
class _UiRequest:
    action: str
    payload: dict[str, Any]
    completed: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Exception | None = None


class MuiBridge:
    """Serve bundled assets and marshal MUI commands into the Tk main thread."""

    _TERMINAL_TRANSPORT_ACTIONS = frozenset(
        {"terminal_events", "terminal_input", "terminal_resize", "terminal_disconnect"}
    )
    _TERMINAL_LONG_POLL_MAX_SECONDS = 20.0

    def __init__(
        self,
        app: Any,
        static_directory: Path,
        *,
        page_mode: PageMode = "full",
        brand_icon_directory: Path | None = None,
    ) -> None:
        self.app = app
        self.static_directory = static_directory.resolve()
        self.page_mode = page_mode
        self.token = secrets.token_urlsafe(32)
        self._requests: queue.Queue[_UiRequest] = queue.Queue()
        self._server = self._create_server()
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.05),
            name="mui-loopback",
            daemon=True,
        )
        self._thread.start()
        self._closed = False
        self._scan_flows: dict[bool, QrScanFlow] = {}
        self._private_key_imports: dict[str, tuple[str, str]] = {}
        self._brand_icon_cache = BrandIconCache(brand_icon_directory) if brand_icon_directory is not None else None

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def page_url(self) -> str:
        return f"{self.origin}/?mode={self.page_mode}#{self.token}"

    def _create_server(self) -> ThreadingHTTPServer:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AuthenticatorMui/1"

            def log_message(self, _format: str, *_args: object) -> None:
                # Browser paths and UI queries do not belong in application logs.
                return

            def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
                bridge._handle_static(self)

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
                bridge._handle_api(self)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        # Long-poll terminal readers must never delay renderer shutdown.
        server.daemon_threads = True
        return server

    @staticmethod
    def _response(handler: BaseHTTPRequestHandler, status: HTTPStatus, body: bytes, content_type: str) -> None:
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self' ws://127.0.0.1:*; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; font-src 'self' data:; script-src 'self'; "
            "object-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_static(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(handler.path)
        if parsed.path.startswith("/brand-icons/"):
            self._handle_brand_icon(handler, parsed.path)
            return
        request_path = parsed.path or "/"
        relative = "index.html" if request_path == "/" else request_path.lstrip("/")
        candidate = (self.static_directory / relative).resolve()
        try:
            candidate.relative_to(self.static_directory)
        except ValueError:
            self._response(handler, HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
            return
        if not candidate.is_file():
            # Vite has no server-side routes; unknown paths must not disclose paths.
            self._response(handler, HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
            return
        types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".woff2": "font/woff2",
        }
        try:
            self._response(handler, HTTPStatus.OK, candidate.read_bytes(), types.get(candidate.suffix, "application/octet-stream"))
        except OSError:
            self._response(handler, HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")

    def _handle_brand_icon(self, handler: BaseHTTPRequestHandler, request_path: str) -> None:
        """Serve a packaged mark now and refresh its official favicon safely."""

        key = request_path.removeprefix("/brand-icons/").removesuffix(".png")
        if not re.fullmatch(r"[a-z0-9-]{1,64}", key):
            self._response(handler, HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
            return
        service = service_metadata_by_key(key)
        if service is None:
            self._response(handler, HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
            return
        if self._brand_icon_cache is not None:
            cached = self._brand_icon_cache.cached(service)
            self._brand_icon_cache.refresh_in_background(service)
            if cached is not None:
                self._response(handler, HTTPStatus.OK, cached, image_content_type(cached))
                return
        source_path = resource_path(f"assets/icons/png/providers/{service.local_icon_name}.png")
        try:
            self._response(handler, HTTPStatus.OK, source_path.read_bytes(), "image/png")
        except OSError:
            self._response(handler, HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")

    def _handle_api(self, handler: BaseHTTPRequestHandler) -> None:
        if urlparse(handler.path).path != "/api":
            self._response(handler, HTTPStatus.NOT_FOUND, b'{"ok":false,"error":"Not found"}', "application/json")
            return
        if not secrets.compare_digest(handler.headers.get("X-Authenticator-MUI", ""), self.token):
            self._response(handler, HTTPStatus.FORBIDDEN, b'{"ok":false,"error":"Unauthorized"}', "application/json")
            return
        try:
            length = int(handler.headers.get("Content-Length", "0"))
            if length < 2 or length > 200_000:
                raise MuiBridgeError("无效的界面请求")
            raw = json.loads(handler.rfile.read(length).decode("utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("action"), str):
                raise MuiBridgeError("无效的界面请求")
            payload = raw.get("payload", {})
            if not isinstance(payload, dict):
                raise MuiBridgeError("无效的界面请求")
            action = raw["action"]
            if action in self._TERMINAL_TRANSPORT_ACTIONS:
                # SSH I/O has no Tk or vault ownership. Keeping it off the UI
                # queue avoids adding the UI scheduler's delay to every key
                # press and terminal output batch.
                result = self._dispatch_terminal_transport(action, payload)
            else:
                request = _UiRequest(action, payload)
                self._requests.put(request)
                if not request.completed.wait(timeout=30):
                    raise MuiBridgeError("界面操作超时，请重试")
                if request.error is not None:
                    raise request.error
                result = request.result
            response = {"ok": True, "result": result}
            self._response(handler, HTTPStatus.OK, json.dumps(response, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        except MuiBridgeError as error:
            response = {"ok": False, "error": str(error)}
            self._response(handler, HTTPStatus.BAD_REQUEST, json.dumps(response, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        except Exception:
            # Do not expose traceback, storage paths or internal service data to the page.
            response = {"ok": False, "error": "本地界面操作失败"}
            self._response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, json.dumps(response, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def process_requests(self, limit: int = 16) -> None:
        """Run queued requests from the Tk main thread only."""

        for _index in range(limit):
            try:
                request = self._requests.get_nowait()
            except queue.Empty:
                return
            try:
                request.result = self._dispatch(request.action, request.payload)
            except Exception as error:  # converted to an intentionally short UI error
                request.error = error if isinstance(error, MuiBridgeError) else MuiBridgeError(str(error) or "操作失败")
            finally:
                request.completed.set()

    def _dispatch_terminal_transport(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle one terminal-only request without entering the Tk queue."""

        try:
            if action == "terminal_events":
                wait_ms = integer_value(
                    payload.get("waitMs"),
                    int(self._TERMINAL_LONG_POLL_MAX_SECONDS * 1_000),
                    0,
                    int(self._TERMINAL_LONG_POLL_MAX_SECONDS * 1_000),
                )
                return {
                    "events": self.app.ssh_sessions.drain_events(
                        str(payload.get("sessionId") or ""),
                        wait_seconds=wait_ms / 1_000,
                    )
                }
            if action == "terminal_input":
                if self.app.locked:
                    raise MuiBridgeError("保险库已锁定，终端已关闭")
                data = payload.get("data")
                if not isinstance(data, str):
                    raise MuiBridgeError("终端输入无效")
                self.app.ssh_sessions.write(str(payload.get("sessionId") or ""), data)
                return {}
            if action == "terminal_resize":
                self.app.ssh_sessions.resize(
                    str(payload.get("sessionId") or ""),
                    integer_value(payload.get("cols"), 100, 20, 500),
                    integer_value(payload.get("rows"), 28, 8, 200),
                )
                return {}
            if action == "terminal_disconnect":
                self.app.ssh_sessions.close(str(payload.get("sessionId") or ""))
                return {}
        except SshSessionError as error:
            raise MuiBridgeError(str(error)) from error
        raise MuiBridgeError("不支持的终端操作")

    def _require_module(self, payload: dict[str, Any]) -> ModuleName:
        module = payload.get("module")
        if module not in {"otp", "passwords", "servers"}:
            raise MuiBridgeError("无效的模块")
        return module

    def _active_module(self) -> ModuleName:
        module = getattr(self.app, "_mui_active_module", None)
        if module not in {"otp", "passwords", "servers"}:
            module = getattr(getattr(self.app, "module_coordinator", None), "active", "otp")
        return module if module in {"otp", "passwords", "servers"} else "otp"

    def _set_active_module(self, payload: dict[str, Any]) -> ModuleName:
        module = self._require_module(payload)
        if getattr(self, "page_mode", "full") == "compact" and module == "servers":
            raise MuiBridgeError("服务器模块不提供轻量模式")
        self.app._mui_active_module = module
        return module

    def _require_unlocked(self) -> None:
        if self.app._busy:
            raise MuiBridgeError("已有任务正在执行，请稍候")
        if self.app.locked:
            raise MuiBridgeError("请先解锁保险库")

    @staticmethod
    def _ids(payload: dict[str, Any]) -> list[str]:
        values = payload.get("ids", [])
        if not isinstance(values, list):
            raise MuiBridgeError("无效的记录选择")
        return [str(value) for value in values if str(value).strip()]

    @staticmethod
    def _parse_scope(items: list[NavigationItem], item_id: object) -> Any:
        wanted = str(item_id or "all")
        return next((item.scope for item in items if item.id == wanted), items[0].scope)

    @staticmethod
    def _sort(module: ModuleName, raw: object) -> OtpSortSpec | PasswordSortSpec:
        raw = raw if isinstance(raw, dict) else {}
        field = str(raw.get("field", "created"))
        direction = str(raw.get("direction", "descending"))
        try:
            if module == "otp":
                return OtpSortSpec(OtpSortField(field), SortDirection(direction))
            return PasswordSortSpec(PasswordSortField(field), SortDirection(direction))
        except ValueError:
            return OtpSortSpec() if module == "otp" else PasswordSortSpec()

    def _apply_view_state(
        self, module: ModuleName, payload: dict[str, Any]
    ) -> tuple[list[Any], Any, list[NavigationItem]]:
        query = str(payload.get("query", ""))[:1_000]
        show_pinned = payload.get("showPinned") is not False
        sort = self._sort(module, payload.get("sort"))
        if module == "otp":
            model = self.app.main_view_model
            navigation = model.navigation_items()
            model.set_scope(self._parse_scope(navigation, payload.get("scope")))
            model.set_sort(sort)
            model.set_show_pinned(show_pinned)
            model.update_state(query=query, active_group_id=model.active_group_id, locked=self.app.locked, scope=model.scope)
            if (self.app.settings.otp_sort_field, self.app.settings.otp_sort_direction) != (sort.field.value, sort.direction.value):
                self.app.settings.otp_sort_field, self.app.settings.otp_sort_direction = sort.field.value, sort.direction.value
                self.app.settings_repository.save(self.app.settings)
            self.app.settings.otp_show_pinned = show_pinned
            return model.visible_entries(), model, navigation
        model = self.app.password_view_model
        navigation = model.navigation_items()
        model.set_scope(self._parse_scope(navigation, payload.get("scope")))
        model.set_sort(sort)
        model.set_show_pinned(show_pinned)
        model.update_state(query=query, active_group_id=model.active_group_id, locked=self.app.locked, scope=model.scope)
        if (self.app.settings.password_sort_field, self.app.settings.password_sort_direction) != (sort.field.value, sort.direction.value):
            self.app.settings.password_sort_field, self.app.settings.password_sort_direction = sort.field.value, sort.direction.value
            self.app.settings_repository.save(self.app.settings)
        self.app.settings.password_show_pinned = show_pinned
        return model.visible_entries(), model, navigation

    def _nav_items(self, items: list[NavigationItem]) -> list[dict[str, Any]]:
        navigation: list[dict[str, Any]] = []
        icon_cache = getattr(self, "_brand_icon_cache", None)
        for item in items:
            service = service_metadata_by_key(item.brand_key or "")
            icon_url = None
            if service is not None:
                version = icon_cache.version(service) if icon_cache is not None else "local"
                icon_url = f"/brand-icons/{service.key}.png?v={version}"
            navigation.append(
                {
                    "id": item.id,
                    "label": item.label,
                    "count": item.count,
                    "icon": item.icon_key,
                    "kind": item.section,
                    "brandKey": item.brand_key,
                    "officialUrl": item.official_url,
                    "iconUrl": icon_url,
                }
            )
        return navigation

    def _groups(self, module: ModuleName) -> list[dict[str, Any]]:
        groups = self.app.vault.groups if module == "otp" else self.app.vault.password_groups
        entries = self.app.vault.entries if module == "otp" else self.app.vault.password_entries
        default_id = "default" if module == "otp" else "password-default"
        counts: dict[str, int] = {}
        for entry in entries:
            for group_id in entry.group_ids:
                counts[group_id] = counts.get(group_id, 0) + 1
        return [
            {
                "id": group.id,
                "name": group.name,
                "count": counts.get(group.id, 0),
                "system": group.id == default_id,
            }
            for group in groups
        ]

    @staticmethod
    def _stats(module: ModuleName, model: Any) -> list[dict[str, str]]:
        if module == "otp":
            stats = model.dashboard_stats(time.time())
            values = (
                ("--" if stats.locked else str(stats.total), "总账号数", "当前保险库", "blue"),
                ("--" if stats.locked else str(stats.valid), "正常", "验证码可用", "green"),
                ("--" if stats.locked else str(stats.expiring), "即将刷新", "10 秒内刷新", "orange"),
                (stats.mode_title, "验证码类型", stats.mode_detail, "purple"),
            )
        else:
            stats = model.dashboard_stats()
            values = (
                ("--" if stats.locked else str(stats.total), "密码记录", "当前保险库", "blue"),
                ("--" if stats.locked else str(stats.pinned), "已置顶", "快速访问", "green"),
                ("--" if stats.locked else str(stats.with_url), "包含网址", "可直接打开", "orange"),
                ("--" if stats.locked else str(stats.custom_groups), "自定义分组", "独立于验证码", "purple"),
            )
        return [{"value": value, "label": label, "detail": detail, "tone": tone} for value, label, detail, tone in values]

    def _server_profile_payload(self, profile: Any) -> dict[str, Any]:
        trusted_key = profile.trusted_host_key
        return {
            "id": profile.id,
            "name": profile.name,
            "host": profile.host,
            "port": profile.port,
            "username": profile.username,
            "authKind": profile.auth_kind.value,
            "credentialsConfigured": profile.credentials_configured,
            "notes": profile.notes,
            "trustedFingerprint": trusted_key.fingerprint if trusted_key is not None else "",
            "trustedAlgorithm": trusted_key.algorithm if trusted_key is not None else "",
            "createdAt": format_created_at(profile.created_at),
            "updatedAt": format_created_at(profile.updated_at),
        }

    def _server_snapshot(self) -> dict[str, Any]:
        profiles = [] if self.app.locked else [
            self._server_profile_payload(profile) for profile in self.app.server_service.list()
        ]
        terminal_tabs: list[dict[str, str]] = []
        if not self.app.locked and hasattr(self.app, "ssh_sessions"):
            terminal_tabs = [
                {
                    "id": session.id,
                    "profileId": session.profile_id,
                    "name": session.profile_name,
                    "status": session.state,
                }
                for session in self.app.ssh_sessions.list_sessions()
            ]
        return {
            "ready": self.app._vault_loaded,
            "locked": self.app.locked,
            "busy": self.app._busy,
            "module": "servers",
            "security": "保险库已锁定" if self.app.locked else "服务器凭据已由本地保险库加密",
            "status": self.app.status_var.get(),
            "summary": f"{len(profiles)} 台服务器",
            "showPinned": True,
            "onTop": self.app.window_on_top,
            "compactAvailable": False,
            "navigation": [],
            "groups": [],
            "stats": [],
            "rows": [],
            "sort": {"field": "created", "direction": "descending"},
            "apiEndpoint": "",
            "autolockMinutes": self.app.settings.autolock_minutes,
            "otpCodesVisible": self.app.settings.otp_codes_visible,
            "passwordsVisible": self.app.settings.passwords_visible,
            "servers": profiles,
            "terminalTabs": terminal_tabs,
        }

    def _server_details(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_unlocked()
        profile = self.app.server_service.get(str(payload.get("id") or ""))
        return self._server_profile_payload(profile)

    def _choose_private_key(self) -> dict[str, str]:
        self._require_unlocked()
        from tkinter import filedialog

        selected = filedialog.askopenfilename(
            parent=self.app,
            title="导入 SSH 私钥",
            filetypes=(("SSH 私钥", "*.pem *.key *.ppk *"), ("所有文件", "*.*")),
        )
        if not selected:
            return {"keyRef": "", "filename": ""}
        try:
            content = Path(selected).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = Path(selected).read_text(encoding="utf-8-sig")
        except OSError as error:
            raise MuiBridgeError("无法读取所选私钥文件") from error
        if not content.strip() or len(content) > 65_536:
            raise MuiBridgeError("私钥文件为空或过大")
        reference = secrets.token_urlsafe(24)
        self._private_key_imports[reference] = (content, Path(selected).name)
        return {"keyRef": reference, "filename": Path(selected).name}

    def _server_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = payload.get("server")
        if not isinstance(raw, dict):
            raise MuiBridgeError("无效的服务器资料")
        try:
            auth_kind = ServerAuthKind(str(raw.get("authKind", ServerAuthKind.PASSWORD)))
        except ValueError as error:
            raise MuiBridgeError("不支持的 SSH 认证方式") from error
        key_reference = str(raw.get("privateKeyRef") or "")
        private_key = ""
        if key_reference:
            stored_key = self._private_key_imports.pop(key_reference, None)
            if stored_key is None:
                raise MuiBridgeError("私钥导入已过期，请重新选择文件")
            private_key = stored_key[0]
        return {
            "id": str(raw.get("id") or ""),
            "name": str(raw.get("name") or ""),
            "host": str(raw.get("host") or ""),
            "port": integer_value(raw.get("port"), 22, 1, 65_535),
            "username": str(raw.get("username") or ""),
            "auth_kind": auth_kind,
            "password": str(raw.get("password") or ""),
            "private_key": private_key,
            "private_key_passphrase": str(raw.get("privateKeyPassphrase") or ""),
            "notes": str(raw.get("notes") or ""),
            "replace_credentials": raw.get("replaceCredentials") is True or bool(key_reference),
        }

    def _save_server(self, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        record = self._server_record(payload)
        try:
            if record["id"]:
                previous = self.app.server_service.get(record["id"])
                profile = self.app.server_service.update(
                    previous.id,
                    UpdateServerCommand(**{key: value for key, value in record.items() if key != "id"}),
                )
                if (
                    previous.host != profile.host
                    or previous.port != profile.port
                    or previous.username != profile.username
                    or previous.auth_kind != profile.auth_kind
                    or record["replace_credentials"]
                ):
                    self.app.ssh_sessions.close_profile(profile.id)
            else:
                profile = self.app.server_service.create(
                    CreateServerCommand(**{key: value for key, value in record.items() if key not in {"id", "replace_credentials"}})
                )
        except ValueError as error:
            raise MuiBridgeError(str(error)) from error
        return {"message": f"已保存服务器“{profile.name}”。", "id": profile.id}

    def _connect_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_unlocked()
        profile = self.app.server_service.get(str(payload.get("id") or ""))
        try:
            session = self.app.ssh_sessions.connect(
                profile,
                cols=integer_value(payload.get("cols"), 100, 20, 500),
                rows=integer_value(payload.get("rows"), 28, 8, 200),
            )
        except ValueError as error:
            raise MuiBridgeError(str(error)) from error
        return {
            "sessionId": session.id,
            "name": profile.name,
            "profileId": profile.id,
        }

    def _terminal_events(self, payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Return a bounded batch of terminal events through the authenticated MUI bridge."""

        try:
            return {"events": self.app.ssh_sessions.drain_events(str(payload.get("sessionId") or ""))}
        except SshSessionError:
            return {"events": [{"type": "status", "status": "error", "message": "终端会话已结束，请重新连接。"}]}

    def _terminal_input(self, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        data = payload.get("data")
        if not isinstance(data, str):
            raise MuiBridgeError("终端输入无效")
        self.app.ssh_sessions.write(str(payload.get("sessionId") or ""), data)
        return {}

    def _terminal_resize(self, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        self.app.ssh_sessions.resize(
            str(payload.get("sessionId") or ""),
            integer_value(payload.get("cols"), 100, 20, 500),
            integer_value(payload.get("rows"), 28, 8, 200),
        )
        return {}

    def _confirm_server_host_key(self, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        session_id = str(payload.get("sessionId") or "")
        session = self.app.ssh_sessions.get(session_id)
        if session is None or session.pending_host_key is None:
            raise MuiBridgeError("主机指纹确认已失效")
        self.app.server_service.set_trusted_host_key(session.profile_id, session.pending_host_key)
        self.app.ssh_sessions.approve_host_key(session_id)
        return {"message": "已信任服务器主机指纹，正在继续连接。"}

    def _disconnect_server(self, payload: dict[str, Any]) -> dict[str, str]:
        session_id = str(payload.get("sessionId") or "")
        self.app.ssh_sessions.close(session_id)
        return {"message": "SSH 终端已断开。"}

    def _disconnect_server_profile(self, payload: dict[str, Any]) -> dict[str, str]:
        profile_id = str(payload.get("id") or "")
        self.app.ssh_sessions.close_profile(profile_id)
        return {"message": "该服务器的 SSH 终端已断开。"}

    def _reset_server_host_key(self, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        profile_id = str(payload.get("id") or "")
        self.app.ssh_sessions.close_profile(profile_id)
        self.app.server_service.reset_trusted_host_key(profile_id)
        return {"message": "已重置信任指纹，下次连接需重新确认。"}

    def _delete_server(self, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        profile_id = str(payload.get("id") or "")
        self.app.ssh_sessions.close_profile(profile_id)
        self.app.server_service.delete(profile_id)
        return {"message": "服务器已删除。"}

    def _snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("compact") is True:
            return self._compact_snapshot(payload)
        module = self._require_module(payload)
        if module == "servers":
            return self._server_snapshot()
        entries, model, navigation = self._apply_view_state(module, payload)
        locked = self.app.locked
        now = time.time()
        rows: list[dict[str, Any]] = []
        if module == "otp":
            for entry in entries:
                try:
                    code = entry.code(now)
                    invalid = False
                except ValueError:
                    code, invalid = "密钥无效", True
                rows.append(
                    {
                        "id": entry.id, "title": entry.title, "account": entry.account, "code": code,
                        "remaining": entry.remaining_seconds(now), "period": entry.period, "type": entry.type_label,
                        "createdAt": format_created_at(entry.created_at), "favorite": entry.favorite,
                        "pinned": entry.pinned, "invalid": invalid,
                    }
                )
        else:
            for entry in entries:
                rows.append(
                    {
                        "id": entry.id, "title": entry.title, "username": entry.username,
                        "password": "••••••••••••", "url": entry.url, "createdAt": format_created_at(entry.created_at),
                        "favorite": entry.favorite, "pinned": entry.pinned,
                    }
                )
        return {
            "ready": self.app._vault_loaded,
            "locked": locked,
            "busy": self.app._busy,
            "module": module,
            "security": model.security_summary(self.app.vault.encrypted, self.app.settings.autolock_minutes) if module == "otp" else ("保险库已锁定" if locked else "本地安全数据已加密"),
            "status": self.app.status_var.get(),
            "summary": model.result_summary(len(entries)),
            "showPinned": model.show_pinned,
            "onTop": self.app.window_on_top,
            "compactAvailable": True,
            "navigation": self._nav_items(navigation),
            "groups": self._groups(module),
            "stats": self._stats(module, model),
            "rows": rows,
            "sort": {"field": model.sort_spec.field.value, "direction": model.sort_spec.direction.value},
            "apiEndpoint": self.app.api_endpoint,
            "autolockMinutes": self.app.settings.autolock_minutes,
            "otpCodesVisible": self.app.settings.otp_codes_visible,
            "passwordsVisible": self.app.settings.passwords_visible,
        }

    @staticmethod
    def _dynamic_otp_rows(entries: list[OTPEntry], now: float, highlighted_ids: set[str] | None = None) -> list[dict[str, Any]]:
        """Return only fields that naturally change while an OTP page is idle."""

        highlighted_ids = highlighted_ids or set()
        rows: list[dict[str, Any]] = []
        for entry in entries:
            try:
                code = entry.code(now)
                invalid = False
            except ValueError:
                code, invalid = "密钥无效", True
            rows.append(
                {
                    "id": entry.id,
                    "code": code,
                    "remaining": entry.remaining_seconds(now),
                    "invalid": invalid,
                    "highlighted": entry.id in highlighted_ids,
                }
            )
        return rows

    def _dynamic_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Serve a lightweight timer refresh without rebuilding static UI data."""

        compact = payload.get("compact") is True
        expected_ids = tuple(str(value) for value in payload.get("rowIds", []) if str(value))
        if self.app.locked:
            return {
                "locked": True,
                "busy": self.app._busy,
                "onTop": self.app.window_on_top,
                "status": self.app.status_var.get(),
                "structureChanged": bool(expected_ids),
                "rows": [],
            }
        if compact:
            if payload.get("module", self._active_module()) != "otp":
                return {
                    "locked": False, "busy": self.app._busy, "onTop": self.app.window_on_top,
                    "status": self.app.status_var.get(), "structureChanged": False, "rows": [],
                }
            query = str(payload.get("query", ""))[:1_000]
            entries = self.app.search_service.search(self.app.vault.entries, query)
            rows = self._dynamic_otp_rows(entries, time.time(), self._active_highlights())
        else:
            module = self._require_module(payload)
            if module != "otp":
                return {
                    "locked": False,
                    "busy": self.app._busy,
                    "onTop": self.app.window_on_top,
                    "status": self.app.status_var.get(),
                    "structureChanged": False,
                    "rows": [],
                }
            # ``_apply_view_state`` runs only for structural snapshots. It
            # maintains the active query/scope/sort model used here.
            entries = self.app.main_view_model.visible_entries()
            rows = self._dynamic_otp_rows(entries, time.time())
        actual_ids = tuple(row["id"] for row in rows)
        return {
            "locked": False,
            "busy": self.app._busy,
            "onTop": self.app.window_on_top,
            "status": self.app.status_var.get(),
            "structureChanged": actual_ids != expected_ids,
            "rows": rows,
        }

    def _compact_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return either small-window list without mutating full-view state.

        The full React page can remain alive while its Tk parent is hidden.
        Keeping the compact query local prevents the two renderer instances
        from overwriting one another's sorting and navigation state.
        """

        query = str(payload.get("query", ""))[:1_000]
        module = payload.get("module", self._active_module())
        if module not in {"otp", "passwords"}:
            raise MuiBridgeError("该模块不提供轻量模式")
        now = time.time()
        rows: list[dict[str, Any]] = []
        if not self.app.locked and module == "otp":
            entries = self.app.search_service.search(self.app.vault.entries, query)
            highlighted_ids = self._active_highlights()
            for entry in entries:
                try:
                    code = entry.code(now)
                    invalid = False
                except ValueError:
                    code, invalid = "密钥无效", True
                rows.append(
                    {
                        "id": entry.id, "title": entry.title, "account": entry.account, "code": code,
                        "remaining": entry.remaining_seconds(now), "period": entry.period, "type": entry.type_label,
                        "createdAt": format_created_at(entry.created_at), "favorite": entry.favorite,
                        "pinned": entry.pinned, "invalid": invalid, "highlighted": entry.id in highlighted_ids,
                    }
                )
        elif not self.app.locked:
            for password_entry in self.app.password_service.list(query=query):
                rows.append(
                    {
                        "id": password_entry.id, "title": password_entry.title, "username": password_entry.username,
                        "password": "••••••••••••", "url": password_entry.url,
                        "createdAt": format_created_at(password_entry.created_at),
                        "favorite": password_entry.favorite, "pinned": password_entry.pinned,
                    }
                )
        return {
            "ready": self.app._vault_loaded,
            "locked": self.app.locked,
            "busy": self.app._busy,
            "module": module,
            "security": "保险库已锁定" if self.app.locked else "本地数据已加密",
            "status": self.app.status_var.get(),
            "summary": f"{len(rows)} {'个账号' if module == 'otp' else '条密码'}",
            "showPinned": True,
            "onTop": self.app.window_on_top,
            "compactAvailable": True,
            "navigation": [],
            "groups": self._groups(module),
            "stats": [],
            "rows": rows,
            "sort": {"field": "created", "direction": "descending"},
            "apiEndpoint": "",
            "autolockMinutes": self.app.settings.autolock_minutes,
            "otpCodesVisible": self.app.settings.otp_codes_visible,
            "passwordsVisible": self.app.settings.passwords_visible,
            "compactClipboard": self.app.settings.compact_clipboard,
        }

    def highlight_accounts(self, entry_ids: list[str] | tuple[str, ...] | set[str]) -> None:
        """Expose compact scan success feedback without a Tk widget rebuild."""

        self._highlighted_ids = {str(entry_id) for entry_id in entry_ids}
        self._highlight_until = time.monotonic() + 5

    def _active_highlights(self) -> set[str]:
        if time.monotonic() > getattr(self, "_highlight_until", 0.0):
            self._highlighted_ids = set()
        return set(getattr(self, "_highlighted_ids", set()))

    def _find_otp(self, record_id: object) -> OTPEntry:
        entry = next((item for item in self.app.vault.entries if item.id == str(record_id)), None)
        if entry is None:
            raise MuiBridgeError("账号不存在")
        return entry

    def _find_password(self, record_id: object) -> Any:
        entry = next((item for item in self.app.vault.password_entries if item.id == str(record_id)), None)
        if entry is None:
            raise MuiBridgeError("密码记录不存在")
        return entry

    def _visible_passwords(self, payload: dict[str, Any]) -> dict[str, dict[str, str]]:
        """Return plaintext only for the small set of rows visible in the table."""

        self._require_unlocked()
        ids = payload.get("ids")
        if not isinstance(ids, list) or len(ids) > 64 or any(not isinstance(item, str) for item in ids):
            raise MuiBridgeError("无效的可见记录")
        wanted = set(ids)
        return {
            "passwords": {
                entry.id: entry.password
                for entry in self.app.vault.password_entries
                if entry.id in wanted
            }
        }

    def _record_details(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_unlocked()
        module = self._require_module(payload)
        if module == "otp":
            entry = self._find_otp(payload.get("id"))
            return {
                "id": entry.id, "issuer": entry.issuer, "account": entry.account, "secret": entry.secret,
                "otpType": entry.otp_type, "counter": str(entry.counter), "period": str(entry.period),
                "digits": str(entry.digits), "algorithm": entry.algorithm, "name": "", "username": "", "password": "", "url": "", "notes": "",
                "favorite": entry.favorite, "pinned": entry.pinned, "groupIds": list(entry.group_ids),
            }
        entry = self._find_password(payload.get("id"))
        return {
            "id": entry.id, "issuer": "", "account": "", "secret": "", "otpType": "totp", "counter": "0", "period": "30", "digits": "6", "algorithm": "SHA1",
            "name": entry.name, "username": entry.username, "password": entry.password, "url": entry.url, "notes": entry.notes,
            "favorite": entry.favorite, "pinned": entry.pinned, "groupIds": list(entry.group_ids),
        }

    @staticmethod
    def _record_payload(payload: dict[str, Any]) -> dict[str, Any]:
        record = payload.get("record")
        if not isinstance(record, dict):
            raise MuiBridgeError("无效的记录内容")
        return record

    def _save_record(self, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        module = self._require_module(payload)
        record = self._record_payload(payload)
        group_ids = tuple(str(value) for value in record.get("groupIds", []) if str(value).strip())
        if module == "otp":
            record_id = str(record.get("id") or uuid.uuid4())
            current = next((entry for entry in self.app.vault.entries if entry.id == record_id), None)
            entry = OTPEntry(
                id=record_id,
                issuer=str(record.get("issuer", "")),
                account=str(record.get("account", "")),
                secret=str(record.get("secret", "")),
                otp_type=str(record.get("otpType", "totp")),
                counter=integer_value(record.get("counter"), 0, 0, 2**63 - 1),
                period=integer_value(record.get("period"), 30, 1, 86_400),
                digits=integer_value(record.get("digits"), 6, 4, 10),
                algorithm=str(record.get("algorithm", "SHA1")),
                # The MUI editor intentionally does not expose the legacy
                # Base32/hex storage implementation detail. Preserve it when
                # an existing entry is edited rather than silently converting
                # a hex secret to Base32 semantics.
                secret_encoding=current.secret_encoding if current else "base32",
                created_at=current.created_at if current else utc_now_iso(),
                group_ids=list(group_ids),
                favorite=record.get("favorite") is True,
                pinned=record.get("pinned") is True,
            )
            if current is None:
                self.app.account_service.create(entry, active_group_id=self.app.main_view_model.active_group_id)
            else:
                self.app.account_service.update(entry)
            self.app._remember_last_issuer(entry.issuer)
            self.app._show_status(f"已{'更新' if current else '新增'} {entry.title}。")
        else:
            command_type: Callable[..., Any] = UpdatePasswordCommand if record.get("id") else CreatePasswordCommand
            command = command_type(
                username=str(record.get("username", "")), password=str(record.get("password", "")),
                name=str(record.get("name", "")), url=str(record.get("url", "")), notes=str(record.get("notes", "")),
                pinned=record.get("pinned") is True, favorite=record.get("favorite") is True, group_ids=group_ids,
            )
            if record.get("id"):
                self.app.password_service.update(str(record["id"]), command)
            else:
                self.app.password_service.create(command)
            self.app._show_status("密码记录已保存。")
        self.app.refresh_tree()
        return {"message": "记录已保存"}

    def _set_boolean(self, payload: dict[str, Any], name: Literal["favorite", "pinned"]) -> dict[str, str]:
        self._require_unlocked()
        module = self._require_module(payload)
        ids = self._ids(payload)
        value = payload.get("value") is True
        if module == "otp":
            getattr(self.app.account_service, f"set_{name}")(ids, value)
        else:
            getattr(self.app.password_service, f"set_{name}")(ids, value)
        self.app.refresh_tree()
        return {"message": "状态已更新"}

    def _groups_action(self, action: str, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        module = self._require_module(payload)
        service = self.app.group_service if module == "otp" else self.app.password_group_service
        if action == "create_group":
            service.create(str(payload.get("name", "")))
        elif action == "delete_group":
            service.delete(str(payload.get("id", "")))
        else:
            service.assign(self._ids(payload), [str(value) for value in payload.get("groupIds", [])])
        self.app.refresh_tree()
        return {"message": "分组已更新"}

    def _copy(
        self,
        payload: dict[str, Any],
        kind: Literal["account", "code", "username", "password"],
    ) -> dict[str, str]:
        self._require_unlocked()
        if kind in {"account", "code"}:
            entry = self._find_otp(payload.get("id"))
            if kind == "account":
                value, title = entry.account, entry.title
                message = f"已复制 {title} 的账号。"
            else:
                value, title = entry.code(), entry.title
                message = f"已复制 {title} 的验证码。"
        else:
            entry = self._find_password(payload.get("id"))
            value, title = (entry.username if kind == "username" else entry.password), entry.title
            message = f"已复制 {title} 的{'用户名' if kind == 'username' else '密码'}。"
        self.app.clipboard_clear()
        self.app.clipboard_append(value)
        self.app._show_status(message)
        return {"message": message}

    def _unlock(self, payload: dict[str, Any]) -> dict[str, str]:
        if not self.app.locked:
            return {"message": "保险库已解锁"}
        password = str(payload.get("password", ""))
        if not password:
            raise MuiBridgeError("请输入主密码")
        self.app.vault_service.unlock(password)
        self.app._storage_load_kind = StorageLoadKind.AUTO_UNLOCKED
        self.app._activate_secure_data("本地安全数据已解锁。")
        return {"message": "保险库已解锁"}

    def _scan(self, payload: dict[str, Any]) -> dict[str, str]:
        self._require_unlocked()
        compact = payload.get("compact") is True
        compact_window = getattr(self.app, "compact_window", None) if compact else None
        host = compact_window if compact_window is not None else self.app
        flow = self._scan_flows.get(compact)
        if flow is None or flow.host is not host:
            flow = QrScanFlow(host, self.app.qr_scanner, self.app.background_tasks)
            self._scan_flows[compact] = flow
        windows = (self.app, compact_window) if compact_window is not None else (self.app,)
        started = flow.start(
            windows,
            self.app.add_scanned_payload,
            lambda error: self.app._show_status(f"扫码失败：{error}"),
            on_cancel=lambda: self.app._show_status("已取消扫码。"),
            on_state_changed=lambda state: self.app._show_status(
                {"automatic": "正在识别屏幕二维码...", "selecting": "请框选二维码", "decoding": "正在识别二维码..."}.get(state, "正在识别二维码...")
            ),
        )
        if not started:
            raise MuiBridgeError("扫码正在进行")
        return {"message": "正在识别二维码"}

    def _dispatch(self, action: str, payload: dict[str, Any]) -> Any:
        if action == "active_module":
            return {"module": self._active_module()}
        if action == "set_module":
            return {"module": self._set_active_module(payload)}
        if action == "snapshot":
            return self._snapshot(payload)
        if action == "dynamic":
            return self._dynamic_snapshot(payload)
        if action == "record_details":
            return self._record_details(payload)
        if action == "save_record":
            return self._save_record(payload)
        if action == "server_details":
            return self._server_details(payload)
        if action == "server_choose_private_key":
            return self._choose_private_key()
        if action == "save_server":
            return self._save_server(payload)
        if action == "connect_server":
            return self._connect_server(payload)
        if action == "terminal_events":
            return self._terminal_events(payload)
        if action == "terminal_input":
            return self._terminal_input(payload)
        if action == "terminal_resize":
            return self._terminal_resize(payload)
        if action == "confirm_server_host_key":
            return self._confirm_server_host_key(payload)
        if action == "disconnect_server":
            return self._disconnect_server(payload)
        if action == "disconnect_server_profile":
            return self._disconnect_server_profile(payload)
        if action == "reset_server_host_key":
            return self._reset_server_host_key(payload)
        if action == "delete_server":
            return self._delete_server(payload)
        if action == "set_favorite":
            return self._set_boolean(payload, "favorite")
        if action == "set_pinned":
            return self._set_boolean(payload, "pinned")
        if action in {"create_group", "delete_group", "assign_groups"}:
            return self._groups_action(action, payload)
        if action == "delete":
            self._require_unlocked()
            ids, module = self._ids(payload), self._require_module(payload)
            deleted = self.app.account_service.delete(ids) if module == "otp" else self.app.password_service.delete(ids)
            self.app.refresh_tree()
            return {"message": f"已删除 {deleted} 条记录。"}
        if action in {"copy_account", "copy_code", "copy_username", "copy_password"}:
            copy_kinds: dict[str, Literal["account", "code", "username", "password"]] = {
                "copy_account": "account",
                "copy_code": "code",
                "copy_username": "username",
                "copy_password": "password",
            }
            return self._copy(payload, copy_kinds[action])
        if action == "reveal_password":
            self._require_unlocked()
            return {"password": self._find_password(payload.get("id")).password}
        if action == "visible_passwords":
            return self._visible_passwords(payload)
        if action == "open_website":
            self._require_unlocked()
            entry = self._find_password(payload.get("id"))
            if not entry.url:
                raise MuiBridgeError("该密码记录没有网址")
            webbrowser.open(entry.url)
            return {"message": "已在默认浏览器打开网站"}
        if action == "set_show_pinned":
            module = self._require_module(payload)
            value = payload.get("value") is not False
            if module == "otp":
                self.app.settings.otp_show_pinned = value
            else:
                self.app.settings.password_show_pinned = value
            self.app.settings_repository.save(self.app.settings)
            return {"message": "显示设置已更新"}
        if action == "toggle_topmost":
            self.app.toggle_always_on_top()
            return {"message": "窗口置顶状态已更新"}
        if action == "compact":
            self._require_unlocked()
            module = self._require_module(payload) if "module" in payload else self._active_module()
            if module == "servers":
                raise MuiBridgeError("服务器模块不提供轻量模式")
            self._set_active_module({"module": module})
            # Let the initiating WebView receive this response before its
            # parent is hidden. The prewarmed compact renderer then appears
            # without a transition toast or a competing snapshot request.
            self.app.after_idle(lambda: self.app.set_compact_mode(True))
            return {}
        if action == "return_full":
            if "module" in payload:
                self._set_active_module(payload)
            # Finish this loopback response before hiding the initiating view.
            self.app.after_idle(lambda: self.app.set_compact_mode(False))
            return {}
        if action == "lock":
            self.app.lock_vault()
            return {"message": "保险库已锁定"}
        if action == "unlock":
            return self._unlock(payload)
        if action == "scan":
            return self._scan(payload)
        if action == "generate_password":
            return {"password": generate_password(PasswordGeneratorOptions())}
        if action == "save_settings":
            settings = self.app.settings
            previous = (settings.autolock_minutes, settings.otp_codes_visible, settings.passwords_visible)
            settings.autolock_minutes = integer_value(payload.get("autolockMinutes"), 0, 0, 1_440)
            settings.otp_codes_visible = payload.get("otpCodesVisible", previous[1]) is True
            settings.passwords_visible = payload.get("passwordsVisible", previous[2]) is True
            try:
                self.app._persist_settings()
            except Exception:
                settings.autolock_minutes, settings.otp_codes_visible, settings.passwords_visible = previous
                raise
            return {"message": "设置已保存"}
        if action == "set_compact_clipboard":
            self._require_unlocked()
            clipboard_value = str(payload.get("value", ""))[:4_096]
            previous = self.app.settings.compact_clipboard
            self.app.settings.compact_clipboard = clipboard_value
            try:
                self.app._persist_settings()
            except Exception:
                self.app.settings.compact_clipboard = previous
                raise
            self.app._show_status("常驻剪贴板已保存。")
            return {"message": "常驻剪贴板已保存"}
        if action == "copy_compact_clipboard":
            self._require_unlocked()
            clipboard_value = str(payload.get("value", ""))[:4_096]
            self.app.clipboard_clear()
            self.app.clipboard_append(clipboard_value)
            self.app._show_status("已复制常驻剪贴板内容。")
            return {"message": "已复制常驻剪贴板内容"}
        if action == "copy_api_token":
            self._require_unlocked()
            self.app.clipboard_clear()
            self.app.clipboard_append(self.app.api_token)
            return {"message": "API 令牌已复制"}
        if action == "import":
            self._require_unlocked()
            self.app.import_file()
            return {"message": "已打开导入窗口"}
        if action == "export_encrypted":
            self._require_unlocked()
            self.app.export_encrypted_backup()
            return {"message": "已打开导出窗口"}
        if action == "export_plain":
            self._require_unlocked()
            self.app.export_plain_backup()
            return {"message": "已打开导出窗口"}
        if action == "export_google":
            self._require_unlocked()
            self.app.export_google_authenticator_qr()
            return {"message": "正在生成二维码"}
        raise MuiBridgeError("不支持的界面操作")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._server.shutdown()
            self._server.server_close()
        finally:
            self._thread.join(timeout=0.25)
