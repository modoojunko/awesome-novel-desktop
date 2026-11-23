## Context

2026-09-19 起七条测试类 workflow 被 `disabled_manually`（额度紧张），仓库 CI 从此不跑任何测试门禁。c-og-slim-v2 的自审实锤了代价：剧情推演兜底引用已删除变量（`NameError`，`ruff F821` 类）进 main，本机门禁三件套全绿没拦住——测试执行面退化为本机自律。当前时点：卷下拆卷拆章＋章纲字段瘦身均已合 main，隔离栈全量 e2e 193 passed / 0 failed（后 192/1 flaky/0），测试套件处于历史最健康时点——恢复窗口。

两条首批恢复的 workflow YAML 完好（`client-backend-ci.yml`：ruff check . ＋ pytest；`client-frontend-ci.yml`：license gate ＋ tsc ＋ vitest --coverage ＋ build），禁用是 GitHub 侧的 workflow state（`disabled_manually`），不在 YAML 里。

## Goals / Non-Goals

**Goals**
- 两条 workflow 回到 `active`，在 main 与 PR 上正常触发并绿。
- 额度护栏：同分支新推取消旧跑（concurrency）、push 触发收窄到 main（PR 触发保留），把浪费面压到最小。
- 后端 ruff 步骤显式追加 `--extend-select F811,F821,F841`（c-og-slim-v2 的 P1 教训：F821 类在默认 F 集里，但显式列出防降级；用 --extend-select 而非 --select，后者会整体替换默认集丢掉 E4/E7/E9）。

**Non-Goals**
- 不恢复 S端 两条/打包/Docker/e2e-scheduled（待额度观察，分批恢复）。
- 不改两条 workflow 的测试覆盖内容（除 ruff 显式 select 外）。
- 不引入新的门禁工具。

## Decisions

**D1 用 GitHub API 启用（不改 YAML 触发语义），护栏进 YAML。**
`disabled_manually` 是 UI/API 层状态（YAML 无 `disabled` 字样），用 `PUT /actions/workflows/{id}/enable` 恢复；护栏（concurrency ＋ push 收窄 main）以 YAML commit 落地，一次 commit 同时完成「启用＋护栏」。

**D2 额度护栏的三个抓手（按性价比排序）。**
① `concurrency`：同分支同 workflow 新推取消旧跑（PR 场景收益最大）；② push 触发收窄 `main`（分支上的双跑取消，PR 触发保留）；③ 依赖 `actions/setup-*` 的 cache 已有，不再加层。不做：self-hosted runner（运维成本不匹配单人仓库）、定时清理（无 nocturnal 堆积）。

**D3 验收基线＝main 树逐字节一致。**
c-og-slim-v2 合入后 main 树（`2ee490cd`）与已验证分支树逐字节一致（本机三件套全绿已跑），恢复的 CI 在同一棵树上跑，预期双绿；若红则为 CI 层新问题，在本 change 内排查不外推。

## Risks / Trade-offs

- [额度再次紧张] → 两条例行跑量小（paths 过滤＋concurrency 取消旧跑）；若 GitHub 额度页再报尽，按既有先例重新禁用并在 memory 登记，不阻塞合并。
- [恢复后首跑撞上 runner 层波动（steps=0 类）] → 与既有 6 个红 check 同签名，不属于本 change 引入；重跑一次区分。

## Migration Plan

单 commit（YAML 护栏）＋ API 启用 → main dispatch 双条件 → 预期双绿。回滚＝revert ＋ 重新 disable。

## Open Questions

（无）
