"""保险库持久化端口及 JSON 实现适配器。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from infrastructure.errors import VaultError
from infrastructure.key_protection import DeviceKeyProtector
from infrastructure.secure_storage import EncryptedDataStore, StorageLoadResult


class SecureDataRepository(Protocol):
    """应用层依赖的保险库操作协议，隔离具体 JSON/加密实现。"""

    def create(self) -> Any:
        """创建尚未加载的保险库对象。"""

        ...

    def load(self, vault: Any) -> StorageLoadResult:
        """读取对象状态，并返回明确的设置/解锁状态。"""

        ...

    def save(self, vault: Any) -> None:
        """持久化当前保险库状态。"""

        ...

    def lock(self, vault: Any) -> None:
        """清除已解锁的内存数据和密钥。"""

        ...

    def unlock(self, vault: Any, passphrase: str) -> None:
        """用密码填充已加密保险库的内存状态。"""

        ...

    def set_passphrase(self, vault: Any, passphrase: str | None) -> None:
        """设置、修改或移除保险库密码。"""

        ...

    def initialize(self, vault: Any, passphrase: str) -> None: ...

    def change_master_password(self, vault: Any, current: str, new: str) -> None: ...


class VaultRepository(SecureDataRepository, Protocol):
    """旧协议名称兼容入口。"""


class JsonVaultRepository:
    """将当前 ``Vault`` 类适配为明确的仓储 API。"""

    def __init__(
        self,
        path: Path,
        vault_factory: Callable[[Path], Any],
        protector: DeviceKeyProtector | None = None,
    ) -> None:
        """记录保险库路径和工厂，以便测试可注入替身实现。"""

        self.path = path
        self._vault_factory = vault_factory
        if protector is None:
            from infrastructure.device_key import WindowsDpapiKeyProtector

            protector = WindowsDpapiKeyProtector()
        self.store = EncryptedDataStore(
            path,
            path.with_name("device.key"),
            protector,
        )

    def create(self) -> Any:
        """创建尚未加载的新保险库对象。"""

        return self._vault_factory(self.path)

    def load(self, vault: Any) -> StorageLoadResult:
        """加载强制加密存储，并尝试使用本机凭据自动解锁。"""

        return self.store.load(vault)

    def save(self, vault: Any) -> None:
        """委托保存当前内存状态。"""

        self.store.save(vault)

    def lock(self, vault: Any) -> None:
        """委托锁定，不让应用层了解底层字段。"""

        self.store.lock(vault)

    def unlock(self, vault: Any, passphrase: str) -> None:
        """委托密码解锁。"""

        self.store.unlock(vault, passphrase)

    def set_passphrase(self, vault: Any, passphrase: str | None) -> None:
        """委托密码设置或移除操作。"""

        if passphrase is None:
            raise VaultError("本地安全数据必须保持加密")
        self.store.initialize(vault, passphrase)

    def initialize(self, vault: Any, passphrase: str) -> None:
        self.store.initialize(vault, passphrase)

    def change_master_password(self, vault: Any, current: str, new: str) -> None:
        self.store.change_master_password(vault, current, new)
