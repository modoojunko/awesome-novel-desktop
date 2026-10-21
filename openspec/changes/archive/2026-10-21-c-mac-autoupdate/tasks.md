# Tasks — c-mac-autoupdate

## 1. macOS bundle 版本元数据

- [x] 1.1 `win_version_info.py`：`_detect_version` 转公开 `detect_version`（`collect` 同源调用，行为零变化）。
- [x] 1.2 `build.spec`：darwin onedir 分支 `BUNDLE(info_plist={CFBundleShortVersionString, CFBundleVersion})`。
- [x] 1.3 `build_mac.sh`：`export APP_VERSION`（本地构建与 CI 同名变量同源）。
- [x] 1.4 `client-package.yml`：mac 段 codesign 前增 PlistBuddy 版本对拍断言步。

## 2. macOS 自动链开闸

- [x] 2.1 `update_check.py`：`_PLATFORM_KEY` 增加 `darwin → "mac"`，注释更新（v1 仅 Windows → 双平台）。
- [x] 2.2 `pywebview_app.py`：`apply_pending_update` 平台分派——win32 原样；darwin 走新分支；其余忽略。
- [x] 2.3 darwin 分支：当前 bundle 解析（`sys.executable` 上溯三级，dev 态跳过）＋父目录探针可写预检（失败静默跳过留日志）。
- [x] 2.4 `_mac_install_runner_script`／`_spawn_install_runner`：bash 脚本生成（等尸有界 60s／DMG 挂载／ditto 复制／codesign --strict 硬闸／同卷原子换装＋回滚／卸载／成功才 `open`）＋ `start_new_session` 分离 spawn＋runner 日志一行留痕。

## 3. 测试与门禁

- [x] 3.1 `test_packaging_shell_apply.py`：存量 `test_non_windows_leaves_pending` 平台改 linux＋断言文案。
- [x] 3.2 darwin 用例组：正常路径脚本形状钉（等尸段／hdiutil attach／codesign --verify／mv 换装／open／runner 日志）＋attempts 递增；可写预检失败不 spawn；非 .app 形态跳过；relaunch 旗标透传。
- [x] 3.3 `test_update_check.py`：平台键映射含 darwin；darwin 键驱动触发闸用例。
- [x] 3.4 后端 pytest 全绿＋（前端零改动，tsc/vitest 不涉；ruff 涉改 py 文件显式跑）。

## 4. 归档与发布

- [x] 4.1 实现合入前 openspec 归档随本 PR（sync deltas → openspec/specs，变更移档 archives）。
- [ ] 4.2 真机验收锚（不阻塞合入）：0.38 发版后 Mac 端 0.37/0.36 → 横幅「新版本已就绪」→ 重启更新 → 新版自动拉起＋applied 记账；顺带验 Finder「显示简介」版本号非 0.0.0。
