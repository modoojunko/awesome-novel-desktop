# Tasks: c-deai-wizard

## 1. 后端（client/backend）

- [ ] 1.1 `write/ai_flavor_scan.py`：`scan_prose`（规则：multi_period/para_head_repeat/canned_reaction/simile_word/not_a_but_b/trailing_tag/quote_sandwich/dash_ban/ellipsis_misuse/halfwidth_punct/nested_quotes/count_words_claim + 软指标 comma_period_ratio/short_para_ratio/dialogue_ratio）＋`RULE_LABELS` 文案表＋`build_problem_segments`（双源合并）＋`quick_verdict`
- [ ] 1.2 `write/router.py`：`POST /ai-flavor-scan`（login；读章＋读朱雀存档合并）；polish 响应附 `changed`/`flags`
- [ ] 1.3 测试 `tests/test_ai_flavor_scan.py`：规则逐条＋合并＋quick_verdict＋端点冒烟

## 2. 前端（client/frontend）

- [ ] 2.1 `workbench/polishWizard/types.ts`＋`applyProseSegments.ts`
- [ ] 2.2 `workbench/polishWizard/PolishWizard.tsx`：Modal 壳＋四步状态机＋四面板＋编排（串行＋预取＋abort＋关闭保护）
- [ ] 2.3 `ProsePane`：`ProseHandle.applyParagraphEdits`（逆序单 chain＋双写 store）
- [ ] 2.4 `AiAssistPanel`：入口行＋门禁矩阵；`ChapterWorkspace` 装配；`lib/ai.ts` 扩展
- [ ] 2.5 测试 `__tests__/PolishWizard.test.tsx`：开窗即扫/勾选/逐段取舍/应用写回

## 3. 闸门与评审

- [ ] 3.1 ruff＋后端受影响套件绿＋前端 tsc/vitest 绿
- [ ] 3.2 Code Reviewer 审全量 diff＋PE 复核接口契约；findings 修复
- [ ] 3.3 提交推分支＋PR
