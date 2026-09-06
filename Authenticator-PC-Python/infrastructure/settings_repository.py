"""应用设置持久化端口及 JSON 设置实现适配器。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol


class SettingsRepository(Protocol):
    """隔离应用层与具体设置文件格式的最小协议。"""

    def create(self) -> Any:
        """创建带默认值、尚未读取磁盘的设置对象。"""

        ...

    def load(self, settings: Any) -> None:
        """从持久化介质填充设置对象。"""

        ...

    def save(self, settings: Any) -> None:
        """把当前设置对象持久化。"""

        ...


class JsonSettingsRepository:
    """把 ``SettingsStore`` 包装为仓储接口，便于替换和测试。"""

    def __init__(self, path: Path, settings_factory: Callable[[Path], Any]) -> None:
        """记录设置文件路径和可替换的设置对象工厂。"""

        self.path = path
        self._settings_factory = settings_factory

    def create(self) -> Any:
        """创建默认设置对象，尚未读取磁盘。"""

        return self._settings_factory(self.path)

    def load(self, settings: Any) -> None:
        """委托读取设置文件。"""

        settings.load()

    def save(self, settings: Any) -> None:
        """委托原子保存设置。"""

        settings.save()
