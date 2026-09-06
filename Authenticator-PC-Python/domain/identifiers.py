"""账号唯一性、服务商名称和分组标识的纯函数。

这里不依赖 Tkinter、文件系统或 HTTP，因此 UI、导入、API 与测试可共享同一套
去重规则。函数返回的字符串/列表均可安全用于比较，不负责持久化。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Protocol

DEFAULT_GROUP_ID = "default"


class AccountLike(Protocol):
    """账号去重所需的最小结构协议，``OTPEntry`` 天然满足该协议。"""

    issuer: str
    account: str
    secret: str
    otp_type: str


def clean_secret(secret: str) -> str:
    """移除密钥中的空白和连字符，返回用于存储、解码和去重的字符串。"""

    return re.sub(r"[\s-]+", "", secret or "").strip()


def normalise_issuer_name(value: Any) -> str:
    """压缩服务商空白并移除成对的中英文引号；非字符串统一视为空值。"""

    if not isinstance(value, str):
        return ""
    issuer = " ".join(value.split())
    quote_pairs = (("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’"))
    while len(issuer) >= 2 and any(
        issuer.startswith(left) and issuer.endswith(right) for left, right in quote_pairs
    ):
        issuer = issuer[1:-1].strip()
    return issuer


def account_identity(entry: AccountLike) -> tuple[str, str, str, str]:
    """返回 ``(服务商, 账号, 密钥, 类型)`` 的标准化去重键。"""

    return (
        normalise_issuer_name(entry.issuer).casefold(),
        str(entry.account or "").strip().casefold(),
        clean_secret(entry.secret).upper(),
        str(entry.otp_type or "").strip().lower(),
    )


def unique_issuer_names(entries: Iterable[AccountLike]) -> list[str]:
    """按稳定、不区分大小写的顺序返回不重复且非空的服务商名称。"""

    issuers: dict[str, str] = {}
    for entry in entries:
        issuer = normalise_issuer_name(entry.issuer)
        if issuer and issuer.casefold() not in issuers:
            issuers[issuer.casefold()] = issuer
    return sorted(issuers.values(), key=lambda value: (value.casefold(), value))


def normalise_group_ids(value: Any) -> list[str]:
    """返回去重的分组标识，并保证默认分组只出现一次且位于第一个位置。"""

    if isinstance(value, str):
        raw_values: list[Any] = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []

    group_ids: list[str] = []
    for raw_value in raw_values:
        group_id = str(raw_value or "").strip()
        if not group_id or len(group_id) > 128 or group_id in group_ids:
            continue
        group_ids.append(group_id)
    # 默认分组是所有账号的不可移除归属，先移除旧位置再插入首位。
    if DEFAULT_GROUP_ID in group_ids:
        group_ids.remove(DEFAULT_GROUP_ID)
    group_ids.insert(0, DEFAULT_GROUP_ID)
    return group_ids
