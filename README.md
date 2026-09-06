# Authenticator

Windows 桌面版与 Android 版验证器的源码仓库。项目提供本地加密的 2FA 验证码与密码本管理功能。

为保护隐私，本仓库不包含任何用户保险库、设备密钥、主密码、API 令牌、剪贴板内容、日志、本机 SDK 路径或已构建的 EXE/APK 文件。

## PC 桌面版

- 源码目录：`Authenticator-PC-Python`
- 源码启动：`python app.py`
- Windows 构建：`python build_exe.py`

程序运行时会在 EXE 同级目录创建并使用 `data` 目录。该目录包含加密保险库和本机设备凭据，始终保持在本地，已被 Git 忽略。

## Android 版

- 源码目录：`Authenticator-Mobile-Android`
- 调试构建：`gradlew.bat assembleDebug`

Android 版本使用应用私有存储保存加密数据，不会把本地数据写入仓库。

## 数据安全

- 使用程序内的导入、导出功能迁移数据，不要手动提交 `data` 目录或备份文件。
- 加密备份、明文备份、日志和本机配置均在 `.gitignore` 中排除。
- 构建产物应通过发布渠道分发，不与源码或用户数据一同提交。
