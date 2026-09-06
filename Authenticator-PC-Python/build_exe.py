"""构建 Authenticator Desktop 独立 Windows EXE 的发布脚本。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

# 构建产物固定放在项目内；脚本会写入这两个目录，日常检查无需运行本文件。
ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "release"
BUILD = ROOT / "build"


def main() -> int:
    """运行质量门禁、PyInstaller、打包后自检和真实 EXE 启动冒烟。"""

    started_at = time.perf_counter()
    RELEASE.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    artifact_name = os.environ.get("AUTHENTICATOR_OUTPUT_NAME", "AuthenticatorDesktop").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", artifact_name):
        raise ValueError("AUTHENTICATOR_OUTPUT_NAME contains unsupported characters")
    # 打包前先阻断质量问题，防止把无法验证的源码发布为二进制产物。
    subprocess.run([sys.executable, "-m", "pytest"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "ruff", "check", "."], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "mypy"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "py_compile", "app.py"], cwd=ROOT, check=True)
    # ``--add-data`` 让窗口图标可在 one-file 解包目录中被 ``resource_path`` 找到。
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--manifest",
        str(ROOT / "assets" / "windows" / "app.manifest"),
        "--name",
        artifact_name,
        "--distpath",
        str(RELEASE),
        "--workpath",
        str(BUILD / "pyinstaller-work"),
        "--specpath",
        str(BUILD / "pyinstaller-spec"),
        "--add-data",
        f"{ROOT / 'assets'};assets",
        "--hidden-import",
        "cryptography.hazmat.bindings._rust",
        "--hidden-import",
        "PIL.ImageGrab",
        "--hidden-import",
        "zxingcpp",
        "--exclude-module",
        "numpy",
        str(ROOT / "app.py"),
    ]
    subprocess.run(command, check=True)

    executable = RELEASE / f"{artifact_name}.exe"
    subprocess.run([str(executable), "--self-test"], check=True)
    # 将 EXE 复制到临时目录后启动，验证首次运行会创建同级 data 文件夹，且不会
    # 读写 release 目录中的正式便携式保险库。
    with tempfile.TemporaryDirectory(prefix="authenticator-smoke-") as temporary_directory:
        smoke_root = Path(temporary_directory)
        smoke_executable = smoke_root / "AuthenticatorDesktopSmoke.exe"
        shutil.copy2(executable, smoke_executable)
        process = subprocess.Popen([str(smoke_executable)], cwd=smoke_root, env=os.environ.copy())
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not (smoke_root / "data").is_dir():
                if process.poll() is not None:
                    raise RuntimeError(f"EXE smoke test exited early with code {process.returncode}")
                time.sleep(0.2)
            if not (smoke_root / "data").is_dir():
                raise RuntimeError("EXE smoke test did not create its adjacent data directory")
        finally:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/IM", smoke_executable.name, "/T", "/F"],
                    check=False,
                    capture_output=True,
                )
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            # Windows 可能在进程退出后短暂保留映像文件句柄。
            if os.name == "nt":
                time.sleep(0.5)

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = metadata["project"]["version"]
    elapsed = time.perf_counter() - started_at
    size_mb = executable.stat().st_size / (1024 * 1024)
    print(f"Build complete: {executable}")
    print(f"Version: {version} | Size: {size_mb:.2f} MiB | Time: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
