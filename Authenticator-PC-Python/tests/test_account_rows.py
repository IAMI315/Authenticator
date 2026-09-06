"""验证账号行展示器的验证码缓存和置顶样式标签契约。"""

from domain.entities import OTPEntry
from presentation.view_models import AccountRowPresenter


def test_account_row_presenter_caches_code_and_preserves_tags():
    """同一时间片重复取行时复用验证码，并保留置顶标签。"""

    entry = OTPEntry(
        "account-1", "Example", "alice@example.com", "JBSWY3DPEHPK3PXP",
        pinned=True, created_at="2025-01-01T00:00:00Z",
    )
    presenter = AccountRowPresenter({})
    row = presenter.row(entry, now=59)
    assert row.account == "alice@example.com"
    assert row.tags == ("pinned",)
    assert row.code == presenter.row(entry, now=59).code
