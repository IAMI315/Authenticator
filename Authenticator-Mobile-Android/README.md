# 验证器 Android

原生 Android 客户端使用 Jetpack Compose 展示界面，并通过 Chaquopy 复用桌面版的
Python 领域与应用服务。手机端不包含轻量悬浮窗和本机 HTTP API。

## 构建

本项目可直接在 Windows 构建，不使用 WSL 或 Docker。构建脚本默认从
`%LOCALAPPDATA%\AuthenticatorBuildTools` 查找 JDK 17 和 Android SDK：

```powershell
python build_apk.py
```

也可以在配置好 `JAVA_HOME` 后直接运行：

```powershell
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug
```

APK 输出到 `release\AuthenticatorMobile-1.4.25-arm64-v8a-debug.apk`。验证码、密码本和服务器档案可在
设置页分别选择排序字段和方向；验证码页会根据服务商字段动态显示常用服务商与“其他服务商”筛选，
不会写入或改变用户的自定义分组。扫码同时支持普通
`otpauth://` 二维码和 Google Authenticator 导出的批量迁移二维码；设置页也可以
生成 Google Authenticator 兼容的分页二维码供另一台设备扫描。
