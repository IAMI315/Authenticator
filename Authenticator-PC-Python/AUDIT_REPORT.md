# 重构审核记录

审核日期：2026-08-26  
审核范围：`Authenticator-PC-Python` 的全部运行时代码、自动化测试、入口、构建脚本和 `REFACTOR_PLAN.md`。

## 结论

项目已实质性完成 `REFACTOR_PLAN.md` 所列八个阶段的重构，而非仅做目录拆分。入口、领域规则、事务写操作、文件与加密、API、后台线程和 Tkinter 界面职责已形成可验证边界；当前代码规范检查、类型检查和自动化测试均通过。

本次审核修复了一项应用层完整性缺口：此前 `AccountService` 没有自行拒绝不存在的分组 ID，虽然现有 UI、导入和 API 路径大多会预先校验，但脚本或未来调用方仍可能留下悬空引用。该校验现已收敛到账号服务，并由回归测试保护。

## 对照重构计划

| 计划目标 | 审核证据 | 结论 |
| --- | --- | --- |
| 稳定入口与兼容启动器 | `app.py` 是唯一实际入口；`authenticator_desktop.py` 只转发 `app.main`。 | 符合 |
| 四层目录与依赖方向 | `domain` 不导入 Tkinter/HTTP/文件；`application` 不导入 Tkinter；`presentation` 组合服务和控件；`infrastructure` 承担文件、加密、HTTP、扫码。 | 符合 |
| 账号/分组写操作事务化 | `AccountService`、`GroupService` 深拷贝状态，在保存失败时回滚；UI 没有直接写 `vault.entries/groups`。 | 符合，且补强未知分组校验 |
| 保险库、设置和加密边界 | `Vault` 负责 `authenticator-desktop/v1`、PBKDF2/AES-GCM 和临时文件原子替换；仓储适配器由 `VaultService`/主窗口使用。 | 符合 |
| API 分层与主线程安全 | `ApiRouter` 路由，`LocalApiServer` 认证/传输，`ApiController` 队列回收，`ApiService` 在主线程处理业务。 | 符合 |
| 主窗口职责拆分 | `MainWindow` 主要负责依赖装配；布局、生命周期、列表、账号、分组、导入导出、保险库控制分别位于 mixin。 | 符合 |
| 后台任务与 Tk 线程隔离 | `BackgroundTaskRunner` 在线程池执行工作，`drain()` 在 Tk 主线程执行回调；保险库加载、解锁、导入解析、导出和扫码遵循该边界。 | 符合 |
| 质量门禁与打包自检 | Pytest、Ruff、Mypy、编译和两个 `--self-test` 入口均可复现通过；`build_exe.py` 包含 PyInstaller 和 EXE 启动检查。 | 符合 |

## 本次代码调整

| 调整 | 原因 | 保护方式 |
| --- | --- | --- |
| `AccountService._normalise_known_group_ids()` | 把分组存在性验证移到统一账号写边界，避免 UI/API 预校验被绕过。 | 新增 `test_account_service_rejects_unknown_group_references_without_persisting`。 |
| 删除 `GroupActionsMixin._save_vault()`、`_validate_group_name()` | 两者无调用，且后者重复了 `GroupService` 的规则，容易产生两个校验来源。 | 静态引用搜索、完整测试集。 |
| 删除 `_compact_previous_topmost` | 状态从未被读取，保留会误导维护者。 | 静态引用搜索、完整测试集。 |
| 中文维护注释和维护指南 | 说明层次、类型、状态机、线程规则、事务和定位入口，降低后续修改成本。 | AST 文档字符串审计覆盖全部运行时代码的模块、类和函数。 |

## 验证结果

```text
python -m pytest                                      36 passed
python -m ruff check .                                All checks passed
python -m mypy                                        Success: no issues found in 53 source files
python -m compileall app.py application domain infrastructure presentation tests
                                                    completed successfully
python app.py --self-test                             passed
python authenticator_desktop.py --self-test           passed
```

## 剩余注意项

- JSON、Tkinter 回调、二维码图像和可替换仓储工厂的边界仍保留少量 `Any`；这是外部/动态接口的隔离点，不应扩散回账号、分组、搜索和视图模型的核心规则。
- 本次没有运行 `build_exe.py`，因为它会重建并覆盖 `build/`、`release/` 中的现有打包产物；代码注释不会改变窗口布局，故未重新做 960x640/420x360 人工视觉验收。发布前仍应运行该脚本及计划中的人工窗口检查。
- 本次未发现会阻断发布的代码缺陷。后续新增功能时，应优先在领域/应用层补测试，再从展示层接入，避免重新出现 UI 直接写保险库或工作线程操作 Tk 的情况。
