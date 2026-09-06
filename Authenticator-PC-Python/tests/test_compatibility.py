"""验证旧启动模块继续无行为差异地转发到稳定入口。"""

import authenticator_desktop as compatibility
from app import main


def test_legacy_module_forwards_to_stable_entry_point():
    """旧模块导出的 ``main`` 必须是稳定入口本身，而非复制实现。"""

    assert compatibility.main is main
