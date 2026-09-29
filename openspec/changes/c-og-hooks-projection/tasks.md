# Tasks: c-og-hooks-projection

## 1. 后端：起草素材补伏笔信号

- [ ] 1.1 `chapters/ai_draft.py` ai_draft_outline：【活跃伏笔】块升级为 `render_hooks_block` 同口径——`[编号] 描述（优先级：X，类型：Y，建议本章收束）`；due_now 复用 `active_hooks_for_chapter` 既有产物
- [ ] 1.2 `prompts/outline_draft.prompt` system 字段口径补判据句：标「建议本章收束」的进 must_resolve，需继续按住的活跃伏笔进 must_hold
- [ ] 1.3 `tests/test_outline_ai_draft.py`：素材块断言——due 伏笔带「建议本章收束」、优先级/类型标签在场

## 2. 前端：台账取数共享与投影派生

- [ ] 2.1 新 `src/hooks/useHooksLedger.ts`：自 HooksPane 原样抽出 `/novels/{id}/hooks`＋卷章树取数与容错；`HooksPane.tsx` 改消费（渲染逻辑零变化）
- [ ] 2.2 新 `src/lib/hookHints.ts`：`ogHookHints(hooks, chapters, currentChId, currentChNo)` 纯函数——`mres`＝计划收 ≤ 本章的悬置伏笔（该收了标、计划收标签），`mhold`＝埋点 ≠ 本章的悬置伏笔（埋于标签，无埋点计「开书」）；回收格编辑候选＝全部悬置伏笔按该收了优先

## 3. 前端：OgPane 两态接入

- [ ] 3.1 查看态：两格为空时渲染台账投影（每条 `[编号] 描述（来源）`＋「来自伏笔台账 · 可在编辑章纲勾选为正式条目」注脚）；投影空时给理由句（无悬置伏笔／计划收不在本章或未设／均本章埋设）；格非空时维持原样
- [ ] 3.2 编辑态：两格文本域下挂候选 chips（本格已有的不再列），点选追加 `[编号] 描述` 一行走 onPatch（3s 自动保存承接）；回收格 chips 带该收了标
- [ ] 3.3 `ChapterWorkspace.tsx` 接线：`useHooksLedger`＋`ogHookHints`（当前章 id 取 `store.chapter.id`）传 `hookHints` 给 OgPane

## 4. 测试与门禁

- [ ] 4.1 vitest：查看态投影两态（空格出投影/理由句、格非空不出）、编辑态 chip 勾选落格且已有不重复列、HooksPane 共享 hook 回归
- [ ] 4.2 pytest：1.3 断言；全量相关套件绿
- [ ] 4.3 e2e：章纲页签投影可见＋chip 勾选落格一条（隔离栈）
- [ ] 4.4 openspec validate --strict；PR；归档
