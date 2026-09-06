"""源码运行和 PyInstaller 打包共用的稳定应用入口。"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from infrastructure.logging_config import configure_logging
from tests.packaged_self_test import run_self_test

__all__ = ["main", "run_self_test"]


def main(argv: Sequence[str] | None = None) -> int:
    """启动自检或 Tk 主窗口，并以进程退出码形式返回结果。

    ``argv`` 为可测试的可选参数序列；省略时使用命令行参数。``--self-test`` 不会
    创建窗口，适合打包后的自动冒烟检查。
    """

    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in arguments:
        run_self_test()
        return 0

    # DPI awareness must be configured before importing Tkinter or creating an
    # HWND. Keeping the UI import local also preserves the headless self-test.
    from presentation.dpi import DpiContext, configure_process_dpi_awareness

    dpi_mode = configure_process_dpi_awareness()
    from presentation.main_window import MainWindow

    # 正常启动只在此处安装日志，避免领域/应用层接触全局日志配置。
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Application starting")
    try:
        application = MainWindow(dpi_context=DpiContext(mode=dpi_mode))
        application.mainloop()
    except Exception:
        logger.exception("Application terminated unexpectedly")
        raise
    logger.info("Application stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
