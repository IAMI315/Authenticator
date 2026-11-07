"""主 Tkinter 窗口的依赖装配与桌面交互控制器。

本文件刻意只保留根窗口和依赖装配；具体布局、生命周期、账号列表、账号操作、
分组、导入导出和保险库控制分别位于 ``presentation.mixins``。
"""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from typing import Any

from application.account_service import AccountService
from application.backup_service import BackupService
from application.group_service import GroupService
from application.import_export import parse_qr_content
from application.import_service import ImportService
from application.password_group_service import PasswordGroupService
from application.password_search_service import PasswordSearchService
from application.password_service import PasswordService
from application.qr_import_service import QrImportService
from application.search_service import SearchService
from application.server_service import ServerService
from application.sorting import parse_otp_sort, parse_password_sort
from application.storage_service import StorageService
from domain.entities import DEFAULT_GROUP_NAME, MAX_GROUP_NAME_LENGTH, OTPEntry
from domain.validators import utc_now_iso
from infrastructure.api_server import LOCAL_API_BASE_PATH, LOCAL_API_HOST, LOCAL_API_PORT
from infrastructure.api_service import ApiService
from infrastructure.backup_codec import BackupCodec
from infrastructure.backup_files import JsonBackupFileStore
from infrastructure.paths import application_data_directory
from infrastructure.qr_scanner import QrScanner
from infrastructure.secure_storage import StorageLoadKind
from infrastructure.settings_repository import JsonSettingsRepository
from infrastructure.settings_store import SettingsStore
from infrastructure.ssh_sessions import SshSessionManager
from infrastructure.task_runner import BackgroundTaskRunner
from infrastructure.vault_repository import JsonVaultRepository
from infrastructure.vault_store import Vault
from presentation.api_controller import ApiController
from presentation.api_scan_coordinator import ApiScanCoordinator
from presentation.compact_window import CompactWindow
from presentation.constants import (
    ALL_ACCOUNTS_LABEL,
    APP_NAME,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
)
from presentation.dpi import DpiContext
from presentation.mixins import (
    AccountActionsMixin,
    AccountListMixin,
    GroupActionsMixin,
    ImportExportMixin,
    LayoutMixin,
    LifecycleMixin,
    VaultControlsMixin,
)
from presentation.module_coordinator import ModuleCoordinator
from presentation.mui.workspace import MuiWorkspace
from presentation.password_controller import PasswordController
from presentation.scheduling import TrailingDebouncer
from presentation.view_models import (
    AccountRowPresenter,
    CodeCache,
    CompactViewModel,
    MainViewModel,
    PasswordViewModel,
)


