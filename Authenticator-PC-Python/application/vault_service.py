"""旧服务名称兼容入口；新代码使用 ``StorageService``。"""

from __future__ import annotations

from application.storage_service import StorageService


class VaultService(StorageService):
    """保持现有导入路径可用，不复制实现。"""
