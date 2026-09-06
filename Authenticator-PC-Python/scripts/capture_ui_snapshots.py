"""Capture isolated UI regression snapshots without reading the user's vault."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import tempfile
from pathlib import Path

# Opt into physical coordinates before Tk is imported so window bounds and
# ImageGrab use the same coordinate system on 125%/150% Windows DPI settings.
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import ImageGrab  # noqa: E402

from domain.entities import OTPEntry  # noqa: E402
from domain.passwords import PasswordEntry  # noqa: E402
from infrastructure.vault_repository import JsonVaultRepository  # noqa: E402
from infrastructure.vault_store import Vault  # noqa: E402
from presentation.main_window import MainWindow  # noqa: E402

SNAPSHOT_SIZES = ((960, 640), (1280, 720), (1600, 900))


def _sample_accounts() -> list[OTPEntry]:
    definitions = (
        ("OpenAI", "user.one@example.com", False),
        ("Google", "work.account@gmail.com", True),
        ("Microsoft", "very-long-account-name-639400@outlook.com", False),
        ("GitHub", "developer@example.com", False),
    )
    entries: list[OTPEntry] = []
    for issuer, account, pinned in definitions:
        entry = OTPEntry.from_uri(
            f"otpauth://totp/{issuer}:{account}?secret=JBSWY3DPEHPK3PXP&issuer={issuer}"
        )
        entry.pinned = pinned
        entries.append(entry)
    return entries


def _sample_passwords() -> list[PasswordEntry]:
    records = (
        ("OpenAI", "user.one@example.com", "https://openai.com", True),
        ("GitHub", "developer@example.com", "https://github.com", False),
        ("", "local-admin", "", False),
    )
    return [
        PasswordEntry.from_dict(
            {
                "name": name,
                "username": username,
                "password": "Snapshot-only-password!42",
                "url": url,
                "pinned": pinned,
            }
        )
        for name, username, url, pinned in records
    ]


def capture(output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    temporary_data = tempfile.TemporaryDirectory(prefix="authenticator-ui-")
    data_directory = Path(temporary_data.name) / "data"
    repository = JsonVaultRepository(data_directory / "vault.json", Vault)
    repository.initialize(repository.create(), "snapshot-password")
    app = MainWindow(data_directory=data_directory)
    app.title("验证器桌面版 - UI 截图")
    app.attributes("-topmost", True)

    def start_when_loaded() -> None:
        if not app._vault_loaded:
            app.after(50, start_when_loaded)
            return
        app.vault.entries = _sample_accounts()
        app.vault.password_entries = _sample_passwords()
        app.refresh_tree()
        steps = [(width, height, module) for width, height in SNAPSHOT_SIZES for module in ("otp", "passwords")]
        run_step(steps, 0)

    def run_step(steps: list[tuple[int, int, str]], index: int) -> None:
        if index >= len(steps):
            app.attributes("-topmost", False)
            app._shutdown()
            temporary_data.cleanup()
            return
        width, height, module = steps[index]
        app.geometry(f"{app.dpi_context.physical_geometry(f'{width}x{height}')}+20+20")
        app.module_coordinator.switch(module)  # type: ignore[arg-type]
        app.lift()
        app.update_idletasks()
        # Resizing across the 1120 px breakpoint rebuilds the sidebar. Give
        # Windows a full paint cycle before screen capture to avoid transient
        # blank controls in regression artifacts.
        app.after(700, lambda: prepare_step(steps, index))

    def prepare_step(steps: list[tuple[int, int, str]], index: int) -> None:
        app.lift()
        app.update_idletasks()
        app.after(150, lambda: save_step(steps, index))

    def save_step(steps: list[tuple[int, int, str]], index: int) -> None:
        width, height, module = steps[index]
        window = ctypes.windll.user32.FindWindowW(None, app.title())
        bounds = ctypes.wintypes.RECT()
        if not window or not ctypes.windll.user32.GetWindowRect(window, ctypes.byref(bounds)):
            raise RuntimeError("无法读取截图窗口边界")
        image = ImageGrab.grab(
            bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom),
            all_screens=True,
        )
        image.save(output_directory / f"{width}x{height}-{module}.png")
        app.after(300, lambda: run_step(steps, index + 1))

    app.after_idle(start_when_loaded)
    app.mainloop()


if __name__ == "__main__":
    capture(Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "build" / "ui-snapshots")
