# C端 更新拉起新实例版本自报修复（c-relaunch-version-selfreport）

## Why

2026-10-27 真机定诊（v0.43 灰度跳，本机采证）：mac 更新链全绿（换装/收账/盘上 bundle
=0.43），但拉起的新实例**自报 0.42**。根因＝**CLIENT_VERSION 环境变量传染链**：旧实例
boot 时把版本写进自己 `os.environ`（`_env_with_release` 存量 env 优先、仅补缺不覆盖）→
mac runner 以 `{**os.environ}` 全量继承 → `open` 原样传给新实例 → 新实例 boot 取值
env 优先于烘焙 release.json（`pywebview_app.py:1357`）⇒ 自报旧版本。后果：版本徽章错、
`update-check.current` 停在旧版 ⇒ `has_update` 恒真 ⇒ 用户被无限重提更新、每次点都重装
一遍——**该缺陷卡住 v0.43 晋升**（生产 mac 用户 0.40→0.43 跳后必然复现）。Windows 路径
（Popen 隐式继承 → Inno → [Run]）理论上同链，是否被 Inno 中转洗掉待徽章采证；修法为
平台无关单点，双平台同批覆盖。

## What Changes

- **冻结态烘焙恒优先**：`_env_with_release` 在打包产物（frozen）下强制以 release.json
  烘焙值覆盖继承 env（dev/非冻结行为不变——env 覆盖与无烘焙回退「dev」全保留）。
- **boot 版本行同步**：main() 的 `client_version_at_boot` 冻结态下同样不再信任继承 env。
- **runner 剥 baked 键（双保险）**：抽 `_without_baked_env(env)`——从传给执行体的环境里
  剥掉烘焙派生键（`CLIENT_VERSION`、`CLIENT_UPDATE_URL(_FALLBACK)`、`SERVER_API_BASE
  (_FALLBACK)`、`PUBLIC_SERVER_API`、`PORTAL_URL`）；mac 显式 env dict 与 Windows Popen
  （补 `env=`）双平台同批生效。

**非目标**：不碰更新链时序/换装算法/留痕契约；不做多实例锁（另在 0.44 桶）；不改
lab_version 烘焙链（lab 值在构建期进 release.json，冻结恒优先后行为不变）。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `client-auto-update`：新增 requirement「更新拉起新实例的版本自报」——自动拉起的新实例
  SHALL 自报其真实烘焙版本，MUST NOT 继承上一版实例经执行体环境链传递的版本值；附场景。

## Design Impact

- 受影响端：C端（Windows/macOS 桌面壳进程环境与版本自报）；**无 React 屏改动**。
- 受影响屏/弹层：无；无文案。
- 共享段：无触碰。原型先行：不需要（OS 级行为，同 c-mac-relaunch-frontmost 口径）。
- 设计工件：实现侧自查。

## Impact

- `client/packaging/build/pywebview_app.py`：`_env_with_release` 冻结分支＋main() boot
  版本行＋`_without_baked_env` helper＋两平台 runner spawn 接线。
- 测试：`client/backend/tests/test_packaging_shell_apply.py` 增
  `_without_baked_env` 双臂＋冻结优先/非冻结保留两臂（后者经源码形状断言——闭包不可
  直接导入）＋Windows spawn env 接线形状断言。
- 真机验收：0.43.1 灰度跳后，Mac/Windows 新实例右下角徽章与 `update-check.current`
  均报 **0.43.1**（不再停留 0.43）。
- 兼容性：dev 态 env 覆盖（`AI_NOVEL_*`）与 lab 烘焙链零变化；不改更新清单/数据格式。
