"""可安全传递到应用层和 UI/API 边界的基础设施异常。"""


class PersistenceError(RuntimeError):
    """本地文件或持久化失败的基类。"""


class VaultError(PersistenceError):
    """保险库或设置无法安全读取、解锁或保存时抛出。"""
