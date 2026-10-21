# Proposal — c-mac-autoupdate（macOS 自动更新链＋bundle 版本元数据）

## Why

1. **Mac 装机 bundle 版本号恒 0.0.0**（2026-10-21 真机实锤：`/Applications/AwesomeNovel.app/Contents/Info.plist` 的 `CFBundleShortVersionString`＝`0.0.0`）——病灶＝`build.spec` 的 `BUNDLE(...)` 从未传 `info_plist`，PyInstaller 落默认值。运行时后端自报版本（release.json 烘焙 0.36）是对的，但 Finder「显示简介」与系统层面恒 0.0.0。`win_version_info` 模块头注释里「mac 侧主体元数据另行立项」指的就是这块。
2. **macOS 不触发自动更新**：自动链在两处被硬闸拦死——`update_check.py:245` `_PLATFORM_KEY = {"win32": "win"}`（darwin 查表得 None）与壳层 `apply_pending_update` 的 `sys.platform != "win32"` 一票否决。而发布侧清单 v2 早已带 `platforms.mac`（DMG url/sha256/size，双平台发版流水线必产），前端三态横幅零平台分叉——只差客户端开闸。Mac 用户现状＝看横幅手动去官网下载，与 Windows 的「重启更新」一键体验断层。

## What Changes

- **macOS bundle 版本元数据**：`build.spec` 的 `BUNDLE` 传入 `info_plist`（`CFBundleShortVersionString`/`CFBundleVersion`＝同源版本，复用 `win_version_info` 的版本单源——`_detect_version` 转公开 `detect_version`：APP_VERSION env > git describe > 0.0.0，tag 去 v 前缀）；`build_mac.sh` 把已算出的 APP_VERSION export 给 PyInstaller；CI 增打包期断言（PlistBuddy 对拍 tag 版本），坏包在流水线红而不是上真机才发现。
- **macOS 自动链开闸**：`_PLATFORM_KEY` 增加 `darwin → "mac"`（清单键与发布链一致）。
- **macOS 静默替换安装（壳层退出链 darwin 分支）**：与 Windows runner 同构的 detached bash runner——等本进程死透（有界 60s）→ 挂载暂存 DMG（`hdiutil attach -nobrowse -readonly`）→ `ditto` 复制 .app 到同卷暂存名 → `codesign --verify --strict` 硬闸 → 同目录 `mv` 原子换装（旧 bundle 先挪 `.old` 备份，失败回滚）→ 卸载 DMG → 安装成功才 `open` 拉起新版。安装目录钉死当前 bundle 所在位置（数据随目录走铁律的 mac 形态）；安装目录不可写（非 admin 装到 /Applications 等）在退出链预检即静默跳过回手动链。等待段结果＋安装结果照 Windows 口径留痕 `installer-runner.log`（「暂不」清理保留名单沿用）。
- **共享段零改动**：TTL／重试上限／sha256 完整复验／pending 唯一属主／启动期 `_reconcile_pending` 版本对拍记账——全部平台无关，原样复用。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `client-auto-update`：MODIFIED——「退出链静默安装」从仅 Windows 扩为 Windows（Inno 安装器）与 macOS（DMG 挂载＋bundle 原子换装）双平台执行体；「构建形态与平台边界」的平台边界同步收窄到其余平台。
- `installer-release`：ADDED——macOS bundle 版本元数据（plist 版本字段与发布版本同源单源＋打包期断言）。

## Impact

- `client/backend/update_check.py`：平台键一行＋注释。
- `client/packaging/build/pywebview_app.py`：darwin 分支（bundle 解析、可写预检、bash runner 生成与 spawn）。
- `client/packaging/build/build.spec`／`build_mac.sh`／`win_version_info.py`：plist 版本注入。
- `.github/workflows/client-package.yml`：mac 打包期 plist 版本断言步。
- 测试：`test_packaging_shell_apply.py`（darwin 用例组＋存量 darwin 平台闸用例改 linux）、`test_update_check.py`（darwin 平台键）。
- 兼容性：旧版 Mac 客户端（≤0.37）行为不变（手动链）；0.38 起自动链生效——首个真实闭环验收锚 **0.37→0.38 或 0.38→0.39 真机**。Windows 链路零触碰（同函数分平台分派，Win 分支逐字节不动）。
