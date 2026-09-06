"""便携式应用数据目录与 PyInstaller 打包资源路径解析。"""

from __future__ import annotations

import sys
from pathlib import Path

DATA_DIRECTORY_NAME = "data"


def resource_path(relative_path: str) -> Path:
    """返回源码或 PyInstaller 临时目录中的资源绝对路径。"""

    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base_path / relative_path


def executable_directory() -> Path:
    """返回程序入口所在目录，且不受当前工作目录影响。"""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def application_data_directory() -> Path:
    """返回并创建程序同级的便携式 ``data`` 目录。

    不回退到用户目录。若程序所在目录不可写，创建目录时直接抛出异常，避免数据
    悄然保存到用户无法预期的位置。
    """

    directory = executable_directory() / DATA_DIRECTORY_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory
