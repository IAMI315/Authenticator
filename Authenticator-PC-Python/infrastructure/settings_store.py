"""JSON 设置存储：窗口、置顶、自动锁定、API 令牌和轻量窗口状态。"""

from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

from domain.identifiers import normalise_issuer_name
from domain.validators import integer_value
from infrastructure.errors import VaultError

# 该处尺寸约束同时保护旧设置文件和窗口初始化，避免异常几何字符串传给 Tk。
DEFAULT_WINDOW_SIZE = "960x640"
MIN_WINDOW_WIDTH = 860
MIN_WINDOW_HEIGHT = 520
SECURE_SETTING_KEYS = frozenset({"api_token", "compact_clipboard", "last_issuer"})
OTP_SORT_FIELDS = frozenset({"service", "account", "type", "created"})
PASSWORD_SORT_FIELDS = frozenset({"name", "username", "url", "created"})
SORT_DIRECTIONS = frozenset({"ascending", "descending"})


def _allowed_value(value: Any, allowed: frozenset[str], default: str) -> str:
    candidate = str(value or "")
    return candidate if candidate in allowed else default


def normalise_window_size(value: Any) -> str:
    """校验 ``宽x高`` 形式的设置值，超出应用可用范围时返回默认尺寸。"""

    match = re.fullmatch(r"(\d{3,4})x(\d{3,4})", str(value or ""))
    if not match:
        return DEFAULT_WINDOW_SIZE
    width, height = (int(part) for part in match.groups())
    if not MIN_WINDOW_WIDTH <= width <= 3_840 or not MIN_WINDOW_HEIGHT <= height <= 2_160:
        return DEFAULT_WINDOW_SIZE
    return f"{width}x{height}"


