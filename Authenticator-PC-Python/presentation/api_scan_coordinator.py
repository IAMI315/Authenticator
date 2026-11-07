"""本机 API 与桌面扫码 UI 之间的异步协调器。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from application.qr_import_service import QrImportService, ScannedImportResult
from infrastructure.errors import VaultError
from infrastructure.qr_scanner import QrCodeNotFoundError
from presentation.qr_scan_flow import QrScanFlow

ApiCompletion = Callable[[tuple[int, dict[str, Any]]], None]


class ApiScanCoordinator:
    """以现有 UI 扫码流程响应一条等待中的 HTTP 请求。

    ``QrScanFlow`` 在后台解析图像、在 Tk 主线程恢复窗口和保存账号。本协调器
    只把最终结果转换为非敏感 API 响应，因此 HTTP 线程不接触 Tk 控件或保险库。
    """

    def __init__(self, app: Any, import_service: QrImportService) -> None:
        self.app = app
        self.import_service = import_service
        self.flow = QrScanFlow(app, app.qr_scanner, app.background_tasks)
        self._completion: ApiCompletion | None = None

    def start(self, payload: dict[str, Any], completion: ApiCompletion) -> bool:
        """启动一次自动全屏识别，未识别到时进入用户框选流程。"""

        if self.flow.running:
            return False
        self._completion = completion
        group_ids = payload.get("group_ids", ())
        windows = (self.app, getattr(self.app, "compact_window", None))
        started = self.flow.start(
            windows,
            lambda result: self._scan_succeeded(result, group_ids),
            self._scan_failed,
            on_cancel=self._scan_cancelled,
            on_state_changed=self._scan_state_changed,
        )
        if not started:
            self._completion = None
        return started

    def cancel(self) -> None:
        """取消进行中的扫码，并确保等待请求获得明确的取消结果。"""

        self.flow.cancel()

    def _scan_state_changed(self, state: str) -> None:
        messages = {
            "automatic": "API 正在识别屏幕二维码...",
            "selecting": "请框选二维码",
            "decoding": "正在识别二维码...",
        }
        self.app._show_status(messages.get(state, "正在识别二维码..."), clear_after=None)

    def _scan_succeeded(self, payload: Any, group_ids: Any) -> None:
        try:
            result = self.import_service.import_payload(payload, group_ids)
        except ValueError as error:
            self._complete(400, {"error": "invalid_scan_import", "message": str(error)})
            return
        except VaultError:
            self._complete(500, {"error": "vault_save_failed"})
            return
        except Exception:
            self._complete(500, {"error": "scan_import_failed"})
            return

        self.app.refresh_tree()
        compact_window = getattr(self.app, "compact_window", None)
        if compact_window is not None:
            compact_window.refresh()
            if result.account_ids:
                compact_window.highlight_accounts(list(result.account_ids))
        self.app._show_status(self._status_message(result), clear_after=10_000)
        self._complete(
            201 if result.accounts_added else 200,
            {
                "completed": True,
                "source": result.source,
                "accounts_added": result.accounts_added,
                "duplicates_skipped": result.duplicates_skipped,
                "account_ids": list(result.account_ids),
                "group_ids": list(result.group_ids),
                "warnings": list(result.warnings),
            },
        )

    def _scan_failed(self, error: Exception) -> None:
        if isinstance(error, ImportError):
            response = 503, {"error": "qr_scanner_unavailable"}
        elif isinstance(error, (QrCodeNotFoundError, ValueError)):
            response = 422, {"error": "invalid_qr_code", "message": str(error)}
        else:
            response = 500, {"error": "scan_failed"}
        self.app._show_status("API 扫码失败。")
        self._complete(*response)

    def _scan_cancelled(self) -> None:
        self.app._show_status("已取消 API 扫码。")
        self._complete(408, {"error": "scan_cancelled"})

    def _complete(self, status: int, document: dict[str, Any]) -> None:
        completion, self._completion = self._completion, None
        if completion is not None:
            completion((status, document))

    @staticmethod
    def _status_message(result: ScannedImportResult) -> str:
        return (
            f"API 扫码完成：新增 {result.accounts_added} 个账号，"
            f"跳过 {result.duplicates_skipped} 个重复账号。"
        )
