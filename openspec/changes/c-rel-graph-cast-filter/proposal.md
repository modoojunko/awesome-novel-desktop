# Change: c-rel-graph-cast-filter

## Why

用户真机截图（2026-10-11）定调两件事：

1. **节点不过滤**：第六章已归档、章纲出场角色仅 2 人，但「角色关系」页签把全书 15 张角色卡全画上环——大部分角色与本章无关，图不可读。角色卡建了但从未进任何章纲「出场角色」的（废卡、设定半成品），也照画不误。
2. **图不随章走**：用户口径是「第一章有一个角色关系，第二章基于第一章的角色关系根据剧情更新」。现状剧情边折叠（章档 relations 域，归档提取时识别）已经在，但上图口径是「全书设定边全量打底」：设定边带 `origin_chapter` 却不按章序收窄，第 5 章才物化进设定的边在第 2 章的图里就"预知"了；节点也没有"截至本章已登记"的概念。

「归档的时候识别关系更新」机制本身已在案（`chapter_archive_extract.prompt` relations 域＋温差规则＋cast/既有章档基线注入，`archive/dossier.py` 四域提取），本变更**不改提取侧、不动提示词仓**——只把上图口径改成随章收窄。

## What Changes

- `client/backend/settings/character_service.py`：`relations_graph` 增 `up_to_ref`（章态）与 `volume_no`（卷态）两个可选口径：
  - **登记集**＝章纲出场角色（`chapter_characters` ⋈ 主线章 `ghost_of IS NULL`，按 `(volume_no, chapter_no)` 章序截至口径章/卷末累计）；登记名解析现名（卡改名后按 `character_id` 命中）。
  - **节点**＝登记过的角色卡；**边**＝双端点都登记才保留，且开书设定边按 `origin_chapter` 章序收窄（来源章在口径章之后的不上图；空 origin＝开书设定恒在）。
  - 响应增 `cast_names`（登记名清单，含登记过但卡已删的名——前端虚线占位用）；不带口径时响应形状不变（现状全书视图，兼容）。
  - `up_to_ref` 找不到章 → 回落全书口径（与 `dossier/preview` 同先例）。
- `client/backend/settings/characters_router.py`：`GET /characters/graph` 增同名 query 参数。
- `client/frontend/src/components/novel/workbench/RelationsGraphPane.tsx`：
  - graph 拉取带口径参数（章 ref 变化即重拉，不再一书一拉）；`mergeGraph` 按登记集裁剧情边——端点未登记的剧情边连同虚线占位节点一起不上图；登记过但无卡的名仍以虚线占位上图（含无边的孤点）。
  - 空态分流：章/卷态下登记集为空 → 引导去章纲登记（区别于「还没有角色卡」）；图例注明「仅章纲已登记角色（截至本章/本卷末）」。
- `client/frontend/src/components/novel/workbench/AiAssistPanel.tsx`（右栏统计口径纠正）：
  - 「人物与势力 N 个 · 关系边 N 条」改用随章 graph（与中栏同源同口径）；
  - 「本章变化 N 条」从「设定边 origin=本章的条数」（口径错，数的是物化进设定的新边）改为「本章章档 relations 行数（待确认＋已采纳，驳回不算）」——与页签气泡、工作流区同源。
- 测试：`test_relations_graph.py` 增口径用例（累计登记/双端点/origin 章序/卷态/卡已删名/refs 找不到回落）；`workbenchExtras.test.tsx` 增过滤与空态用例、存量 mock 适配带参 URL；`AiAssistPanel.test.tsx` 统计口径用例。
- 明确不做：提取提示词与归档链不动（识别机制在案）；章纲页签本身的出场角色编辑不动（`c-cast-split-user-layer` 域）；卷态右栏无 AI 面板（面板仅章态）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：「角色关系页签（关系图为主表达）」Requirement——全书统一视图口径改为**随章收窄**：章/卷态按章纲出场角色登记集过滤节点与边、设定边按来源章序收窄、登记集为空给引导空态；端点增 `up_to_ref`/`volume_no` 口径参数。delta 见本 change `specs/workbench/spec.md`。

## Impact

- C端：`client/backend/{settings/character_service.py,settings/characters_router.py,tests/test_relations_graph.py}`；`client/frontend/src/components/novel/workbench/{RelationsGraphPane.tsx,AiAssistPanel.tsx}`＋`client/frontend/src/__tests__/{workbenchExtras.test.tsx,AiAssistPanel.test.tsx}`
- 端点：`GET /characters/graph` 加可选参数，缺省行为不变（全书视图）；唯一消费方＝关系图页签＋右栏统计
- 数据：零迁移、零回填（登记集现查现用）；章档行、设定边零接触
- 发布：随下次客户端镜像生效；5274 演示栈重建后即时体验
