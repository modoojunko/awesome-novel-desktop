# c-mac-relaunch-frontmost · 验收登记

## 1.1 界面影响判定

本 change 无 React 屏改动、无应用内文案（纯 OS 级窗口行为：壳层自激活），依据
proposal「Design Impact」免原型先行；若未来改为应用内横幅提示，另补原型。

## 4.1 后端全量（CI 口径）

- 命令：`python -m pytest tests/ -q --timeout=30`（与 .github/workflows/client-backend-ci.yml:52 逐字一致）
- 结果：**2530 passed, 303 skipped** in 196.32s（0:03:16），退出码 0
- 本 change 新增 4 用例（test_packaging_shell_apply.py 28/28：存量 24＋新增 4）

## 4.2 门禁结论登记

- 未触 `client/frontend`（零文件改动）→ design:lint／design:check／tsc／design-cross
  不涉，照 c-update-detached-ps-fix 4.2 precedent 登记「未触前端、命令不涉」。
- ruff（CI 闸＝`ruff check --extend-select F811,F821,F841 .`，仅扫 client/backend）：
  闸内文件（tests/test_packaging_shell_apply.py）**All checks passed**。
- 壳层文件（client/packaging/build/pywebview_app.py）在 CI ruff 闸**之外**（存量债
  53 条，main 同 hash 判例在案）；A/B 对拍（ruff 0.16.3，concise 全规则）＝本 change
  新增 1 条 BLE001（`_activate_to_front` 的吞异常留痕），与文件既有 8 处同族同风格
  （该文件设计原则＝激活/等待失败只留痕不炸启动链），不进任何门禁。

## 5.4 OpenSpec 归档随实现 PR

- `openspec archive c-mac-relaunch-frontmost --yes`：MODIFIED delta 已 sync 进
  `openspec/specs/client-auto-update/spec.md`（「退出链静默安装」增补前台可见性条款＋
  「自动拉起窗口必须到前台」场景，主 spec 既有 8 场景全量保留），change 移入
  `openspec/changes/archive/2026-10-26-c-mac-relaunch-frontmost/`。
- `openspec validate c-mac-relaunch-frontmost --strict`（归档前）：**valid**。
