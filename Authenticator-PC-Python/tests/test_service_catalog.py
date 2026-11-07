"""Public service metadata and icon cache coverage."""

from __future__ import annotations

import time

from infrastructure.brand_icon_cache import BrandIconCache, image_content_type
from infrastructure.service_catalog import service_metadata_for


def test_known_service_metadata_normalises_aliases_and_retains_official_website():
    service = service_metadata_for("ChatGPT")

    assert service is not None
    assert service.key == "openai"
    assert service.official_url == "https://openai.com"
    assert service.favicon_url.startswith("https://openai.com/")


def test_brand_icon_cache_refreshes_official_bytes_without_blocking_caller(tmp_path):
    service = service_metadata_for("GitHub")
    assert service is not None
    # Header-only PNG is sufficient here: the cache is deliberately a byte
    # transport and image decode belongs to the browser's renderer.
    cache = BrandIconCache(tmp_path, fetcher=lambda _service: b"\x89PNG\r\n\x1a\npublic-icon")

    assert cache.cached(service) is None
    cache.refresh_in_background(service)
    deadline = time.monotonic() + 2
    while cache.cached(service) is None and time.monotonic() < deadline:
        time.sleep(0.01)

    stored = cache.cached(service)
    assert stored == b"\x89PNG\r\n\x1a\npublic-icon"
    assert image_content_type(stored) == "image/png"
    assert cache.version(service) != "0"
