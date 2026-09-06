"""验证完整/轻量视图模型共享筛选、分组和锁定状态。"""

from application.search_service import SearchService
from application.sorting import OtpSortField, OtpSortSpec, SortDirection
from domain.entities import AccountGroup, OTPEntry, default_account_group
from presentation.view_models import CompactViewModel, MainViewModel

SECRET = "JBSWY3DPEHPK3PXP"


class FakeVault:
    """视图模型读取分组/账号及分组查找所需的内存替身。"""

    def __init__(self):
        """创建两条不同创建时间且分组不同的账号。"""

        self.groups = [default_account_group(), AccountGroup("work", "工作")]
        self.entries = [
            OTPEntry("new", "GitHub", "new@example.com", SECRET, created_at="2025-02-01T00:00:00Z"),
            OTPEntry("old", "Outlook", "old@example.com", SECRET, created_at="2025-01-01T00:00:00Z", group_ids=["default", "work"]),
        ]

    def group_by_id(self, group_id):
        """按 ID 返回测试分组。"""

        return next((group for group in self.groups if group.id == group_id), None)


def test_main_view_model_filters_groups_and_builds_summary():
    """主视图模型应同时应用分组/文本筛选并生成匹配摘要。"""

    model = MainViewModel(FakeVault(), SearchService(), "全部账号")
    model.update_state(query="outlook", active_group_id="work")
    visible = model.visible_entries()
    assert [entry.id for entry in visible] == ["old"]
    assert model.result_summary(len(visible)) == "工作内匹配 1/2 个账号"
    assert [(choice.label, choice.group_id) for choice in model.group_choices()] == [
        ("全部账号", None), ("默认分组", "default"), ("工作", "work")
    ]


def test_compact_view_model_shares_query_and_lock_state():
    """轻量视图必须复用主视图查询，并在锁定时隐藏所有账号。"""

    main = MainViewModel(FakeVault(), SearchService(), "全部账号")
    compact = CompactViewModel(main)
    main.update_state(query="github", active_group_id=None, locked=False)
    recent = compact.recent_entries()
    assert [entry.id for entry in recent] == ["new"]
    assert compact.content_signature(recent)[0] == "rows"
    main.update_state(query="github", active_group_id=None, locked=True)
    assert compact.recent_entries() == []
    assert compact.content_signature([]) == ("locked",)


def test_full_table_sort_does_not_change_compact_recent_order():
    main = MainViewModel(FakeVault(), SearchService(), "全部账号")
    compact = CompactViewModel(main)
    main.set_sort(OtpSortSpec(OtpSortField.SERVICE, SortDirection.DESCENDING))

    assert [entry.id for entry in main.visible_entries()] == ["old", "new"]
    assert [entry.id for entry in compact.recent_entries()] == ["new", "old"]


def test_compact_view_model_returns_the_complete_account_pool_by_default():
    vault = FakeVault()
    vault.entries.extend(
        [
            OTPEntry("older", "Google", "older@example.com", SECRET, created_at="2024-12-01T00:00:00Z"),
            OTPEntry("oldest", "OpenAI", "oldest@example.com", SECRET, created_at="2024-11-01T00:00:00Z"),
        ]
    )
    main = MainViewModel(vault, SearchService(), "全部账号")

    assert [entry.id for entry in CompactViewModel(main).recent_entries()] == [
        "new",
        "old",
        "older",
        "oldest",
    ]
    assert [entry.id for entry in CompactViewModel(main, recent_limit=2).recent_entries()] == [
        "new",
        "old",
    ]
