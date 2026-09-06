# 验证器桌面版工程化重构计划

本文件记录验证器桌面版的渐进式重构路线。目标是在保持现有中文界面、保险库格式、API 和 EXE 使用方式兼容的前提下，逐步拆分领域模型、持久化、应用服务、UI 和 API。

## 当前状态

计划中的八个阶段均已实现并进入发布验证。当前稳定入口为 `app.py`；`authenticator_desktop.py` 仅保留对 `app.main()` 的兼容转发。重构未修改保险库格式、API 路径、中文界面或主要操作方式。

密码本同级模块已按现有分层接入：`domain/passwords.py` 负责模型与生成规则，`application/password_*` 负责事务服务和端口，`presentation/password_*` 负责独立工作区、控制器及对话框。保险库保持 `authenticator-desktop/v1`，通过可选字段兼容保存密码记录和独立密码分组，本机 API 不暴露密码数据。

## 已完成的第一轮

- 已增加 `app.py` 稳定入口、`pyproject.toml`、开发依赖和 Python 产物忽略规则。
- 已建立 `domain/identifiers.py`，统一服务商、密钥、分组和账号唯一标识规范化。
- 已建立 `application/AccountService` 和 `GroupService`，账号及分组写操作支持事务回滚。
- 主窗口的新增、编辑、删除、HOTP、账号置顶、批量分组、API 新增和导入已接入服务边界。
- 已迁移基础 pytest 测试，并通过源码编译、项目自测和 EXE 构建启动检查。

## 已完成的第二轮

- `infrastructure/vault_repository.py` 和 `settings_repository.py` 已接入主窗口，保存入口不再直接调用 JSON 文件实现。
- `infrastructure/api_service.py` 已承接 API 业务规则；主窗口 `_handle_api_request` 现在只做服务委托。
- `infrastructure/api_server.py` 已承接本机 HTTP 认证、路由、请求体限制和线程生命周期，旧传输实现已从主程序移除。
- `infrastructure/crypto.py` 已抽取 PBKDF2/AES-256-GCM envelope 编解码，保持 `authenticator-desktop/v1` 格式不变。
- `application/vault_service.py` 已统一保险库加载、锁定、解锁和密码修改的生命周期边界，并在密码保存失败时恢复加密状态。
- `domain/otp.py` 已承接 OTP 计算，TOTP/HOTP 向量测试脱离 Tkinter 执行。
- 新增仓储、加密、API 服务、HTTP 传输、OTP 和保险库生命周期测试，目前共 20 个测试通过。

## 已完成的第三轮

- `domain/entities.py` 和 `domain/validators.py` 已承接账号、分组、URI、时间和类型规范化；兼容入口仍导出旧类名。
- `application/search_service.py` 和 `application/import_export.py` 已承接搜索排序和导入解析。
- `infrastructure/vault_store.py`、`settings_store.py`、`paths.py` 和 `errors.py` 已承接保险库、设置、路径和持久化错误。
- `presentation/styles.py` 已集中管理清新毛玻璃主题；`presentation/view_models.py` 统一完整界面与轻量模式的筛选、分组和最近账号状态。
- `presentation/dialogs/` 已拆分密码、账号编辑、分组、导入、设置和二维码区域选择器。
- `presentation/compact_window.py` 已独立轻量模式窗口；`presentation/main_window.py` 已成为主窗口控制器，旧 `authenticator_desktop.py` 只保留兼容入口和自测。
- 扫码截图与解码已通过 `BackgroundTaskRunner` 在工作线程执行，结果回调由 Tk 主线程队列消费。
- 当前主窗口控制器约 1,636 行，仍需进一步按账号、分组、保险库和布局职责拆分至计划目标的 300～500 行。

## 已完成的第四轮

