"""安全数据存储的应用生命周期服务。"""

from __future__ import annotations

from typing import Any

from infrastructure.errors import VaultError
from infrastructure.secure_storage import StorageLoadResult
from infrastructure.vault_repository import SecureDataRepository


class StorageService:
    """协调安全仓储的加载、初始化、锁定、恢复和主密码变更。"""

    def __init__(self, vault: Any, repository: SecureDataRepository) -> None:
        self.vault = vault
        self.repository = repository

    def load(self) -> StorageLoadResult:
        return self.repository.load(self.vault)

    def initialize(self, passphrase: str) -> None:
        self.repository.initialize(self.vault, passphrase)

    def unlock(self, passphrase: str) -> None:
        self.repository.unlock(self.vault, passphrase)

    def lock(self) -> None:
        self.repository.lock(self.vault)

    def change_master_password(self, current: str, new: str) -> None:
        self.repository.change_master_password(self.vault, current, new)

    def set_passphrase(self, passphrase: str | None) -> None:
        """兼容旧调用；强制加密版本不允许移除主密码。"""

        if passphrase is None:
            raise VaultError("本地安全数据必须保持加密")
        self.initialize(passphrase)
