# ci-gates-restore — 恢复 C端 两条测试 workflow 回归门禁（ruff/pytest/vitest 回 CI 设防）

## Why

2026-09-19 起七条测试类 workflow 被 `disabled_manually`（当时 Actions 额度紧张），仓库 CI 从此不跑测试门禁。后果在 c-og-slim-v2 的自审中被实锤：剧情推演兜底引用已删除变量（`NameError`，ruff `F821` 可拦）直接进了 main——本机门禁三件套全绿没拦住，因为测试的实际执行面退化为本机自律。**卷下拆卷拆章＋章纲字段瘦身均已合 main**（本机隔离栈全量 e2e 193 passed / 0 failed），测试套件处于历史上最健康的时点，正是恢复 CI 设防的窗口。首批恢复 C端 两条（后端 CI ＋ 前端 CI），S端 与打包类维持禁用待额度观察。

## What Changes

- **恢复两条 workflow 的 `state`**：`client-backend-ci.yml`（ruff check . ＋ pytest tests/）与 `client-frontend-ci.yml`（vitest/tsc/design:lint）——从 `disabled_manually` 改回 `active`（GitHub API `PUT /actions/workflows/{id}/enable`，不改 YAML 内容）。
- **预算护栏**（防再次额度爆掉）：两条 workflow 增加 `concurrency` 组（同分支新推取消旧跑）；`pull_request` 触发保留、`push` 触发收窄为 `main`（避免分支推激起双跑）；不为省额度降测试覆盖。
- **门禁内容升级一处**：后端 CI 的 ruff 步骤显式追加 `--extend-select F811,F821,F841`（c-og-slim-v2 的 P1 兜底 NameError 正是 F821 能拦的类别；--extend-select 在默认集之上追加，SHALL NOT 用 --select 整体替换默认集）。
- **验收基线**：恢复后在 main 上 dispatch 两条件，预期双绿（main 树 ＝ 已验证分支树逐字节一致，本机三件套全绿）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——CI workflow 的启停属仓库基建，无产品行为契约变化；故设 `skip_specs: true`。）

## Impact

- `.github/workflows/client-backend-ci.yml`、`client-frontend-ci.yml`（concurrency/触发收窄）；GitHub Actions workflow state（API 启用）。
- 额度：两条 workflow 均为 ubuntu-latest 标准跑道（后端 ~3 分钟/次、前端 ~5 分钟/次），按 paths 过滤后日触发频次低；如额度仍紧张，`concurrency`＋push 收窄已把浪费面压到最小。
- 已知限制：仓库 Actions 当前 6 个 check 因 runner 层原因（`steps=0`、日志 404）全红——**main 同样全红**，与本 change 无关；恢复的两条此前也是被禁用状态，不在红 check 之列。
