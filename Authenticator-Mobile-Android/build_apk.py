"""Build and verify the Android APK on Windows without WSL or Docker."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_TOOLS = ROOT / ".build-tools"
USER_TOOLS = Path(os.environ.get("LOCALAPPDATA", "")) / "AuthenticatorBuildTools"
TOOL_ROOTS = (PROJECT_TOOLS, USER_TOOLS)
OUTPUT = ROOT / "release" / "AuthenticatorMobile-1.4.25-arm64-v8a-debug.apk"


def _tool_directory(*names: str) -> Path:
    for root in TOOL_ROOTS:
        for name in names:
            candidate = root / name
            if candidate.exists():
                return candidate
    return TOOL_ROOTS[0] / names[0]


SDK = _tool_directory("sdk", "android-sdk")
JDK_ROOT = _tool_directory("jdk17")
LOCAL_GRADLE = _tool_directory("gradle") / "gradle-8.10.2" / "bin" / "gradle.bat"
TEST_ENVIRONMENT = PROJECT_TOOLS / "python311-tests"


def _jdk() -> Path:
    configured = Path(os.environ.get("AUTHENTICATOR_JAVA_HOME", os.environ.get("JAVA_HOME", "")))
    if (configured / "bin" / "java.exe").exists():
        return configured
    candidates = sorted(JDK_ROOT.glob("*/bin/java.exe"), reverse=True)
    if not candidates:
        raise RuntimeError(
            "JDK 17 not found. Set AUTHENTICATOR_JAVA_HOME or install it under "
            f"{JDK_ROOT}",
        )
    return candidates[0].parents[1]


def _configure_sdk_location(sdk: Path) -> None:
    if not (sdk / "platforms" / "android-35" / "android.jar").exists():
        raise RuntimeError(f"Android SDK platform 35 not found under {sdk}")
    local_properties = ROOT / "local.properties"
    existing = local_properties.read_text(encoding="utf-8").splitlines() if local_properties.exists() else []
    retained = [line for line in existing if not line.startswith("sdk.dir=")]
    retained.append(f"sdk.dir={sdk.as_posix()}")
    local_properties.write_text("\n".join(retained) + "\n", encoding="utf-8")


def _test_python(python_311: Path, env: dict[str, str]) -> Path:
    executable = TEST_ENVIRONMENT / "Scripts" / "python.exe"
    if not executable.exists():
        subprocess.run([str(python_311), "-m", "venv", str(TEST_ENVIRONMENT)], env=env, check=True)
    subprocess.run(
        [str(executable), "-m", "pip", "install", "pytest", "cryptography==42.0.8"],
        env=env,
        check=True,
    )
    return executable


def main() -> int:
    env = os.environ.copy()
    env["JAVA_HOME"] = str(_jdk())
    env["ANDROID_HOME"] = str(SDK)
    env["ANDROID_SDK_ROOT"] = str(SDK)
    _configure_sdk_location(SDK)
    python_311 = Path(os.environ.get("APPDATA", "")) / "uv" / "python" / "cpython-3.11.15-windows-x86_64-none" / "python.exe"
    if not python_311.exists():
        raise RuntimeError(f"Python 3.11 not found at {python_311}")
    env["AUTHENTICATOR_PYTHON311"] = str(python_311)

    test_python = _test_python(python_311, env)
    subprocess.run([str(test_python), "-m", "pytest", "tests"], cwd=ROOT, env=env, check=True)
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
