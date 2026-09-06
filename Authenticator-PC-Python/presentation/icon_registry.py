"""Runtime PNG icon registry with deterministic offline provider fallbacks."""

from __future__ import annotations

import hashlib
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageTk

from infrastructure.paths import resource_path
from presentation.dpi import DpiContext

ACTION_ALIASES = {
    "add": "plus",
    "import": "file-input",
    "export": "file-output",
    "compact": "scan-line",
    "topmost": "pin",
    "lock": "lock-keyhole",
    "unlock": "lock-keyhole-open",
    "more": "ellipsis",
    "grid": "layout-grid",
    "group": "folders",
    "edit": "pencil",
    "delete": "trash-2",
    "open": "external-link",
}

PROVIDER_ALIASES = {
    "openai": "openai",
    "chatgpt": "openai",
    "google": "google",
    "gmail": "google",
    "microsoft": "microsoft",
    "office": "microsoft",
    "outlook": "microsoftoutlook",
    "github": "github",
    "xai": "xai",
    "x.ai": "xai",
    "amazon": "amazon",
    "aws": "amazon",
    "discord": "discord",
    "steam": "steam",
    "battle.net": "battledotnet",
    "battlenet": "battledotnet",
}

PROVIDER_COLORS = {
    "openai": "#111827",
    "google": "#4285F4",
    "microsoft": "#2563EB",
    "microsoftoutlook": "#0078D4",
    "github": "#181717",
    "xai": "#111827",
    "amazon": "#FF9900",
    "discord": "#5865F2",
    "steam": "#1B2838",
    "battledotnet": "#148EFF",
}

FALLBACK_COLORS = (
    "#2563EB",
    "#0F9D76",
    "#7C3AED",
    "#DB7C0B",
    "#0E7490",
    "#BE4661",
)


class IconRegistry:
    def __init__(self, root: tk.Misc, dpi_context: DpiContext | None = None) -> None:
        self.root = root
        self.dpi_context = dpi_context or DpiContext()
        self._cache: dict[tuple[str, int, str], ImageTk.PhotoImage] = {}

    def invalidate_scale(self) -> None:
        self._cache.clear()

    @staticmethod
    def canonical_provider(value: str) -> str | None:
        key = " ".join(str(value or "").casefold().split())
        for alias, canonical in PROVIDER_ALIASES.items():
            if alias in key:
                return canonical
        return None

    def image(self, key: str, size: int = 20, tint: str | None = None) -> ImageTk.PhotoImage:
        pixel_size = self.dpi_context.dp(size)
        action_name = ACTION_ALIASES.get(key, key)
        action_path = resource_path(f"assets/icons/png/actions/{action_name}.png")
        provider_name = self.canonical_provider(key)
        provider_path = (
            resource_path(f"assets/icons/png/providers/{provider_name}.png")
            if provider_name
            else Path()
        )
        if action_path.exists():
            source_path = action_path
            color = tint or "#334155"
            cache_key = (f"action:{action_name}", pixel_size, color)
        elif provider_name and provider_path.exists():
            source_path = provider_path
            color = tint or PROVIDER_COLORS.get(provider_name, "#334155")
            cache_key = (f"provider:{provider_name}", pixel_size, color)
        else:
            color = tint or self._fallback_color(key)
            cache_key = (f"fallback:{key.casefold()}", pixel_size, color)
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
            fallback = self._fallback_image(key, pixel_size, color)
            image = ImageTk.PhotoImage(fallback, master=self.root)
            self._cache[cache_key] = image
            return image

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        with Image.open(source_path) as source:
            rgba = source.convert("RGBA").resize((pixel_size, pixel_size), Image.Resampling.LANCZOS)
        colored = self._tint(rgba, color)
        image = ImageTk.PhotoImage(colored, master=self.root)
        self._cache[cache_key] = image
        return image

    @staticmethod
    def _tint(image: Image.Image, color: str) -> Image.Image:
        red, green, blue = ImageColor.getrgb(color)[:3]
        alpha = image.getchannel("A")
        result = Image.new("RGBA", image.size, (red, green, blue, 0))
        result.putalpha(alpha)
        return result

    @staticmethod
    def _fallback_color(key: str) -> str:
        digest = hashlib.sha256(key.casefold().encode("utf-8")).digest()
        return FALLBACK_COLORS[digest[0] % len(FALLBACK_COLORS)]

    @staticmethod
    def _fallback_image(key: str, size: int, color: str) -> Image.Image:
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=max(3, size // 4), fill=color)
        label = next((character.upper() for character in key.strip() if character.isalnum()), "?")
        try:
            font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
                "msyh.ttc", max(9, int(size * 0.5))
            )
        except OSError:
            font = ImageFont.load_default()
        bounds = draw.textbbox((0, 0), label, font=font)
        text_width = bounds[2] - bounds[0]
        text_height = bounds[3] - bounds[1]
        draw.text(
            ((size - text_width) / 2, (size - text_height) / 2 - bounds[1]),
            label,
            fill="#FFFFFF",
            font=font,
        )
        return image
