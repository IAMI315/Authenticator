"""主窗口 mixin 的静态类型支撑。

运行时 ``WindowMixin`` 不提供行为；类型检查时通过 ``__getattr__`` 告诉 Mypy，
各 mixin 的属性和方法最终由 ``MainWindow`` 组合提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    class WindowMixin:
        """仅供类型检查的动态主窗口基类，不应在此处添加业务逻辑。"""

        def __getattr__(self, name: str) -> Any:
            """允许类型检查器把组合根提供的未知属性视为动态可用。"""

            ...
else:
    class WindowMixin:
        """运行时空标记基类，用于让多个控制器 mixin 共享一个父类。"""

        pass
