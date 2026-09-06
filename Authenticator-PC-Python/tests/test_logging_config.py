"""验证本地滚动日志配置的幂等性和实际写入能力。"""

import logging
from logging.handlers import RotatingFileHandler

from infrastructure.logging_config import configure_logging


def test_logging_configuration_is_idempotent_and_writes_locally(tmp_path):
    """重复配置同一日志文件不能叠加处理器，且 INFO 文本必须实际落盘。"""

    path = configure_logging(tmp_path)
    assert configure_logging(tmp_path) == path
    matching_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(path)
    ]
    assert len(matching_handlers) == 1
    logging.getLogger("test").info("lifecycle-only message")
    matching_handlers[0].flush()
    assert "lifecycle-only message" in path.read_text(encoding="utf-8")
    logging.getLogger().removeHandler(matching_handlers[0])
    matching_handlers[0].close()
