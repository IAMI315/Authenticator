"""Build and verify the Android APK on Windows without WSL or Docker."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = Path(os.environ.get("LOCALAPPDATA", "")) / "AuthenticatorBuildTools"
SDK = TOOLS / "android-sdk"
JDK_ROOT = TOOLS / "jdk17"
OUTPUT = ROOT / "release" / "AuthenticatorMobile-1.4.5-arm64-v8a-debug.apk"
LOCAL_GRADLE = TOOLS / "gradle" / "gradle-8.10.2" / "bin" / "gradle.bat"


def _jdk() -> Path:
    candidates = sorted(JDK_ROOT.glob("*/bin/java.exe"), reverse=True)
    if not candidates:
        raise RuntimeError(f"JDK 17 not found under {JDK_ROOT}")
    return candidates[0].parents[1]


def main() -> int:
    env = os.environ.copy()
    env["JAVA_HOME"] = str(_jdk())
    env["ANDROID_HOME"] = str(SDK)
    env["ANDROID_SDK_ROOT"] = str(SDK)
    python_311 = Path(os.environ.get("APPDATA", "")) / "uv" / "python" / "cpython-3.11.15-windows-x86_64-none" / "python.exe"
    if not python_311.exists():
        raise RuntimeError(f"Python 3.11 not found at {python_311}")
    env["AUTHENTICATOR_PYTHON311"] = str(python_311)

    subprocess.run([sys.executable, "-m", "pytest", "tests"], cwd=ROOT, check=True)
    wrapper = LOCAL_GRADLE if LOCAL_GRADLE.exists() else ROOT / "gradlew.bat"
    subprocess.run(
        [str(wrapper), "--no-daemon", "testDebugUnitTest", "lintDebug", "assembleDebug"],
        cwd=ROOT,
        env=env,
        check=True,
    )

    source = ROOT / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
    OUTPUT.parent.mkdir(exist_ok=True)
    shutil.copy2(source, OUTPUT)
    for old_apk in OUTPUT.parent.glob("AuthenticatorMobile-*.apk"):
        if old_apk != OUTPUT:
            old_apk.unlink()
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest().upper()
    print(f"APK: {OUTPUT}")
    print(f"Size: {OUTPUT.stat().st_size / (1024 * 1024):.2f} MiB")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
