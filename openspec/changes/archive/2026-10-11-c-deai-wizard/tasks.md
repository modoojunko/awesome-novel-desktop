# Tasks: c-deai-wizard

## 1. 后端（client/backend）

- [x] 1.1 `write/ai_flavor_scan.py`：`scan_prose`（规则：multi_period/para_head_repeat/canned_reaction/simile_word/not_a_but_b/trailing_tag/quote_sandwich/dash_ban/ellipsis_misuse/halfwidth_punct/nested_quotes/count_words_claim + 软指标 comma_period_ratio/short_para_ratio/dialogue_ratio）＋`RULE_LABELS` 文案表＋`build_problem_segments`（双源合并）＋`quick_verdict`
- [x] 1.2 `write/router.py`：`POST /ai-flavor-scan`（login；读章＋读朱雀存档合并；章 404／空正文 400／损坏存档降级规则模式）；polish 响应附 `changed`/`flags`/`flags_blocking`
- [x] 1.3 测试 `tests/test_ai_flavor_scan.py`：26 条（规则逐条＋合并＋quick_verdict＋端点冒烟＋评审盲区钉：平衡引号/知道味道/章级指标排除/引号内省略号/损坏存档/缺章 404）

## 2. 前端（client/frontend）

- [x] 2.1 `workbench/polishWizard/types.ts`＋`applyParagraphEdits`（ProsePane 内部：逆序单 chain＋双写 store＋段文本漂移防护）
- [x] 2.2 `workbench/polishWizard/PolishWizard.tsx`：Modal 壳＋四步状态机＋四面板＋编排（串行＋inflight 防重入＋关闭保护：adopted>0 / undecided>0 / 全保留静默 三路径）
- [x] 2.3 质量兜底接线：polishTextDetail 完整出参（changed=false → 合规保留卡＋默认 keep；flags_blocking → 红字＋默认 keep；advisory 黄条）；步骤④终选翻转（flip）；segContext 上下文保鲜（已采用候选拼回后续段上下文）
- [x] 2.4 `AiAssistPanel` 入口行＋门禁矩阵（free 锁／未配模型禁用／检测中·stale·空章·归档禁用，hint 逐态）；`lib/ai.ts`：aiFlavorScan＋polishTextDetail＋polishText（既有调用方不变）
- [x] 2.5 测试 `__tests__/PolishWizard.test.tsx` 7 条（四步走通只写采用段／空应用禁用／漂移拒写／关闭保护／规则模式无朱雀露出／重试）

## 3. 闸门与评审

- [x] 3.1 前端：tsc clean；vitest 全量 1499 passed（124 files）；vite build 成功。后端：受影响套件＋全量（真 CI 口径）2001→2059 passed 0 failed；ruff clean
- [x] 3.2 三路设计评审（PE/FE/PM，汇总见 drafts/修稿向导-三路评审汇总.md）＋实现后 Code Reviewer 复审轮（PASS-WITH-FINDINGS：上轮 7 findings 全 FIXED-VERIFIED；新发现 N1/N2/MINOR-5 已修，N3 备案）＋PE 接口契约复核（四项裁决 CONFIRMED；MAJOR-1 映射失效已修）
- [x] 3.3 提交推分支＋PR #828/#830 已合入 main（#830＝移除选区去AI味旧入口，向导归一）

## 4. 验收（真机/演示栈）

- [x] 4.1 真机走一轮：检测 → 向导四步 → 应用 → 顶部重检看人味变化（5274 多轮走查，2026-10-11 确认界面定稿）
- [ ] 4.2 PRO 无检测存档：规则模式全程无朱雀数据露出
- [ ] 4.3 空应用（全保留原文）：不置 stale、不弹「正文已更新」
