# c-relaunch-version-selfreport · 验收登记

## 1.1 界面影响判定

无 React 屏改动、无应用内文案（进程环境与版本自报），依据 proposal「Design Impact」
免原型先行。

## 4.1 后端全量（CI 口径）

- 命令：`python -m pytest tests/ -q --timeout=30`（与 client-backend-ci.yml 逐字一致）
- 结果：**2548 passed, 308 skipped** in 192.35s，退出码 0
- 本 change 新增 4 用例（test_packaging_shell_apply.py 36/36：存量 32＋新增 4）
- **存量同批更新 2 处**（test_config_release.py 注入段实跑哨兵）：`_env_with_release`
  冻结判别式真源码依赖 `sys.frozen`，两条 exec 哨兵的受限 globs 补 `"sys": sys`
  （判例在案：注入段结构变了本测试须同批更新；exec 环境如实供给生产依赖的名字）

## 4.2 门禁结论登记

- 未触 `client/frontend` → design:lint／design:check／tsc／design-cross 不涉。
- ruff（CI 闸＝`--extend-select F811,F821,F841 .`）：闸内 tests/ **All checks passed**。
- 壳层文件（CI ruff 闸外）：ruff 0.16.3 concise A/B 对拍 main 57 → worktree 57，
  **零新增**（规则家族同构、仅行号位移）。

## 5.3 OpenSpec 归档随实现 PR

- `openspec archive c-relaunch-version-selfreport --yes`：ADDED requirement「更新拉起
  新实例的版本自报」（含三场景）已 sync 进 `openspec/specs/client-auto-update/spec.md`，
  change 移入 `openspec/changes/archive/<date>-c-relaunch-version-selfreport/`。
- `openspec validate c-relaunch-version-selfreport --strict`（归档前）：**valid**。

## 实现备注

- `_env_with_release` 冻结判别式**内联不引 helper**：该函数源码行被
  test_config_release 两条 exec 哨兵抽到受限 globs 实跑，呼患外部名字即 NameError
  （首版调 `_is_frozen()` 即撞，已改内联＋判例入档）。
- 冻结语义对七个烘焙键一并对齐：SERVER_API_BASE(_FALLBACK)／PUBLIC_SERVER_API／
  PORTAL_URL／CLIENT_VERSION／CLIENT_UPDATE_URL(_FALLBACK)；dev 态 env 覆盖与
  「dev」回退语义不变（spec 场景 3）。
