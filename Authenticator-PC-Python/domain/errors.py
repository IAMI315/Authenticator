"""领域层异常；不依赖 Tkinter、文件存储或 HTTP。"""

from __future__ import annotations


class DomainError(ValueError):
    """所有领域规则违反的基类，调用方可统一转成用户提示或 API 错误。"""


class DuplicateAccountError(DomainError):
    """账号标准化去重键已存在时抛出。"""


class AccountNotFoundError(DomainError):
    """按账号标识查找失败时抛出。"""


class GroupNotFoundError(DomainError):
    """按分组标识查找失败时抛出。"""


class DuplicatePasswordError(DomainError):
    """密码记录的标准化唯一键已存在时抛出。"""


class PasswordNotFoundError(DomainError):
    """按密码记录标识查找失败时抛出。"""


class PasswordGroupNotFoundError(DomainError):
    """按密码分组标识查找失败时抛出。"""
