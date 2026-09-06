"""账号搜索与稳定排序规则。

该模块在 UI 与 API 之间共享，因此排序、置顶和模糊匹配不依赖 Treeview 等界面控件。
"""

from __future__ import annotations

from collections.abc import Iterable

from application.sorting import OtpSortSpec, sort_otp_entries
from domain.entities import OTPEntry
from domain.validators import created_at_timestamp


def normalise_search_text(value: str) -> str:
    """压缩空白并大小写无关化用户搜索文本。"""

    return " ".join((value or "").casefold().split())


def filter_entries(
    entries: list[OTPEntry], query: str, sort_spec: OtpSortSpec | None = None
) -> list[OTPEntry]:
    """按所有搜索词筛选账号，并按相关度、置顶、创建时间和文本稳定排序。"""

    normalised_query = normalise_search_text(query)
    terms = tuple(normalised_query.split())

    def account_text(entry: OTPEntry) -> str:
        """返回账号名称的搜索规范化文本。"""

        return normalise_search_text(entry.account)

    def service_text(entry: OTPEntry) -> str:
        """返回服务商名称的搜索规范化文本。"""

        return normalise_search_text(entry.issuer)

    def searchable_text(entry: OTPEntry) -> str:
        """拼接可参与全文匹配的账号、服务、类型显示和值。"""

        return " ".join((service_text(entry), account_text(entry), normalise_search_text(entry.type_label), normalise_search_text(entry.otp_type)))

    # 空查询仍需要确定性排序，置顶账号优先、其余账号按创建时间倒序。
    if not terms and sort_spec is None:
        return sorted(entries, key=lambda entry: (not entry.pinned, -created_at_timestamp(entry.created_at), account_text(entry), service_text(entry)))
    matched = [entry for entry in entries if all(term in searchable_text(entry) for term in terms)]

    if sort_spec is not None:
        return sort_otp_entries(matched if terms else entries, sort_spec)

    def relevance(entry: OTPEntry) -> int:
        """返回越小越优先的匹配等级，账号字段优先于服务商字段。"""

        account = account_text(entry)
        service = service_text(entry)
        if account == normalised_query:
            return 0
        if account.startswith(normalised_query):
            return 1
        if all(term in account for term in terms):
            return 2
        if service == normalised_query:
            return 3
        if service.startswith(normalised_query):
            return 4
        if all(term in service for term in terms):
            return 5
        return 6

    return sorted(
        matched,
        key=lambda entry: (
            relevance(entry), not entry.pinned, -created_at_timestamp(entry.created_at),
            account_text(entry), service_text(entry),
        ),
    )


class SearchService:
    """为调用方提供面向迭代器的搜索门面，内部统一转换为列表排序。"""

    def search(
        self,
        entries: Iterable[OTPEntry],
        query: str = "",
        sort_spec: OtpSortSpec | None = None,
    ) -> list[OTPEntry]:
        """返回符合 ``query`` 的排序账号列表，不修改输入集合。"""

        return filter_entries(list(entries), query, sort_spec)
