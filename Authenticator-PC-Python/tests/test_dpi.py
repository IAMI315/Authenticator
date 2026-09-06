"""DPI-awareness and logical geometry regression tests."""

from pathlib import Path

from presentation.dpi import DpiContext, DpiMode


def test_dpi_context_converts_logical_pixels_and_geometry():
    context = DpiContext(dpi=120, mode=DpiMode.PER_MONITOR_V2)

    assert context.scale == 1.25
    assert context.dp(20) == 25
    assert context.logical_px(1200) == 960
    assert context.physical_geometry("960x640") == "1200x800"
    assert context.logical_geometry(1200, 800) == "960x640"


def test_windows_manifest_declares_per_monitor_v2():
    manifest = (
        Path(__file__).resolve().parents[1] / "assets" / "windows" / "app.manifest"
    ).read_text(encoding="utf-8")

    assert "PerMonitorV2,PerMonitor" in manifest
    assert "true/pm" in manifest