class SettingsStore:
    """应用设置的内存表示和原子 JSON 读写实现。

    ``values`` 保持可扩展的 JSON 字典；属性访问器负责将外部输入转为稳定类型，
    因此 UI 不需要直接依赖键名或做重复范围校验。
    """

    def __init__(self, path: Path) -> None:
        """创建默认设置状态；构造过程不访问磁盘。"""

        self.path = path
        self.values: dict[str, Any] = self._default_values()
        self.secure_dirty = False

    @staticmethod
    def _default_values() -> dict[str, Any]:
        """返回全新的默认设置字典，防止加载失败后复用可变状态。"""

        return {
            "autolock_minutes": 0,
            "always_on_top": False,
            "window_size": DEFAULT_WINDOW_SIZE,
            "last_issuer": "",
            "compact_mode": False,
            "compact_clipboard": "",
            "otp_sort_field": "created",
            "otp_sort_direction": "descending",
            "password_sort_field": "created",
            "password_sort_direction": "descending",
            "otp_show_pinned": True,
            "password_show_pinned": True,
        }

    def load(self) -> None:
        """读取设置；文件不存在或损坏时静默恢复默认值，不阻止主程序启动。"""

        self.values = self._default_values()
        self.secure_dirty = False
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.values["autolock_minutes"] = integer_value(
                    data.get("autolock_minutes"), 0, 0, 1_440
                )
                self.values["always_on_top"] = data.get("always_on_top") is True
                self.values["window_size"] = normalise_window_size(data.get("window_size"))
                self.values["last_issuer"] = normalise_issuer_name(data.get("last_issuer"))
                self.values["compact_mode"] = data.get("compact_mode") is True
                self.values["otp_sort_field"] = _allowed_value(
                    data.get("otp_sort_field"), OTP_SORT_FIELDS, "created"
                )
                self.values["otp_sort_direction"] = _allowed_value(
                    data.get("otp_sort_direction"), SORT_DIRECTIONS, "descending"
                )
                self.values["password_sort_field"] = _allowed_value(
                    data.get("password_sort_field"), PASSWORD_SORT_FIELDS, "created"
                )
                self.values["password_sort_direction"] = _allowed_value(
                    data.get("password_sort_direction"), SORT_DIRECTIONS, "descending"
                )
                self.values["otp_show_pinned"] = data.get("otp_show_pinned", True) is not False
                self.values["password_show_pinned"] = data.get("password_show_pinned", True) is not False
                compact_clipboard = data.get("compact_clipboard", "")
                if isinstance(compact_clipboard, str):
                    self.values["compact_clipboard"] = compact_clipboard
                stored_api_token = data.get("api_token")
                if isinstance(stored_api_token, str) and len(stored_api_token.strip()) >= 32:
                    self.values["api_token"] = stored_api_token.strip()
                self.secure_dirty = any(key in data for key in SECURE_SETTING_KEYS)
        except (OSError, json.JSONDecodeError):
            # 设置不是账号数据，损坏时宁可重置也不能阻止用户打开保险库。
            self.values = self._default_values()
            self.secure_dirty = False

    @property
    def autolock_minutes(self) -> int:
        """自动锁定分钟数，范围为 0 到 1440。"""

        return integer_value(self.values.get("autolock_minutes"), 0, 0, 1_440)

    @autolock_minutes.setter
    def autolock_minutes(self, minutes: int) -> None:
        """写入经过范围限制的自动锁定分钟数。"""

        self.values["autolock_minutes"] = integer_value(minutes, 0, 0, 1_440)

    @property
    def always_on_top(self) -> bool:
        """返回完整/轻量窗口共享的置顶开关。"""

        return self.values.get("always_on_top") is True

    @always_on_top.setter
    def always_on_top(self, enabled: bool) -> None:
        """保存布尔化后的置顶开关。"""

        self.values["always_on_top"] = bool(enabled)

    @property
    def window_size(self) -> str:
        """返回已校验的完整窗口尺寸。"""

        return normalise_window_size(self.values.get("window_size"))

    @window_size.setter
    def window_size(self, size: str) -> None:
        """保存已校验的完整窗口尺寸。"""

        self.values["window_size"] = normalise_window_size(size)

    @property
    def last_issuer(self) -> str:
        """返回上一次使用的服务商名称（已去引号、压缩空白）。"""

        return normalise_issuer_name(self.values.get("last_issuer"))

    @last_issuer.setter
    def last_issuer(self, issuer: str) -> None:
        """保存规范化后的服务商名称。"""

        self.values["last_issuer"] = normalise_issuer_name(issuer)
        self.secure_dirty = True

    @property
    def compact_mode(self) -> bool:
        """返回下次启动时是否恢复轻量悬浮窗。"""

        return self.values.get("compact_mode") is True

    @compact_mode.setter
    def compact_mode(self, enabled: bool) -> None:
        """保存轻量模式开关。"""

        self.values["compact_mode"] = bool(enabled)

    @property
    def otp_sort_field(self) -> str:
        return _allowed_value(self.values.get("otp_sort_field"), OTP_SORT_FIELDS, "created")

    @otp_sort_field.setter
    def otp_sort_field(self, value: str) -> None:
        self.values["otp_sort_field"] = _allowed_value(value, OTP_SORT_FIELDS, "created")

    @property
    def otp_sort_direction(self) -> str:
        return _allowed_value(
            self.values.get("otp_sort_direction"), SORT_DIRECTIONS, "descending"
        )

    @otp_sort_direction.setter
    def otp_sort_direction(self, value: str) -> None:
        self.values["otp_sort_direction"] = _allowed_value(
            value, SORT_DIRECTIONS, "descending"
        )

    @property
    def password_sort_field(self) -> str:
        return _allowed_value(
            self.values.get("password_sort_field"), PASSWORD_SORT_FIELDS, "created"
        )

    @password_sort_field.setter
    def password_sort_field(self, value: str) -> None:
        self.values["password_sort_field"] = _allowed_value(
            value, PASSWORD_SORT_FIELDS, "created"
        )

    @property
    def password_sort_direction(self) -> str:
        return _allowed_value(
            self.values.get("password_sort_direction"), SORT_DIRECTIONS, "descending"
        )

    @password_sort_direction.setter
    def password_sort_direction(self, value: str) -> None:
        self.values["password_sort_direction"] = _allowed_value(
            value, SORT_DIRECTIONS, "descending"
        )

    @property
    def otp_show_pinned(self) -> bool:
        return self.values.get("otp_show_pinned") is not False

    @otp_show_pinned.setter
    def otp_show_pinned(self, enabled: bool) -> None:
        self.values["otp_show_pinned"] = bool(enabled)

    @property
    def password_show_pinned(self) -> bool:
        return self.values.get("password_show_pinned") is not False

    @password_show_pinned.setter
    def password_show_pinned(self, enabled: bool) -> None:
        self.values["password_show_pinned"] = bool(enabled)

    @property
    def compact_clipboard(self) -> str:
        """返回轻量窗口的用户常驻剪贴板文本。"""

        value = self.values.get("compact_clipboard", "")
        return value if isinstance(value, str) else ""

    @compact_clipboard.setter
    def compact_clipboard(self, value: str) -> None:
        """保存剪贴板文本；非字符串输入会显式转为字符串。"""

        self.values["compact_clipboard"] = value if isinstance(value, str) else str(value)
        self.secure_dirty = True

    @property
    def api_token(self) -> str:
        """返回本机 API 令牌；缺失或过短时生成新的高熵令牌。"""

        token = self.values.get("api_token")
        if not isinstance(token, str) or len(token.strip()) < 32:
            token = secrets.token_urlsafe(32)
            self.values["api_token"] = token
            self.secure_dirty = True
        return token

    def secure_values(self) -> dict[str, str]:
        """返回应进入加密保险库的设置，不包含普通窗口偏好。"""

        return {
            "api_token": self.api_token,
            "compact_clipboard": self.compact_clipboard,
            "last_issuer": self.last_issuer,
        }

    def apply_secure_values(self, values: dict[str, Any]) -> None:
        """用已解密设置覆盖内存值，并清除敏感设置脏标记。"""

        api_token = values.get("api_token")
        if isinstance(api_token, str) and len(api_token.strip()) >= 32:
            self.values["api_token"] = api_token.strip()
        else:
            self.values.pop("api_token", None)
        clipboard = values.get("compact_clipboard")
        self.values["compact_clipboard"] = clipboard if isinstance(clipboard, str) else ""
        self.values["last_issuer"] = normalise_issuer_name(values.get("last_issuer"))
        self.secure_dirty = False

    def save(self) -> None:
        """以临时文件和原子替换持久化设置；失败时抛出 ``VaultError``。"""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                public_values = {
                    key: value for key, value in self.values.items() if key not in SECURE_SETTING_KEYS
                }
                json.dump(public_values, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            raise VaultError("无法保存设置") from error
