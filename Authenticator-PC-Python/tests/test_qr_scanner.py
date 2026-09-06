"""验证 Windows DPI 缩放下逻辑屏幕选区到截图像素选区的转换。"""

from infrastructure.qr_scanner import expand_image_bbox, scale_screen_bbox


def test_scale_screen_bbox_handles_windows_dpi_scaling():
    """150% DPI 截图应将逻辑坐标正确转换为物理像素坐标。"""

    assert scale_screen_bbox((100, 50, 300, 150), (0, 0, 1000, 500), (1500, 750)) == (
        150, 75, 450, 225
    )


def test_expand_image_bbox_adds_quiet_zone_and_clamps_to_screenshot():
    assert expand_image_bbox((100, 80, 300, 280), (800, 600)) == (84, 64, 316, 296)
    assert expand_image_bbox((2, 3, 102, 103), (800, 600)) == (0, 0, 114, 115)
