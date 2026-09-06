# 验证器桌面版维护指南

本文配合源码中的中文模块说明、类说明和关键函数注释使用。它描述的是当前程序的实际边界和数据流，方便在定位问题或扩展功能前先找到正确的修改位置。

## 运行结构

```text
app.py
  -> presentation.main_window.MainWindow（依赖装配与 Tk 根窗口）
       -> presentation.mixins/*（界面事件、生命周期、列表、导入导出）
       -> presentation.dialogs/*（只收集/显示 UI 数据）
       -> application/*（账号、分组、导入、搜索、保险库业务规则）
       -> domain/*（实体、校验、OTP、唯一性规则）
       -> infrastructure/*（JSON、加密、文件、API、后台线程、扫码）
```

依赖方向应保持从 `presentation` 指向 `application/domain/infrastructure`。`domain` 不应导入 Tkinter、文件系统或 HTTP；`application` 不应直接操作 Tk 控件；HTTP 工作线程也不得读取或修改保险库对象。

## 主要类型与不变量

| 类型/对象 | 所在模块 | 维护时必须保持的约束 |
| --- | --- | --- |
| `OTPEntry` | `domain.entities` | `secret` 为去空格、去连字符后的密钥；`group_ids` 始终以 `default` 开头；TOTP/HOTP/Steam/Battle.net 的参数必须先经 `validate()` 校验。 |
| `AccountGroup` | `domain.entities` | `default` 是系统分组，名称固定为“默认分组”，不可改名或删除。 |
| `Vault` | `infrastructure.vault_store` | 磁盘格式固定为 `authenticator-desktop/v1`；写入采用临时文件加 `os.replace()`；加密时内存必须持有已解锁的派生密钥才能保存。 |
| `AccountService` | `application.account_service` | 任何账号写操作均经事务快照和保存回滚；不可由 UI 直接修改 `vault.entries`。 |
| `GroupService` | `application.group_service` | 分组创建、改名、删除、批量归属均经事务；删除分组只移除归属，不删除账号。 |
| `ImportService` | `application.import_service` | 账号、分组合并和保存视为一个整体；保存失败时恢复导入前的内存状态。 |
| `BackgroundTaskRunner` | `infrastructure.task_runner` | 工作函数运行在线程池；`on_success`/`on_error` 只能由 Tk 主线程调用 `drain()` 后执行。 |
| `ApiController` | `presentation.api_controller` | HTTP 服务只投递 `ApiRequest`；实际业务处理发生在 Tk 主线程的 `process()` 中。 |

## 常见修改入口

| 需求 | 首选修改位置 | 不应修改的位置 |
| --- | --- | --- |
| 新增 OTP 类型、URI 字段或校验规则 | `domain/entities.py`、`domain/validators.py`、`domain/otp.py` | 不要先在对话框或 API 中复制校验。 |
| 调整账号创建、编辑、删除或置顶 | `application/account_service.py` | 不要在 `presentation/mixins` 里直接写 `vault.entries`。 |
| 调整分组语义 | `application/group_service.py` | 不要只改 `GroupManagerDialog`。 |
| 支持新的导入格式 | `application/import_export.py`，随后由 `ImportService` 落库 | 不要在 UI 线程直接解析大文件或直接 append。 |
| 修改保险库格式/加密 | `infrastructure/vault_store.py`、`infrastructure/crypto.py` | 必须保持旧格式读取能力，并补充仓储/加密测试。 |
| 新增本机 API 路由 | `api_router.py` -> `api_server.py` -> `api_service.py` | HTTP 请求线程不能访问 `MainWindow` 或 `Vault`。 |
| 调整列表排序、筛选、行展示 | `application/search_service.py`、`presentation/view_models.py` | 不要把排序规则塞回 Tk Treeview 事件。 |
| 修改完整窗口交互 | 对应的 `presentation/mixins/*.py` | 不要把业务规则重新放回 `main_window.py`。 |

## 状态与线程

`MainWindow._busy` 表示保险库读取、解锁、导入解析、导出或修改密码等独占后台操作正在进行。此时 API 返回未就绪状态，界面写操作也会被拒绝。`BackgroundTaskRunner` 本身不接触 Tk；主窗口每 50 ms 调用 `drain()`，因此所有 UI 回调仍在主线程执行。

`Vault.encrypted` 表示文件格式需要密码；`MainWindow.locked` 表示当前内存没有可用账号数据。前者为真而后者为假时，保险库已解锁且可读写；两者均为真时只允许解锁。

## 诊断顺序

1. 先运行 `python -m pytest`、`python -m ruff check .`、`python -m mypy` 和 `python -m compileall app.py application domain infrastructure presentation`。
2. 数据或密码问题从 `Vault.load()`、`Vault.unlock()`、`decrypt_payload()` 和实体的 `from_dict()` 开始定位。
3. 写入失败先看服务层的 `_transaction()` 是否正确回滚，再看 `Vault.save()` 的异常。
4. API 问题依次检查 `ApiRouter.match()`、`LocalApiServer` 的认证/请求体解析、`ApiController.process()` 和 `ApiService.handle()`。
5. 界面卡顿或线程错误先看 `_run_background_operation()` 与 `BackgroundTaskRunner.drain()`，确认工作线程没有触碰 Tk 控件。

## 质量门禁

发布前执行：

```powershell
python -m pytest
python -m ruff check .
python -m mypy
python -m py_compile app.py
python app.py --self-test
python authenticator_desktop.py --self-test
```

`build_exe.py` 会额外生成/覆盖 `build/` 与 `release/` 中的打包产物，因此应在需要发布验证时再运行。
