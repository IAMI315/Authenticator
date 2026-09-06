"""UI、导入和 API 适配器之间可共享的不可变命令值对象。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountQuery:
    """账号列表查询条件：搜索文本和可选的活动分组 ID。"""

    text: str = ""
    group_id: str | None = None


@dataclass(frozen=True)
class GroupAssignment:
    """批量分组命令：目标账号 ID 元组和应保留的分组 ID 元组。"""

    account_ids: tuple[str, ...]
    group_ids: tuple[str, ...]
