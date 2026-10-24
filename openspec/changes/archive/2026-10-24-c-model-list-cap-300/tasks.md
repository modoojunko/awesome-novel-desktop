# Tasks: c-model-list-cap-300

## 1. 后端

- [x] 1.1 `api_configs/service.py`：`_normalize_models` 上限常量 100→300（自动截断窗与手动报错阈值同源），报错文案「上限 100」→「上限 300」。验证：新增 pytest——自动路径 137 条（火山形状）全量落库且尾部新模型在场、手动路径 301 条报 422/ValueError、边界 300 恰好通过、截断时保头仍置首。
- [x] 1.2 存量测试同步：既有钉「上限 100」的用例改为 300 口径；后端全量 pytest 绿（worktree 独立 venv，PROMPT_PACK_DEV_DIR 带源）。验证：`pytest` 0 红＋ruff 绿。

## 2. 前端

- [x] 2.1 `lib/imageApi.ts` 火山预设 models 头换 `doubao-seedream-5-0-flash-260915`（`5-0-260128`/`4-5`/`4-0` 兜后保留）；原型 `docs/design-c/prototypes/model-config.html` IMG_PROVIDERS 同批；`ADJUSTMENTS.md` 登记条目（预设换在役款＋清单容量 300 说明）。验证：面板单测断言预设首项；原型 JS 语法过。
- [x] 2.2 门禁：vitest 全绿、`tsc --noEmit` 绿、`design:lint`＋`design:check`（parity 8）绿。验证：命令 0 红。

## 3. 收尾

- [ ] 3.1 openspec sync delta→主 spec、change 移档 archive，随实现 PR 同批带上（sync 前 fetch 确认基线）。验证：`openspec validate` 绿。
- [ ] 3.2 PR＋CI 双绿；真机验收＝豆包配置重测连接后清单含 `doubao-seed-2-1-pro-260915`/`doubao-seed-evolving`，图像弹窗预填为 flash。验证：用户侧抽检或 demo 栈换包后自测。
