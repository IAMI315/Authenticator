"""验证密码变更保存失败时加密内存状态能够恢复。"""

import pytest

from application.vault_service import VaultService


class FakeVault:
    """模拟密码修改时需要恢复的最小加密状态。"""

    encrypted = False
    _envelope = None
    _key = None
    _salt = None
    _iterations = 100



class FakeRepository:
    """模拟强制加密仓储。"""

    def __init__(self):
        self.initialized_with = None
        self.changed_with = None

    def load(self, vault):
        """未使用的加载替身，返回未加密状态。"""

        return False

    def save(self, vault):
        """未使用的保存替身。"""

        return None

    def lock(self, vault):
        """未使用的锁定替身。"""

        return None

    def unlock(self, vault, passphrase):
        """未使用的解锁替身。"""

        return None

    def set_passphrase(self, vault, passphrase):
        return None

    def initialize(self, vault, passphrase):
        self.initialized_with = passphrase

    def change_master_password(self, vault, current, new):
        self.changed_with = (current, new)


def test_vault_service_enforces_encryption_and_delegates_password_changes():
    """服务不得移除加密，并应通过仓储初始化或修改主密码。"""

    vault = FakeVault()
    repository = FakeRepository()
    service = VaultService(vault, repository)
    service.set_passphrase("password")
    service.change_master_password("password", "new-password")
    assert repository.initialized_with == "password"
    assert repository.changed_with == ("password", "new-password")
    with pytest.raises(Exception):
        service.set_passphrase(None)
