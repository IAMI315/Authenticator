"""Offline-first cache for public provider favicons.

Only websites from :mod:`infrastructure.service_catalog` may be requested.
The renderer always talks to the loopback bridge; it never receives an external
favicon URL or performs a cross-origin request itself.
"""

from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from http.client import HTTPMessage
from pathlib import Path
from typing import IO
from urllib.parse import urlparse

from infrastructure.service_catalog import ServiceMetadata

MAX_ICON_BYTES = 512 * 1024
_ICON_SUFFIX = ".icon"


def image_content_type(value: bytes) -> str:
    """Identify the small image formats accepted from official favicon routes."""

    if value.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if value.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if value.startswith((b"\x00\x00\x01\x00", b"\x00\x00\x02\x00")):
        return "image/x-icon"
    if b"<svg" in value[:1024].lower():
        return "image/svg+xml"
    return ""


class _OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow favicon redirects only inside the declared official hostname."""

    def __init__(self, hostname: str) -> None:
        super().__init__()
        self.hostname = hostname.casefold()

    def redirect_request(
        self,
        request: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        target = newurl
        hostname = (urlparse(target).hostname or "").casefold()
        if hostname != self.hostname and not hostname.endswith(f".{self.hostname}"):
            return None
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class BrandIconCache:
    """Read cached icons and refresh missing/expired ones without blocking UI."""

    def __init__(
        self,
        directory: Path,
        fetcher: Callable[[ServiceMetadata], bytes] | None = None,
    ) -> None:
        self.directory = directory
        self._fetcher = fetcher or self._download
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self._next_retry: dict[str, float] = {}

    def cached(self, service: ServiceMetadata) -> bytes | None:
        try:
            value = self._path(service).read_bytes()
        except OSError:
            return None
        return value if image_content_type(value) else None

    def version(self, service: ServiceMetadata) -> str:
        """Return a cache-busting version without revealing a filesystem path."""

        try:
            return str(self._path(service).stat().st_mtime_ns)
        except OSError:
            return "0"

    def refresh_in_background(self, service: ServiceMetadata) -> None:
        """Schedule a single safe fetch for this provider until it finishes."""

        with self._lock:
            if service.key in self._pending or time.monotonic() < self._next_retry.get(service.key, 0):
                return
            self._pending.add(service.key)
        threading.Thread(
            target=self._refresh,
            args=(service,),
            name=f"brand-icon-{service.key}",
            daemon=True,
        ).start()

    def _refresh(self, service: ServiceMetadata) -> None:
        succeeded = False
        try:
            value = self._fetcher(service)
            if not image_content_type(value):
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self._path(service)
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(value)
            os.replace(temporary, target)
            succeeded = True
        except (OSError, urllib.error.URLError, ValueError):
            # Network availability and provider favicon support are optional;
            # the packaged icon remains the immediate offline fallback.
            return
        finally:
            with self._lock:
                self._pending.discard(service.key)
                # Failed favicon requests should not retry once per sidebar
                # refresh while the user is offline. Successful fetches still
                # refresh occasionally so provider artwork can be updated.
                self._next_retry[service.key] = time.monotonic() + (86_400 if succeeded else 900)

    def _download(self, service: ServiceMetadata) -> bytes:
        parsed = urlparse(service.favicon_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Only explicit HTTPS provider favicon URLs are allowed")
        opener = urllib.request.build_opener(_OfficialRedirectHandler(parsed.hostname))
        request = urllib.request.Request(
            service.favicon_url,
            headers={"User-Agent": "AuthenticatorDesktop/1.4", "Accept": "image/*"},
        )
        with opener.open(request, timeout=4) as response:
            length = int(response.headers.get("Content-Length", "0") or 0)
            if length > MAX_ICON_BYTES:
                raise ValueError("Provider icon is too large")
            value = response.read(MAX_ICON_BYTES + 1)
        if len(value) > MAX_ICON_BYTES:
            raise ValueError("Provider icon is too large")
        return value

    def _path(self, service: ServiceMetadata) -> Path:
        return self.directory / f"{service.key}{_ICON_SUFFIX}"