class MainWindow(
    LayoutMixin,
    LifecycleMixin,
    AccountListMixin,
    GroupActionsMixin,
    AccountActionsMixin,
    ImportExportMixin,
    VaultControlsMixin,
    tk.Tk,
):
    """程序唯一的 Tk 根窗口及跨层依赖组合根。

    Mixin 顺序反映功能分区而非业务继承：布局创建控件，生命周期驱动事件循环，
    其余 mixin 只处理相应 UI 事件。关键状态包括 ``vault``、``locked``、``_busy``、
    ``main_view_model``、``background_tasks`` 和 ``api_controller``。
    """

    def __init__(
        self,
        data_directory: Path | None = None,
        dpi_context: DpiContext | None = None,
        mui_enabled: bool | None = None,
    ) -> None:
        """装配持久化、领域服务、视图模型与 Tk 控件，并安排首次异步加载。"""

        super().__init__()
        self.dpi_context = dpi_context or DpiContext()
        self.dpi_context.refresh_for_window(self)
        self.title(APP_NAME)
        # 基础设施对象：路径、保险库、设置、扫码和后台线程均在此处集中创建。
        self.data_directory = data_directory or application_data_directory()
        # Temporary test and screenshot vaults retain the deterministic native
        # UI. Production starts MUI by default unless ``--classic-ui`` opts out.
        self._mui_requested = data_directory is None if mui_enabled is None else bool(mui_enabled)
        self.mui_workspace: MuiWorkspace | None = None
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.vault_repository = JsonVaultRepository(self.data_directory / "vault.json", Vault)
        self.vault = self.vault_repository.create()
        self.backup_codec = BackupCodec(self.vault_repository.store.protector)
        self.backup_service = BackupService(
            self.backup_codec,
            JsonBackupFileStore(),
            self.vault_repository.store,
            utc_now_iso,
        )
        self.qr_scanner = QrScanner(parse_qr_content)
        self.background_tasks = BackgroundTaskRunner()
        self.settings_repository = JsonSettingsRepository(self.data_directory / "settings.json", SettingsStore)
        self.settings = self.settings_repository.create()
        # 应用服务只接受回调/仓储边界，UI 事件不能绕过它们直接写保险库集合。
        self.account_service = AccountService(self.vault, self._persist_vault)
        self.search_service = SearchService()
        self.main_view_model = MainViewModel(self.vault, self.search_service, ALL_ACCOUNTS_LABEL)
        self.compact_view_model = CompactViewModel(self.main_view_model)
        self.password_search_service = PasswordSearchService()
        self.password_service = PasswordService(
            self.vault,
            self._persist_vault,
            self.password_search_service,
        )
        self.password_group_service = PasswordGroupService(self.vault, self._persist_vault)
        self.password_view_model = PasswordViewModel(self.vault, self.password_service)
        self.password_controller = PasswordController(
            self,
            self.password_service,
            self.password_group_service,
            self.password_view_model,
        )
        self.server_service = ServerService(self.vault, self._persist_vault)
        self.ssh_sessions = SshSessionManager()
        self.module_coordinator = ModuleCoordinator(self, self.password_controller)
        self.vault_service = StorageService(self.vault, self.vault_repository)
        self.import_service = ImportService(
            self.vault,
            self._persist_vault,
            utc_now_iso,
        )
        self.qr_import_service = QrImportService(self.vault, self.import_service)
        self.group_service = GroupService(
            self.vault,
            self._persist_vault,
            default_group_name=DEFAULT_GROUP_NAME,
            all_accounts_label=ALL_ACCOUNTS_LABEL,
            max_name_length=MAX_GROUP_NAME_LENGTH,
        )
        self.settings_repository.load(self.settings)
        self.main_view_model.set_sort(
            parse_otp_sort(self.settings.otp_sort_field, self.settings.otp_sort_direction)
        )
        self.password_view_model.set_sort(
            parse_password_sort(
                self.settings.password_sort_field,
                self.settings.password_sort_direction,
            )
        )
        self.main_view_model.set_show_pinned(self.settings.otp_show_pinned)
        self.password_view_model.set_show_pinned(self.settings.password_show_pinned)
        self.geometry(self.dpi_context.physical_geometry(self.settings.window_size))
        self.minsize(self.dpi_context.dp(MIN_WINDOW_WIDTH), self.dpi_context.dp(MIN_WINDOW_HEIGHT))
        self.resizable(True, True)
        # 窗口/保险库状态：``locked`` 与 ``vault.encrypted`` 的含义见维护指南。
        self.window_on_top = self.settings.always_on_top
        self.compact_mode = False
        self._compact_normal_geometry = self.settings.window_size
        self.attributes("-topmost", self.window_on_top)
        self.locked = False
        self._vault_loaded = False
        self._storage_load_kind = StorageLoadKind.NEEDS_SETUP
        self._busy = False
        self._closing = False
        self.last_activity = time.monotonic()
        self.status_token = 0
        self.search_var = tk.StringVar()
        self.group_var = tk.StringVar(value=ALL_ACCOUNTS_LABEL)
        self.active_group_id: str | None = None
        self._group_label_to_id: dict[str, str | None] = {}
        self.result_summary_var = tk.StringVar(value="0 个账号")
        self.status_var = tk.StringVar(value="就绪")
        self.security_var = tk.StringVar()
        self.detail_var = tk.StringVar(value="选择一个账号以复制、编辑或导出 URI。")
        # ``action_widgets`` 是锁定/忙碌状态需要统一禁用的 ttk 按钮集合。
        self.action_widgets: list[Any] = []
        self._displayed_entries: list[OTPEntry] = []
        self._search_after_id: str | None = None
        self._window_size_debouncer = TrailingDebouncer(self, 500, self._save_window_size)
        self._dpi_after_id: str | None = None
        self._selection_anchor_id: str | None = None
        self._code_cache: CodeCache = {}
        self._row_presenter = AccountRowPresenter(self._code_cache)
        self.api_error: str | None = None
        self.compact_window: CompactWindow | None = None
        # API 服务只被主线程 ``ApiController.process`` 调用，HTTP 线程不会触及 vault。
        self.api_service = ApiService(
            self.vault,
            self.account_service,
            OTPEntry.from_dict,
            self.search_service.search,
            utc_now_iso,
            lambda: self._vault_loaded and not self._busy,
            lambda: self.locked,
            refresh_callback=self.refresh_tree,
            status_callback=self._show_status,
        )
        self.api_scan_coordinator = ApiScanCoordinator(self, self.qr_import_service)
        # API 必须等安全设置解密完成后才取得令牌并启动。
        self.api_token = ""
        self.api_controller: ApiController | None = None
        self.api_endpoint = f"http://{LOCAL_API_HOST}:{LOCAL_API_PORT}{LOCAL_API_BASE_PATH}"

        # 以下调用均在 Tk 主线程：构建控件后再绑定事件和定时轮询。
        self._configure_style()
        self._set_icon()
        self._build_menu()
        self._build_widgets()
        self._update_topmost_button()
        if self._mui_requested:
            self.after_idle(self._initialize_mui_workspace)
        if self.settings.compact_mode:
            self.after_idle(lambda: self.set_compact_mode(True))
        self.search_var.trace_add("write", self._schedule_search)
        self.bind_all("<KeyPress>", self._note_activity, add="+")
        self.bind_all("<Button>", self._note_activity, add="+")
        self.bind_all("<Control-f>", lambda _event: self.module_coordinator.focus_search(), add="+")
        self.protocol("WM_DELETE_WINDOW", self._shutdown)
        self.after_idle(self._load_vault)
        self.after(50, self._process_api_requests)
        self.after(50, self._process_background_tasks)
        self.after(1_000, self._tick)

    def _initialize_mui_workspace(self) -> None:
        """Mount the bundled MUI UI, retaining classic Tk as a safe fallback."""

        if self._closing or self.mui_workspace is not None:
            return
        try:
            self.mui_workspace = MuiWorkspace(self, self)
            self._set_classic_chrome_visible(False)
            self.mui_workspace.activate()
            # Creating an Edge profile and loading React is the expensive part
            # of the first compact switch. Prewarm it after the full window is
            # usable, then keep it paused and hidden until it is requested.
            self.after(1_200, self._prewarm_compact_workspace)
        except Exception as error:
            self.mui_workspace = None
            self._set_classic_chrome_visible(True)
            self._show_status(f"MUI 界面不可用，已使用经典界面：{error}", clear_after=10_000)

    def _prewarm_compact_workspace(self) -> None:
        """Prepare the compact MUI surface without showing a second window."""

        if (
            self._closing
            or self.compact_mode
            or self.compact_window is not None
            or self.mui_workspace is None
            or not self._mui_requested
        ):
            return
        try:
            self.compact_window = CompactWindow(self, start_hidden=True)
        except Exception:
            # The regular switch path retains its existing fallback behavior.
            self.compact_window = None

    def _mui_surface_active(self) -> bool:
        """Whether a visible MUI renderer owns the current interface."""

        workspace = getattr(self, "mui_workspace", None)
        if workspace is not None and workspace.active:
            return True
        compact = getattr(self, "compact_window", None)
        compact_workspace = getattr(compact, "_mui_workspace", None)
        return bool(compact_workspace is not None and compact_workspace.active)

    def _set_classic_chrome_visible(self, visible: bool) -> None:
        """Avoid laying out the hidden Tk workspace while MUI owns the window."""

        widgets = (
            getattr(self, "header_frame", None),
            getattr(self, "body_frame", None),
            getattr(self, "main_footer", None),
        )
        if not all(widgets):
            return
        if not visible:
            for widget in widgets:
                if widget is not None:
                    widget.grid_remove()
            return
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.body_frame.grid(row=1, column=0, sticky="nsew")
        self.main_footer.grid(row=2, column=0, sticky="ew")
        self._responsive_layout_signature = None
        self.after_idle(self._apply_responsive_layout)
