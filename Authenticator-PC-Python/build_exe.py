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
FRONTEND = ROOT / "frontend"


def main() -> int:
    """运行质量门禁、PyInstaller、打包后自检和真实 EXE 启动冒烟。"""

    started_at = time.perf_counter()
    RELEASE.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    artifact_name = os.environ.get("AUTHENTICATOR_OUTPUT_NAME", "AuthenticatorDesktop").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", artifact_name):
        raise ValueError("AUTHENTICATOR_OUTPUT_NAME contains unsupported characters")
    _build_frontend()
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
        "--icon",
        str(ROOT / "assets" / "icon.ico"),
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
        "--add-data",
        f"{FRONTEND / 'dist'};frontend/dist",
        "--hidden-import",
        "cryptography.hazmat.bindings._rust",
        "--hidden-import",
        "PIL.ImageGrab",
        "--hidden-import",
        "zxingcpp",
        "--hidden-import",
        "tkwebview2.tkwebview2",
        "--hidden-import",
        "clr",
        "--collect-all",
        "tkwebview2",
        "--collect-all",
        "webview",
        "--collect-all",
        "clr_loader",
        "--collect-all",
        "pythonnet",
        # Paramiko discovers ciphers and key implementations dynamically.  Collect
        # its bundled dependencies so SSH keeps working from the one-file EXE.
        "--collect-all",
        "paramiko",
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


def _build_frontend() -> None:
    """Install locked local UI dependencies and bundle them without a CDN."""

    if not (FRONTEND / "package.json").is_file():
        raise RuntimeError("MUI frontend package.json is missing")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise RuntimeError("MUI build requires Node.js and npm")
    skip_install = os.environ.get("AUTHENTICATOR_SKIP_NPM_INSTALL") == "1"
    if skip_install:
        if not (FRONTEND / "node_modules").is_dir():
            raise RuntimeError("AUTHENTICATOR_SKIP_NPM_INSTALL requires frontend/node_modules")
    elif (FRONTEND / "package-lock.json").is_file():
        if os.name == "nt":
            # ``npm ci`` first deletes node_modules. On this Windows desktop
            # that clean step can fail or stall when a package directory still
            # has a transient system handle. Install from the lockfile in
            # place and prevent any lockfile rewrite instead.
            subprocess.run([npm, "install", "--no-audit", "--no-fund", "--package-lock=false"], cwd=FRONTEND, check=True)
        else:
            subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)
    else:
        subprocess.run([npm, "install"], cwd=FRONTEND, check=True)
    subprocess.run([npm, "run", "test"], cwd=FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
