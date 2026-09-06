"""注重隐私的本地滚动日志配置。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from infrastructure.paths import application_data_directory

LOG_FILE_NAME = "authenticator.log"
LOG_MAX_BYTES = 512 * 1024
LOG_BACKUP_COUNT = 2


def configure_logging(directory: Path | None = None) -> Path:
    """配置小容量滚动日志并返回日志路径。

    调用方不得记录账号、OTP 密钥或 API 令牌。重复调用会复用已有相同文件处理器，
    以兼容测试和两个启动入口。
    """

    log_directory = directory or application_data_directory()
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / LOG_FILE_NAME
    root_logger = logging.getLogger()
    # 避免兼容入口或测试重复注册同一个日志文件处理器。
    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path:
            return log_path

    handler = RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    return log_path
