"""不导入 Tkinter 的展示状态、列表行模型和验证码缓存。"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from application.password_service import PasswordService
from application.search_service import SearchService
from application.sorting import (
    DEFAULT_OTP_SORT,
    DEFAULT_PASSWORD_SORT,
    OtpSortSpec,
    PasswordSortSpec,
)
from domain.entities import DEFAULT_GROUP_ID, AccountGroup, OTPEntry
from domain.passwords import (
    MASKED_PASSWORD,
    PASSWORD_DEFAULT_GROUP_ID,
    PasswordEntry,
    PasswordGroup,
)
from domain.validators import format_created_at


class VaultView(Protocol):
    """视图模型读取保险库所需的最小只读结构。"""

    entries: list[OTPEntry]
    groups: list[AccountGroup]

    def group_by_id(self, group_id: str) -> AccountGroup | None:
        """按 ID 返回分组；视图模型用 ``None`` 表示已删除的活动分组。"""

        ...


# 缓存键随会影响验证码的字段改变而失效；值同时保存显示文本和密钥是否无效。
CodeSignature: TypeAlias = tuple[str, str, str, int, int, int, str]
CodeCacheValue: TypeAlias = tuple[CodeSignature, str, bool]
CodeCache: TypeAlias = dict[str, CodeCacheValue]
CompactContentSignature: TypeAlias = tuple[object, ...]


def _provider_key(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


@dataclass(frozen=True)
class AllScope:
    label: str


@dataclass(frozen=True)
class FavoriteScope:
    label: str = "收藏夹"


@dataclass(frozen=True)
class GroupScope:
    group_id: str
    label: str


@dataclass(frozen=True)
class ProviderScope:
    provider_key: str
    label: str


@dataclass(frozen=True)
class OtherProvidersScope:
    excluded_keys: tuple[str, ...]
    label: str


NavigationScope: TypeAlias = AllScope | FavoriteScope | GroupScope | ProviderScope | OtherProvidersScope


@dataclass(frozen=True)
class NavigationItem:
    id: str
    label: str
    count: int
    icon_key: str
    section: str
    scope: NavigationScope


@dataclass(frozen=True)
class OtpDashboardStats:
    total: int
    valid: int
    expiring: int
    mode_title: str
    mode_detail: str
    locked: bool = False


@dataclass(frozen=True)
class PasswordDashboardStats:
    total: int
    pinned: int
    with_url: int
    custom_groups: int
    locked: bool = False


@dataclass(frozen=True)
class GroupChoice:
    """分组下拉框的一项：可见标签和内部可选分组 ID。"""

    label: str
    group_id: str | None


class MainViewModel:
    """将保险库读取状态转换为完整界面需要的分组、列表和提示文本。"""

    def __init__(self, vault: VaultView, search_service: SearchService, all_accounts_label: str) -> None:
        """注入只读保险库协议、排序服务和“全部账号”显示文本。"""

        self.vault = vault
        self.search_service = search_service
        self.all_accounts_label = all_accounts_label
        self.query = ""
        self.active_group_id: str | None = None
        self.scope: NavigationScope = AllScope(all_accounts_label)
        self.locked = False
        self.sort_spec = DEFAULT_OTP_SORT
        self.show_pinned = True

    def update_state(
        self,
        *,
        query: str | None = None,
        active_group_id: str | None = None,
        locked: bool | None = None,
        scope: NavigationScope | None = None,
    ) -> None:
        """同步 UI 查询、活动分组和锁定状态。

        ``active_group_id`` 即使为 ``None`` 也表示调用方要切换回全部账号，因此不能
        用“参数是否为 None”判断是否更新它。
        """

        if query is not None:
            self.query = query
        if scope is not None:
            self.set_scope(scope)
        else:
            group = self.vault.group_by_id(active_group_id) if active_group_id else None
            self.set_scope(
                GroupScope(group.id, group.name)
                if group is not None
                else AllScope(self.all_accounts_label)
            )
        if locked is not None:
            self.locked = locked

    def set_scope(self, scope: NavigationScope) -> None:
        self.scope = scope
        self.active_group_id = scope.group_id if isinstance(scope, GroupScope) else None

    def set_sort(self, sort_spec: OtpSortSpec) -> None:
        self.sort_spec = sort_spec

    def set_show_pinned(self, show_pinned: bool) -> None:
        self.show_pinned = bool(show_pinned)

    def group_choices(self) -> list[GroupChoice]:
        """返回“全部账号”加当前保险库分组的下拉选项。"""

        return [GroupChoice(self.all_accounts_label, None), *[
            GroupChoice(group.name, group.id) for group in self.vault.groups
        ]]

    def active_group_name(self) -> str:
        """返回活动分组显示名；分组已删除时安全回退为“全部账号”。"""

        if self.active_group_id is None:
            return self.all_accounts_label
        group = self.vault.group_by_id(self.active_group_id)
        return group.name if group is not None else self.all_accounts_label

    def navigation_items(self, provider_limit: int = 6) -> list[NavigationItem]:
        entries = self.vault.entries
        items = [
            NavigationItem("all", self.all_accounts_label, len(entries), "folder", "main", AllScope(self.all_accounts_label)),
            NavigationItem(
                "favorites", "收藏夹", sum(entry.favorite for entry in entries), "star", "main", FavoriteScope()
            ),
        ]
        for group in self.vault.groups:
            if group.id == DEFAULT_GROUP_ID:
                continue
            items.append(
                NavigationItem(
                    f"group:{group.id}",
                    group.name,
                    sum(group.id in entry.group_ids for entry in entries),
                    "folder",
                    "groups",
                    GroupScope(group.id, group.name),
                )
            )
        counts = Counter(_provider_key(entry.title) for entry in entries if _provider_key(entry.title))
        labels: dict[str, str] = {}
        for entry in entries:
            key = _provider_key(entry.title)
            if key and key not in labels:
                labels[key] = entry.title
        top_keys = tuple(
            key for key, _count in sorted(counts.items(), key=lambda item: (-item[1], labels[item[0]].casefold()))[:provider_limit]
        )
        for key in top_keys:
            items.append(
                NavigationItem(
                    f"provider:{key}", labels[key], counts[key], key, "providers", ProviderScope(key, labels[key])
                )
            )
        other_count = sum(1 for entry in entries if _provider_key(entry.title) not in top_keys)
        if other_count:
            items.append(
                NavigationItem(
                    "providers:other",
                    "其他服务商",
                    other_count,
                    "grid",
                    "providers",
                    OtherProvidersScope(top_keys, "其他服务商"),
                )
            )
        return items

    def visible_entries(self, sort_spec: OtpSortSpec | None = None) -> list[OTPEntry]:
        """先按活动分组筛选，再委托搜索服务进行全文匹配和排序。"""

        entries: Iterable[OTPEntry] = self.vault.entries
        if isinstance(self.scope, FavoriteScope):
            entries = (entry for entry in entries if entry.favorite)
        elif isinstance(self.scope, GroupScope):
            entries = (entry for entry in entries if self.scope.group_id in entry.group_ids)
        elif isinstance(self.scope, ProviderScope):
            entries = (entry for entry in entries if _provider_key(entry.title) == self.scope.provider_key)
        elif isinstance(self.scope, OtherProvidersScope):
            entries = (entry for entry in entries if _provider_key(entry.title) not in self.scope.excluded_keys)
        if not self.show_pinned:
            entries = (entry for entry in entries if not entry.pinned)
        return self.search_service.search(entries, self.query, sort_spec or self.sort_spec)

    def result_summary(self, visible_count: int | None = None) -> str:
        """生成完整界面顶部的数量/筛选范围说明。"""

        if self.locked:
            return "保险库已锁定"
        count = len(self.visible_entries()) if visible_count is None else visible_count
        total = len(self.vault.entries)
        scope_name = self.scope.label
        if self.query.strip():
            scope = f"{scope_name}内" if not isinstance(self.scope, AllScope) else ""
            return f"{scope}匹配 {count}/{total} 个账号"
        if not isinstance(self.scope, AllScope):
            return f"{scope_name} · {count} 个账号"
        return f"{total} 个账号"

    def dashboard_stats(self, now: float | None = None) -> OtpDashboardStats:
        if self.locked:
            return OtpDashboardStats(0, 0, 0, "已锁定", "解锁后查看", True)
        current_time = time.time() if now is None else now
        valid = 0
        expiring = 0
        type_counts: Counter[str] = Counter()
        for entry in self.vault.entries:
            type_counts[entry.otp_type.upper()] += 1
            code_valid = False
            try:
                entry.code(current_time)
                valid += 1
                code_valid = True
            except ValueError:
                pass
            remaining = entry.remaining_seconds(current_time)
            if code_valid and remaining is not None and remaining <= 10:
                expiring += 1
        if not type_counts:
            mode_title, mode_detail = "暂无", "尚无验证码"
        elif len(type_counts) == 1:
            mode_title = next(iter(type_counts))
            mode_detail = "当前验证码类型"
        else:
            ordered = type_counts.most_common()
            mode_title = f"{len(ordered)} 种类型"
            mode_detail = " · ".join(f"{name} {count}" for name, count in ordered[:2])
        return OtpDashboardStats(len(self.vault.entries), valid, expiring, mode_title, mode_detail)

    def security_summary(self, encrypted: bool, autolock_minutes: int) -> str:
        """生成保险库加密和自动锁定状态的用户可见摘要。"""

        if self.locked:
            return "保险库已锁定"
        if not encrypted:
            return "本地安全数据：等待加密"
        summary = "已加密并自动解锁"
        if autolock_minutes:
            summary += f" | 自动锁定 {autolock_minutes} 分钟"
        return f"本地保险库：{summary}"


class CompactViewModel:
    """复用完整界面筛选状态，为轻量窗口提供完整账号列表。"""

    def __init__(self, main: MainViewModel, recent_limit: int | None = None) -> None:
        """保存共享主视图模型；保留可选上限以兼容旧调用方。"""

        self.main = main
        self.recent_limit = recent_limit

    def recent_entries(self) -> list[OTPEntry]:
        """锁定时返回空列表，否则返回完整的已筛选排序结果。"""

        if self.main.locked:
            return []
        entries = self.main.visible_entries(DEFAULT_OTP_SORT)
        return entries if self.recent_limit is None else entries[: self.recent_limit]

    def content_signature(self, entries: list[OTPEntry]) -> CompactContentSignature:
        """返回轻量窗口是否需重建行控件的内容签名。"""

        if self.main.locked:
            return ("locked",)
        if not entries:
            return ("empty", bool(self.main.query.strip()))
        return ("rows", tuple((entry.id, entry.title, entry.account) for entry in entries))


@dataclass(frozen=True)
class AccountRow:
    """Canvas data-table row for one OTP account."""

    service: str
    account: str
    code: str
    expires: str
    entry_type: str
    created_at: str
    tags: tuple[str, ...]
    remaining_seconds: int | None
    period: int
    icon_key: str


class AccountRowPresenter:
    """把领域账号转换为稳定表格行，并维护小型验证码缓存。"""

    def __init__(self, code_cache: CodeCache) -> None:
        """接收由主窗口拥有的缓存，使刷新列表不会重复计算相同时间片验证码。"""

        self._code_cache = code_cache

    def row(self, entry: OTPEntry, now: float | None = None) -> AccountRow:
        """构造单个账号的显示行；无效密钥显示错误文本并添加 ``invalid`` 标签。"""

        if now is None:
            now = time.time()
        counter = entry.counter if entry.otp_type == "hotp" else int(now) // entry.period
        # 时间型账号仅在时间片变化时失效；HOTP 则由计数器变化驱动失效。
        signature: CodeSignature = (
            entry.secret,
            entry.secret_encoding,
            entry.otp_type,
            counter,
            entry.period,
            entry.digits,
            entry.algorithm,
        )
        cached_value = self._code_cache.get(entry.id)
        if cached_value and cached_value[0] == signature:
            code, invalid = cached_value[1], cached_value[2]
        else:
            try:
                code, invalid = entry.code(now), False
            except ValueError:
                code, invalid = "密钥无效", True
            self._code_cache[entry.id] = (signature, code, invalid)
        remaining = entry.remaining_seconds(now)
        expires = f"{remaining} 秒" if remaining is not None else f"计数 {entry.counter}"
        tags = tuple(tag for tag in ("pinned" if entry.pinned else "", "invalid" if invalid else "") if tag)
        return AccountRow(
            entry.title,
            entry.account or "-",
            code,
            expires,
            entry.type_label,
            format_created_at(entry.created_at),
            tags,
            remaining,
            entry.period,
            _provider_key(entry.title),
        )


@dataclass(frozen=True)
class PasswordGroupChoice:
    label: str
    group_id: str | None


@dataclass(frozen=True)
class PasswordRow:
    name: str
    username: str
    password: str
    url: str
    created_at: str
    tags: tuple[str, ...]
    icon_key: str


class PasswordVaultView(Protocol):
    password_entries: list[PasswordEntry]
    password_groups: list[PasswordGroup]

    def password_group_by_id(self, group_id: str) -> PasswordGroup | None: ...


class PasswordViewModel:
    """Presentation state for the password workspace without Tk dependencies."""

    def __init__(self, vault: PasswordVaultView, password_service: PasswordService) -> None:
        self.vault = vault
        self.password_service = password_service
        self.query = ""
        self.active_group_id: str | None = None
        self.scope: NavigationScope = AllScope("全部密码")
        self.locked = False
        self.revealed_entry_id: str | None = None
        self.sort_spec = DEFAULT_PASSWORD_SORT
        self.show_pinned = True

    def update_state(
        self,
        *,
        query: str,
        active_group_id: str | None,
        locked: bool,
        scope: NavigationScope | None = None,
    ) -> None:
        self.query = query
        if scope is not None:
            self.set_scope(scope)
        else:
            group = self.vault.password_group_by_id(active_group_id) if active_group_id else None
            self.set_scope(GroupScope(group.id, group.name) if group is not None else AllScope("全部密码"))
        self.locked = locked
        if locked:
            self.revealed_entry_id = None

    def set_scope(self, scope: NavigationScope) -> None:
        self.scope = scope
        self.active_group_id = scope.group_id if isinstance(scope, GroupScope) else None

    def set_sort(self, sort_spec: PasswordSortSpec) -> None:
        self.sort_spec = sort_spec

    def set_show_pinned(self, show_pinned: bool) -> None:
        self.show_pinned = bool(show_pinned)

    def group_choices(self) -> list[PasswordGroupChoice]:
        return [
            PasswordGroupChoice("全部密码", None),
            *[PasswordGroupChoice(group.name, group.id) for group in self.vault.password_groups],
        ]

    def navigation_items(self, provider_limit: int = 6) -> list[NavigationItem]:
        entries = self.vault.password_entries
        items = [
            NavigationItem("all", "全部密码", len(entries), "folder", "main", AllScope("全部密码")),
            NavigationItem(
                "favorites", "收藏夹", sum(entry.favorite for entry in entries), "star", "main", FavoriteScope()
            ),
        ]
        for group in self.vault.password_groups:
            if group.id == PASSWORD_DEFAULT_GROUP_ID:
                continue
            items.append(
                NavigationItem(
                    f"group:{group.id}",
                    group.name,
                    sum(group.id in entry.group_ids for entry in entries),
                    "folder",
                    "groups",
                    GroupScope(group.id, group.name),
                )
            )
        counts = Counter(_provider_key(entry.name) for entry in entries if _provider_key(entry.name))
        labels: dict[str, str] = {}
        for entry in entries:
            key = _provider_key(entry.name)
            if key and key not in labels:
                labels[key] = entry.name
        top_keys = tuple(
            key for key, _count in sorted(counts.items(), key=lambda item: (-item[1], labels[item[0]].casefold()))[:provider_limit]
        )
        for key in top_keys:
            items.append(
                NavigationItem(
                    f"provider:{key}", labels[key], counts[key], key, "providers", ProviderScope(key, labels[key])
                )
            )
        other_count = sum(1 for entry in entries if _provider_key(entry.name) not in top_keys)
        if other_count:
            items.append(
                NavigationItem(
                    "providers:other",
                    "其他服务",
                    other_count,
                    "grid",
                    "providers",
                    OtherProvidersScope(top_keys, "其他服务"),
                )
            )
        return items

    def visible_entries(self) -> list[PasswordEntry]:
        if self.locked:
            return []
        if isinstance(self.scope, GroupScope):
            entries = self.password_service.list(self.query, self.scope.group_id, self.sort_spec)
        else:
            entries = self.password_service.list(self.query, sort_spec=self.sort_spec)
        if isinstance(self.scope, FavoriteScope):
            entries = [entry for entry in entries if entry.favorite]
        elif isinstance(self.scope, ProviderScope):
            entries = [entry for entry in entries if _provider_key(entry.name) == self.scope.provider_key]
        elif isinstance(self.scope, OtherProvidersScope):
            entries = [entry for entry in entries if _provider_key(entry.name) not in self.scope.excluded_keys]
        if not self.show_pinned:
            entries = [entry for entry in entries if not entry.pinned]
        return entries

    def result_summary(self, visible_count: int | None = None) -> str:
        if self.locked:
            return "保险库已锁定"
        count = len(self.visible_entries()) if visible_count is None else visible_count
        total = len(self.vault.password_entries)
        if self.query.strip():
            return f"匹配 {count}/{total} 条密码"
        if not isinstance(self.scope, AllScope):
            return f"{self.scope.label} · {count} 条密码"
        return f"{total} 条密码"

    def dashboard_stats(self) -> PasswordDashboardStats:
        if self.locked:
            return PasswordDashboardStats(0, 0, 0, 0, True)
        entries = self.vault.password_entries
        return PasswordDashboardStats(
            total=len(entries),
            pinned=sum(entry.pinned for entry in entries),
            with_url=sum(bool(entry.url) for entry in entries),
            custom_groups=sum(group.id != PASSWORD_DEFAULT_GROUP_ID for group in self.vault.password_groups),
        )

    def row(self, entry: PasswordEntry) -> PasswordRow:
        password = entry.password if entry.id == self.revealed_entry_id else MASKED_PASSWORD
        return PasswordRow(
            entry.title,
            entry.username,
            password,
            entry.url or "-",
            format_created_at(entry.created_at),
            ("pinned",) if entry.pinned else (),
            _provider_key(entry.name),
        )

    def toggle_reveal(self, entry_id: str | None) -> None:
        self.revealed_entry_id = None if entry_id == self.revealed_entry_id else entry_id

    def conceal(self) -> None:
        self.revealed_entry_id = None
