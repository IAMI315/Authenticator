"""主窗口生命周期、后台任务、定时器、自动锁定和退出控制。"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox
from typing import Any

from infrastructure.errors import VaultError
from infrastructure.secure_storage import MIN_MASTER_PASSWORD_LENGTH, StorageLoadKind, StorageLoadResult
from presentation.api_controller import ApiController
from presentation.compact_window import CompactWindow
from presentation.constants import APP_NAME
from presentation.dialogs import PasswordDialog
from presentation.mixins.base import WindowMixin


class LifecycleMixin(WindowMixin):
    """维护主窗口跨线程状态和事件循环周期任务。

类属性是由 ``MainWindow`` 初始化的共享状态提示，帮助维护者定位状态所有者；
本 mixin 的回调始终应在 Tk 主线程运行，后台工作只通过 ``BackgroundTaskRunner``。
    """

    compact_window: CompactWindow | None
    compact_mode: bool
    window_on_top: bool
    _closing: bool
    _busy: bool
    status_token: int
    api_error: str | None
    api_controller: ApiController | None

    def _load_vault(self) -> None:
        """异步读取保险库，成功后更新锁定状态，失败时提示并关闭程序。"""

        def loaded(result: StorageLoadResult) -> None:
            """在 Tk 主线程应用安全存储状态，并启动必要的设置或恢复流程。"""

            self._storage_load_kind = result.kind
            if result.unlocked:
                self._activate_secure_data("本地安全数据已自动解锁。")
                return
            self.locked = True
            self._vault_loaded = False
            self.refresh_tree()
            if result.kind == StorageLoadKind.NEEDS_SETUP:
                self._show_status("首次使用需要创建主密码。", clear_after=None)
                self.after(100, self._request_initial_master_password)
            else:
                message = (
                    "检测到旧版加密保险库，请输入原密码完成升级。"
                    if result.kind == StorageLoadKind.NEEDS_LEGACY_PASSWORD
                    else "本机自动解锁不可用，请输入主密码恢复。"
                )
                self._show_status(message, clear_after=None)
                self.after(100, self.unlock_vault)

        def load_failed(error: Exception) -> None:
            """显示无法读取保险库的错误；继续运行可能导致数据状态不可信。"""

            messagebox.showerror(APP_NAME, str(error), parent=self)
            self._shutdown()

        self._run_background_operation(
            self.vault_service.load,
            loaded,
            status="正在读取本地保险库...",
            on_error=load_failed,
        )

    def _request_initial_master_password(self) -> None:
        """首次运行或明文迁移时强制创建主密码；取消即退出且不写文件。"""

        password = PasswordDialog.ask(
            self,
            "创建主密码",
            "本地主密码用于保护账号、密钥和密码本。正常启动会由 Windows 自动解锁；"
            "换电脑或本机凭据失效时仍需此密码。忘记密码可能导致数据无法恢复。",
            confirm=True,
            min_length=MIN_MASTER_PASSWORD_LENGTH,
        )
        if password is None:
            self._shutdown()
            return
        self.vault.secure_settings = self.settings.secure_values()

        def initialized(_result: None) -> None:
            self._storage_load_kind = StorageLoadKind.AUTO_UNLOCKED
            self._activate_secure_data("本地数据已加密并启用自动解锁。")

        self._run_background_operation(
            lambda: self.vault_service.initialize(password),
            initialized,
            status="正在加密本地数据...",
        )

    def _activate_secure_data(self, status: str) -> None:
        """应用解密后的安全设置，持久化缺省令牌并启动本机 API。"""

        self.settings.apply_secure_values(self.vault.secure_settings)
        self.api_token = self.settings.api_token
        self.locked = False
        self._vault_loaded = True
        try:
            self._persist_settings()
        except VaultError as error:
            self._vault_loaded = False
            self.locked = True
            messagebox.showerror(APP_NAME, str(error), parent=self)
            self._shutdown()
            return
        self.last_activity = time.monotonic()
        if self.api_controller is None:
            self.api_error = None
            self.api_controller = ApiController(
                self.api_service,
                self.api_token,
                on_error=self._set_api_error,
            )
            self.api_endpoint = self.api_controller.endpoint
            self._start_local_api()
        self.refresh_tree()
        self._show_status(status)

    def _run_background_operation(
        self,
        work: Callable[[], Any],
        on_success: Callable[[Any], None],
        *,
        status: str,
        on_error: Callable[[Exception], None] | None = None,
    ) -> bool:
        """在线程池执行非 Tk 工作，并把结果回调调度回 Tk 主线程。

        返回 ``False`` 表示窗口正忙/关闭或执行器已关闭。``_busy`` 既防止重复写入，
        也使 API 在耗时保险库操作期间返回未就绪。
        """

        if self._busy or self._closing:
            self._show_status("已有任务正在执行，请稍候。")
            return False
        self._busy = True
        self._show_status(status, clear_after=None)

        def succeeded(result: Any) -> None:
            """由 ``drain`` 在 Tk 主线程执行，先清忙碌标记再交给调用方。"""

            self._busy = False
            if not self._closing:
                on_success(result)

        def failed(error: Exception) -> None:
            """由 ``drain`` 在 Tk 主线程执行，选择注入处理器或标准错误框。"""

            self._busy = False
            if self._closing:
                return
            if on_error is not None:
                on_error(error)
            else:
                messagebox.showerror(APP_NAME, str(error), parent=self)

        try:
            self.background_tasks.submit(work, succeeded, failed)
        except RuntimeError as error:
            failed(error)
            return False
        return True

    def _update_topmost_button(self) -> None:
        """同步完整窗口和轻量窗口的置顶按钮状态样式。"""

        if not hasattr(self, "topmost_button"):
            return
        self.topmost_button.configure(
            text="置顶",
            style="TopmostOn.TButton" if self.window_on_top else "TopmostOff.TButton",
        )
        if self.compact_window is not None:
            self.compact_window.update_topmost_button()

    def set_compact_mode(self, enabled: bool = False) -> None:
        """在完整窗口和轻量悬浮窗之间切换，并持久化模式/正常窗口尺寸。"""

        enabled = bool(enabled)
        if enabled == self.compact_mode and (not enabled or self.compact_window is not None):
            if enabled and self.compact_window is not None:
                self.compact_window.deiconify()
                self.compact_window.lift()
            return
        if enabled:
            # 进入轻量模式时隐藏根窗口，子 Toplevel 才是用户可见窗口。
            if self.locked:
                self._show_status("保险库已锁定，解锁后才能使用轻量模式。")
                return
            self.module_coordinator.conceal_passwords()
            self._compact_normal_geometry = self.dpi_context.logical_geometry(
                self.winfo_width(), self.winfo_height()
            )
            self.compact_mode = True
            self.settings.compact_mode = True
            self.settings.window_size = self._compact_normal_geometry
            try:
                self._persist_settings()
            except VaultError:
                self.compact_mode = False
                self.settings.compact_mode = False
                return
            self.attributes("-topmost", self.window_on_top)
            self.withdraw()
            self.compact_window = CompactWindow(self)
            self.compact_window.attributes("-topmost", self.window_on_top)
            self.compact_window.deiconify()
            self.compact_window.lift()
            return

        if self.compact_window is not None:
            try:
                self.compact_window.destroy()
            except tk.TclError:
                pass
            self.compact_window = None
        self.compact_mode = False
        self.settings.compact_mode = False
        self.deiconify()
        if self._compact_normal_geometry:
            self.geometry(self.dpi_context.physical_geometry(self._compact_normal_geometry))
        self.attributes("-topmost", self.window_on_top)
        try:
            self._persist_settings()
        except VaultError:
            pass
        self.lift()

    def toggle_always_on_top(self) -> None:
        """切换当前可见窗口的置顶属性，设置保存失败时恢复原值。"""

        previous_value = self.window_on_top
        self.window_on_top = not previous_value
        target_window: Any = self.compact_window if self.compact_mode and self.compact_window is not None else self
        target_window.attributes("-topmost", self.window_on_top)
        self.settings.always_on_top = self.window_on_top
        try:
            self._persist_settings()
        except VaultError as error:
            self.window_on_top = previous_value
            self.settings.always_on_top = previous_value
            target_window.attributes("-topmost", previous_value)
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self._update_topmost_button()
        if self.compact_window is None:
            self._show_status("窗口将始终置顶显示。" if self.window_on_top else "窗口已取消置顶。")
        else:
            self.compact_window.status_var.set("窗口已置顶。" if self.window_on_top else "窗口已取消置顶。")

    def _schedule_window_size_save(self, event: tk.Event[Any]) -> None:
        """对连续 Configure 事件去抖，避免拖动窗口时频繁写设置文件。"""

        if event.widget is not self or self._closing or self.state() != "normal":
            return
        self._window_size_debouncer.trigger()

    def _save_window_size(self, force: bool = False) -> None:
        """保存正常主窗口尺寸；关闭流程传 ``force`` 以完成最后一次写入。"""

        if (self._closing and not force) or self.state() != "normal":
            return
        size = self.dpi_context.logical_geometry(self.winfo_width(), self.winfo_height())
        if self.settings.window_size == size:
            return
        self.settings.window_size = size
        try:
            self._persist_settings()
        except VaultError:
            # 尺寸保存失败不能打断账号操作，保留当前内存尺寸即可。
            return

    def _start_local_api(self) -> None:
        """窗口空闲后启动本机 API，并记录可在设置页显示的启动错误。"""

        if self.api_controller is None or self._closing:
            return
        self.api_controller.start()
        self.api_error = self.api_controller.error
        self.api_endpoint = self.api_controller.endpoint

    def _set_api_error(self, error: str) -> None:
        """接收 API 控制器错误文本，供状态页和后续操作读取。"""

        self.api_error = error

    def _api_status_text(self) -> str:
        """返回设置对话框可直接展示的 API 状态。"""

        if self.api_error:
            return self.api_error
        return self.api_controller.status_text() if self.api_controller is not None else "未启动"

    def _process_api_requests(self) -> None:
        """每 50ms 在 Tk 主线程处理一小批 API 队列消息。"""

        if self._closing:
            return
        if self.api_controller is not None:
            self.api_controller.process()
        if not self._closing:
            self.after(50, self._process_api_requests)

    def _process_background_tasks(self) -> None:
        """每 50ms 在 Tk 主线程执行后台任务完成回调。"""

        if self._closing:
            return
        self.background_tasks.drain()
        self.after(50, self._process_background_tasks)

    def _shutdown(self) -> None:
        """有序关闭：阻止新回调、保存尺寸、停止 API、关闭执行器并销毁 Tk。"""

        if self._closing:
            return
        self._closing = True
        self._window_size_debouncer.cancel()
        self._responsive_debouncer.cancel()
        # 退出时记录实际可见模式。轻量窗口关闭会走到这里，因此下次启动
        # 能恢复到轻量模式；点击“完整界面”则已在切换时写入 False。
        self.settings.compact_mode = bool(self.compact_mode)
        try:
            self._persist_settings()
        except VaultError:
            # 退出不能被偏好设置写入失败阻塞，当前会话仍按用户选择结束。
            pass
        self._save_window_size(force=True)
        if self.api_controller is not None:
            self.api_controller.stop()
        self.background_tasks.close()
        self.destroy()

    def _note_activity(self, _event: tk.Event[Any] | None = None) -> None:
        """记录键盘/鼠标活动，用于加密保险库的闲置自动锁定计时。"""

        if not self.locked:
            self.last_activity = time.monotonic()

    def _tick(self) -> None:
        """每秒检查自动锁定，并只更新可见行的验证码/倒计时文本。"""

        if self._busy:
            self.after(1_000, self._tick)
            return
        if not self.locked and self.vault.encrypted and self.settings.autolock_minutes:
            timeout = self.settings.autolock_minutes * 60
            if time.monotonic() - self.last_activity >= timeout:
                self.lock_vault(auto_locked=True)
        if not self.locked:
            self._update_visible_rows()
        elif self.compact_window is not None:
            self.compact_window.refresh()
        self.after(1_000, self._tick)

    def _show_status(self, message: str, clear_after: int | None = 6_000) -> None:
        """显示状态栏文本，并用递增令牌防止旧定时器清掉新消息。"""

        self.status_token += 1
        token = self.status_token
        self.status_var.set(message)
        if clear_after:
            self.after(clear_after, lambda: self.status_var.set("就绪") if token == self.status_token else None)

    def _guard_unlocked(self) -> bool:
        """阻止忙碌或锁定状态下的写操作；锁定时触发解锁流程后返回假。"""

        if self._busy:
            self._show_status("已有任务正在执行，请稍候。")
            return False
        if not self.locked:
            return True
        self._show_status("请先解锁保险库，再修改数据。")
        self.unlock_vault()
        return not self.locked
