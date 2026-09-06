"""完整界面和轻量窗口共享扫码流程的无 Tk 单元测试。"""

from __future__ import annotations

from typing import Any

from infrastructure.qr_scanner import QrCodeNotFoundError
from presentation.qr_scan_flow import QrScanFlow


class FakeWindow:
    def __init__(self, state: str = "normal") -> None:
        self._state = state
        self.withdraw_count = 0
        self.deiconify_count = 0
        self.lift_count = 0
        self.grab_count = 0

    def state(self, value: str | None = None) -> str:
        if value is not None:
            self._state = value
        return self._state

    def withdraw(self) -> None:
        self.withdraw_count += 1
        self._state = "withdrawn"

    def deiconify(self) -> None:
        self.deiconify_count += 1
        self._state = "normal"

    def lift(self) -> None:
        self.lift_count += 1

    def grab_set(self) -> None:
        self.grab_count += 1


class FakeHost(FakeWindow):
    def __init__(self, grab_owner: FakeWindow | None = None) -> None:
        super().__init__()
        self.grab_owner = grab_owner

    def update_idletasks(self) -> None:
        pass

    def after(self, _delay: int, callback: Any) -> str:
        callback()
        return "after-id"

    def grab_current(self) -> FakeWindow | None:
        return self.grab_owner

    def winfo_vrootx(self) -> int:
        return 0

    def winfo_vrooty(self) -> int:
        return 0

    def winfo_vrootwidth(self) -> int:
        return 1920

    def winfo_vrootheight(self) -> int:
        return 1080


class ImmediateTasks:
    def submit(self, work: Any, on_success: Any, on_error: Any) -> None:
        try:
            result = work()
        except Exception as error:
            on_error(error)
        else:
            on_success(result)


class FallbackScanner:
    def __init__(self) -> None:
        self.captured: tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None = None

    def scan_screen(self) -> Any:
        raise QrCodeNotFoundError("not found")

    def capture_region(
        self,
        bbox: tuple[int, int, int, int],
        logical_screen: tuple[int, int, int, int],
    ) -> str:
        self.captured = (bbox, logical_screen)
        return "region-image"

    def decode(self, image: Any) -> str:
        assert image == "region-image"
        return "decoded-payload"


def test_not_found_automatically_falls_back_to_region_without_error_callback() -> None:
    owner = FakeWindow("zoomed")
    dialog = FakeHost(grab_owner=owner)
    scanner = FallbackScanner()
    selector_calls: list[object] = []
    successes: list[str] = []
    errors: list[Exception] = []
    states: list[str] = []

    def select_region(_parent: Any, callback: Any) -> object:
        selector_calls.append(_parent)
        callback((100, 120, 500, 520))
        return object()

    flow = QrScanFlow(
        dialog,  # type: ignore[arg-type]
        scanner,
        ImmediateTasks(),
        selector_factory=select_region,
        automatic_delay_ms=0,
    )
    started = flow.start(
        (owner, dialog),
        successes.append,
        errors.append,
        on_state_changed=states.append,
    )

    assert started
    assert successes == ["decoded-payload"]
    assert errors == []
    assert selector_calls == [dialog]
    assert scanner.captured == ((100, 120, 500, 520), (0, 0, 1920, 1080))
    assert states == ["automatic", "selecting", "decoding"]
    assert owner.state() == "zoomed" and dialog.state() == "normal"
    assert owner.withdraw_count == 1 and dialog.withdraw_count == 1
    assert owner.grab_count == 1
    assert not flow.running


def test_automatic_success_skips_region_selector() -> None:
    host = FakeHost()
    selected = False
    successes: list[str] = []

    class AutomaticScanner(FallbackScanner):
        def scan_screen(self) -> str:
            return "automatic-payload"

    def select_region(_parent: Any, _callback: Any) -> object:
        nonlocal selected
        selected = True
        return object()

    flow = QrScanFlow(
        host,  # type: ignore[arg-type]
        AutomaticScanner(),
        ImmediateTasks(),
        selector_factory=select_region,
        automatic_delay_ms=0,
    )
    flow.start((host,), successes.append, lambda error: None)

    assert successes == ["automatic-payload"]
    assert not selected
    assert host.deiconify_count == 1
