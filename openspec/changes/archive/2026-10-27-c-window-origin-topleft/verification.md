# c-window-origin-topleft · 验收登记

## 1.1 界面影响判定

无 React 屏改动、无应用内文案（OS 级窗口初始坐标），依据 proposal「Design Impact」
免原型先行；若未来做位置持久化设置 UI，另按 design-language 补原型。

## 4.1 后端全量（CI 口径）

- 命令：`python -m pytest tests/ -q --timeout=30`（与 client-backend-ci.yml 逐字一致）
- 结果：**2543 passed, 304 skipped** in 202.20s，退出码 0
- 本 change 新增 4 用例（test_packaging_shell_apply.py 32/32：存量 28＋新增 4）

## 4.2 门禁结论登记

- 未触 `client/frontend` → design:lint／design:check／tsc／design-cross 不涉。
- ruff（CI 闸＝`--extend-select F811,F821,F841 .`，仅 client/backend）：闸内
  tests/test_packaging_shell_apply.py **All checks passed**。
- 壳层文件（client/packaging/build/pywebview_app.py，CI ruff 闸外）：ruff 0.16.3
  concise A/B 对拍 main 56 → worktree 57，唯一新增＝`_window_origin` 的 1 条
  BLE001（吞异常回退），与文件既有 10+ 处同族同风格（该文件设计原则＝位置/激活
  失败只降级留痕不炸启动链），不进任何门禁。

## 5.3 OpenSpec 归档随实现 PR

- `openspec archive c-window-origin-topleft --yes`：ADDED requirement「窗口初始位置
  锚定主屏左上角」（含三场景）已 sync 进 `openspec/specs/client-shell-startup/spec.md`，
  change 移入 `openspec/changes/archive/<date>-c-window-origin-topleft/`。
- `openspec validate c-window-origin-topleft --strict`（归档前）：**valid**。
