"""独立于 Tk 控件的屏幕二维码截图、缩放和解码适配器。"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from typing import Any


class QrCodeNotFoundError(ValueError):
    """截图中没有可由本程序导入的普通 OTP 或 Google 迁移二维码。"""


def scale_screen_bbox(
    bbox: tuple[int, int, int, int],
    logical_screen: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """把逻辑屏幕坐标转换为截图物理像素坐标，兼容 Windows DPI 缩放。"""

    logical_left, logical_top, logical_width, logical_height = logical_screen
    image_width, image_height = image_size
    if logical_width <= 0 or logical_height <= 0:
        return bbox
    scale_x = image_width / logical_width
    scale_y = image_height / logical_height
    left, top, right, bottom = bbox
    return (
        math.floor((left - logical_left) * scale_x),
        math.floor((top - logical_top) * scale_y),
        math.ceil((right - logical_left) * scale_x),
        math.ceil((bottom - logical_top) * scale_y),
    )


def expand_image_bbox(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    padding_ratio: float = 0.08,
) -> tuple[int, int, int, int]:
    """Expand a selected QR region to recover its required quiet zone."""

    left, top, right, bottom = bbox
    image_width, image_height = image_size
    padding = max(12, round(min(max(1, right - left), max(1, bottom - top)) * padding_ratio))
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(image_width, right + padding),
        min(image_height, bottom + padding),
    )


class QrScanner:
    """从图像中寻找支持的 2FA 二维码，并由注入的解析器构造结果。"""

    def __init__(self, payload_parser: Callable[[str], Any]) -> None:
        """保存二维码文本解析器，避免基础设施依赖具体领域或应用类型。"""

        self._payload_parser = payload_parser

    def decode(self, image: Any) -> Any:
        """解码首个普通 OTP 或 Google 迁移 QR Code；未找到时抛出 ``ValueError``。"""

        import zxingcpp

        for candidate in self._decode_candidates(image):
            barcodes = zxingcpp.read_barcodes(candidate, formats=zxingcpp.BarcodeFormat.QRCode)
            for barcode in barcodes:
                if not isinstance(barcode.text, str):
                    continue
                uri = barcode.text.strip()
                if not uri.lower().startswith(("otpauth://", "otpauth-migration://")):
                    continue
                try:
                    return self._payload_parser(uri)
                except ValueError:
                    # 全屏可能同时出现过期/损坏二维码和有效二维码，继续尝试其余结果。
                    continue
        raise QrCodeNotFoundError(
            "选定区域中未识别到有效的 2FA 二维码，请完整框选二维码并保留周围白边"
        )

    @staticmethod
    def _decode_candidates(image: Any) -> Iterator[Any]:
        """Yield bounded preprocessing variants for dense or tightly cropped QR codes."""

        from PIL import Image, ImageOps

        yield image
        try:
            rgb = image.convert("RGB")
            width, height = rgb.size
        except (AttributeError, TypeError, ValueError):
            return
        border = max(16, round(min(width, height) * 0.06))
        bordered = ImageOps.expand(rgb, border=border, fill="white")
        yield bordered
        minimum_side = min(width, height)
        if minimum_side <= 0:
            return
        target_side = 700
        scale = target_side / minimum_side
        resized = rgb.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
        yield ImageOps.expand(resized, border=max(16, round(target_side * 0.06)), fill="white")

    def capture_region(
        self,
        bbox: tuple[int, int, int, int],
        logical_screen: tuple[int, int, int, int],
    ) -> Any:
        """Capture and safely expand a region while all application windows remain hidden."""

        from PIL import ImageGrab

        screenshot = ImageGrab.grab(all_screens=True)
        physical_bbox = scale_screen_bbox(bbox, logical_screen, screenshot.size)
        return screenshot.crop(expand_image_bbox(physical_bbox, screenshot.size))

    @staticmethod
    def capture_screen() -> Any:
        """截取完整虚拟桌面，供轻量窗口先执行无交互自动识别。"""

        from PIL import ImageGrab

        return ImageGrab.grab(all_screens=True)

    def scan_screen(self) -> Any:
        """截取完整虚拟桌面并解码；未找到时由调用方决定是否回退到框选。"""

        return self.decode(self.capture_screen())

    def scan_region(
        self,
        bbox: tuple[int, int, int, int],
        logical_screen: tuple[int, int, int, int],
    ) -> Any:
        """截图指定逻辑屏幕区域，转换 DPI 坐标后解码二维码。"""

        return self.decode(self.capture_region(bbox, logical_screen))