- `presentation\main_window.py` 已成为唯一主窗口实现，`authenticator_desktop.py` 仅保留兼容导出、自测和启动入口。
- `presentation\dialogs\` 已进一步包含账号编辑和二维码区域选择器；`presentation\compact_window.py` 独立轻量模式 UI。
- `presentation\view_models.py` 新增 `AccountRowPresenter`，统一验证码缓存、倒计时和 Treeview 行模型。
- `infrastructure\paths.py`、`vault_store.py`、`settings_store.py` 负责路径、保险库和设置实现，主窗口依赖仓储及服务接口。
- 完整界面与轻量模式共享 `MainViewModel`/`CompactViewModel` 搜索、分组和最近账号状态。
- 当轮 25 个 pytest、内置自测、compileall、PyInstaller 构建和 EXE 启动冒烟均通过。

## 已完成的第五轮

- `presentation/main_window.py` 已缩减为约 150 行的依赖装配类。
- 主窗口职责拆分到 `presentation/mixins/` 下的布局、生命周期、账号列表、账号操作、分组、导入导出和保险库控制器。
- `presentation/api_controller.py` 负责 API 服务生命周期与 Tk 主线程消息消费。
- `application/import_service.py` 统一导入账号/分组、重复检测、ID 冲突处理、持久化与完整回滚；UI 不再直接修改账号或分组集合。
- `infrastructure/api_dtos.py`、`api_router.py`、`api_server.py` 和 `api_service.py` 分别承接消息类型、纯路由、HTTP 传输和业务响应。
- `VaultService` 已通过 `VaultRepository` 执行加载、锁定、解锁和密码修改，不再绕过仓储边界。

## 已完成的第六轮

- 保险库初次读取、PBKDF2 密码派生、解锁、导入解析和文件导出已接入 `BackgroundTaskRunner`。
- 后台线程不操作 Tk 控件；结果和错误由 Tk 主线程定时消费。
- 耗时任务期间暂停账号刷新并使 API 返回未就绪状态，避免并发读取正在变更的保险库。
- 二维码截图与解码继续复用同一任务执行器；退出时会停止接收新任务并清理执行器。

## 已完成的第七轮

- `infrastructure/logging_config.py` 提供小容量滚动日志，只记录生命周期和异常，不记录账号、密钥或 API 令牌。
- `app.py` 成为唯一稳定入口，兼容启动器只调用 `app.main()`。
- `--self-test` 调用 `tests/packaged_self_test.py`，可在源码和打包 EXE 中检查关键运行依赖。
- `pyproject.toml` 已配置 pytest、ruff 和 mypy；当前 53 个源码文件通过类型检查。
- 测试已直接引用分层模块，仅保留一个兼容启动器契约测试。

## 参考图 UI 重构

- 完整界面已重构为顶部应用栏、响应式混合侧栏、四张统计卡、共享 Canvas 数据表和底部操作栏。
- 验证码与密码本分别保留搜索、导航范围、选择和滚动状态；轻量悬浮窗布局保持不变。
- `presentation/canvas_table.py` 统一两类数据表的固定表头、局部刷新、单选、多选、键盘和命中区域行为。
- `presentation/navigation_sidebar.py` 和 `dashboard_widgets.py` 分别承接范围筛选与统计展示，Canvas 不读取保险库。
- 操作图标和服务商图标以本地 SVG 源码及预渲染 PNG 保存，EXE 运行时不联网、不加载 SVG 渲染器。
- `scripts/capture_ui_snapshots.py` 使用隔离数据生成 `960x640`、`1280x720`、`1600x900` 两模块回归截图。

## 当前测试基线

- pytest 覆盖 OTP、密码生成、v2 强制加密仓储、DPAPI、旧库迁移、双模式备份、设置容错、账号/密码及两套分组的事务回滚、API、扫码、后台任务、ViewModel 和 Canvas 表格交互。
- `python -m ruff check .` 通过。
- `python -m mypy` 通过。
- `python -m compileall` 与两种兼容入口的 `--self-test` 通过。
- `build_exe.py` 在打包前执行全部质量检查，打包后执行内置自测和真实 EXE 启动冒烟。
- 2026-08-29 参考图 UI 发布验收已通过；当前补丁版本 `1.2.3` 使用 8 倍矢量路径采样、圆头笔画和行背景预合成进一步改善倒计时圆环，并将全部运行数据固定保存到 EXE 同级的 `data` 文件夹；EXE 大小 20.49 MiB，完整构建耗时 49.6 秒。
- 2026-08-29 源码版本升级为 `1.3.0`：本地敏感数据强制加密、DPAPI 自动解锁、旧库迁移及加密/明文双模式备份已完成；72 个 pytest、Ruff、Mypy 和源码编译通过，本阶段按要求未构建 EXE。
- 2026-08-26 代码审核补充：移除未使用的 UI 校验/状态代码；账号服务现在统一校验分组引用完整性，避免绕过 UI/API 时写入悬空分组 ID；审核后的 36 个 pytest、Ruff、Mypy、源码编译和两种入口自检均通过。
- 2026-08-28 密码本模块发布验收通过：版本 `1.1.0`，50 个 pytest、Ruff、Mypy、源码编译、打包内自测和 EXE 启动冒烟通过；EXE 大小 `19.44 MiB`，完整构建耗时 `47.2s`。

## 兼容性要求

- 保持 `authenticator-desktop/v1` 格式标识；本地强制加密信封升级到 `version: 2`，并兼容读取迁移旧版明文和加密数据。
- 保持 AES-256-GCM、PBKDF2 参数和旧版数据读取能力。
- 保持本机 API 路径、认证请求头和主要状态码。
- 保持 Tkinter，不引入新的 UI 框架。
- 当前阶段只执行源码单元测试、Ruff、Mypy 和源码编译；收到单独构建指令后再执行 EXE 检查。

## 目标目录

```text
domain/          领域对象和纯业务规则
application/     账号、分组和保险库应用服务
infrastructure/  文件、加密、扫码和 API 适配器
presentation/    主窗口、轻量窗口、对话框和样式
tests/           自动化测试
```

## 发布验收命令

```powershell
python -m pytest
python -m ruff check .
python -m mypy
python -m py_compile app.py
python build_exe.py
```

每次发布均须完整执行以上流程。涉及窗口布局的变更还需在 960x640 完整界面和 420x360 轻量窗口进行人工视觉检查；自动化测试负责保护可脱离 Tk 控件验证的状态和业务行为。
