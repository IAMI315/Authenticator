"""兼容旧脚本和快捷方式的启动器；所有实际启动逻辑都委托给 ``app.main``。"""

from __future__ import annotations

from app import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
