# Tasks: c-rel-graph-cast-filter

## 1. 后端（client/backend）

- [x] 1.1 `settings/character_service.py`：`relations_graph` 增 `up_to_ref`/`volume_no` 口径——登记集查询（chapter_characters ⋈ 主线章，按 (volume_no, chapter_no) 截至口径累计、id 解析现名）、节点/边按登记集过滤（双端点规则）、设定边按 origin 章序收窄、响应附 `cast_names`
- [x] 1.2 `settings/characters_router.py`：`GET /characters/graph` 增 query 参数透传
- [x] 1.3 `tests/test_relations_graph.py`：新增用例——章态累计登记过滤（含前章登记本章未出场）、未登记卡与其边不上图、origin 章序收窄（空 origin 恒在）、卷态口径、登记过卡已删名进 cast_names、up_to_ref 找不到回落全书；存量 3 用例不动

## 2. 前端（client/frontend）

- [x] 2.1 `workbench/RelationsGraphPane.tsx`：graph 拉取带口径参数并随章重拉；`mergeGraph` 按登记集裁剧情边与 ghost（登记无卡名占位上图、含孤点）；空态分流（登记集空 → 引导章纲）；图例过滤注记
- [x] 2.2 `workbench/AiAssistPanel.tsx`：人物/关系边统计改随章 graph；「本章变化」改章档 relations 行数（待确认＋已采纳，驳回不算）
- [x] 2.3 `__tests__/workbenchExtras.test.tsx`：存量 mock 适配带参 URL；新增过滤（未登记边/ghost 裁剪、登记无卡占位、空登记引导态、图例注记）用例
- [x] 2.4 `__tests__/AiAssistPanel.test.tsx`：统计口径用例（随章计数＋本章变化=章档行数）
- [x] 2.5 `e2e/chapter-dossier.spec.ts`：两章播种 `outline.characters`（林晚/阿蓟，只登记不建卡——ghost 断言依赖）；评审 2026-10-11 补（登记集口径下原断言会落引导空态）

## 3. 门禁与收尾

- [x] 3.1 后端全量 pytest 绿（worktree 内跑，防主检出旧提示词假红）；前端 vitest 全量绿；tsc／ruff 过
- [x] 3.2 `openspec validate c-rel-graph-cast-filter` 过
- [x] 3.2a specs delta 补 `volume-outline` MODIFIED（卷域投影同步登记集口径；评审 2026-10-11 补：跨 capability sync）
- [ ] 3.3 演示栈换包自测（可选）：第六章页签只剩章纲登记角色、随章切换图收窄
- [ ] 3.4 归档另行 PR（本 change 实现合入后做 specs sync）
