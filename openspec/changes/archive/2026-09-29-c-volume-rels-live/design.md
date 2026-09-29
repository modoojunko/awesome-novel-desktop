## Context

- 现状：RelationsGraphPane 三种挂载态——章态（`chapterRef`，双源：preview 往章演变＋章档端点本章边）、卷态（`volumeScope`，只画开书设定边）、书态（两者皆无，理论上不出现）。卷态不并入剧情边是 #434 立项时的取舍，#576 做章态剧情边时沿袭；`visibleEdges` 的按卷投影过滤（`parseChapterRef(e.origin)` 卷号 ≤ volumeScope）当时已写好，只是卷态从不喂 dossier 数据。
- 数据面：章档关系行（ChapterRelationChange，accepted）→ 折叠单源 `story_state_upto`（已采纳∧已归档∧非 stale，按 (owner,other) 后章覆盖）＝`GET /dossier/preview?up_to_ref`；章档端点 `GET /chapters/{ref}/dossier` 返回单章 rows（不要求已归档——归档后回草稿的章仍持有已采纳行）。两条路 C端 后端均现成，零后端改动。
- 卷树 `GET /volumes` 每章已带 `status`/`archived`/`stale`（volumes/service.py list_volumes），RelationsGraphPane 本来就拉它做来源章题名——卷态所需的「本卷末章 ref」与「未归档章清单」可自取，VolumeWorkspace 无需新传 props。

## Goals / Non-Goals

- Goals：卷态图随时对齐本卷剧情最新的已确认关系；投影口径与章态的往章演变同源；只读语义不变（无章高亮、无工作流、待确认不上图）。
- Non-Goals：不改写章消费折叠单源本身（stale 排除口径不动）；不新增后端端点；不给卷态加待确认工作流；不动章态与书态行为。

## Decisions

- **D1 客户端组装，不加后端端点**：preview 截至本卷末章（覆盖已归档部分，一次调用）＋范围内未归档章逐章拉章档端点取已采纳行。未归档章通常只有写作前沿 0–2 章，请求数可控；组件本就持有卷树，无需新契约。
- **D2 「随时对齐最新」＝已采纳即上图，归档与否不设门槛**：preview 负责已归档章（stale 排除沿用折叠单源的安全口径）；未归档章的已采纳行并入——用户在章页采纳即视为剧情事实，回草稿重写窗口内卷页不丢。待确认提案不属「已确认」，不上图。
- **D3 未归档行排在 preview 行之后**：mergeGraph 同向同优先级先到先得（KIND_PRIO 相等时先行者胜）。未归档章若在归档前沿章之前（重写旧章窗口），后归档章的 preview 折叠行是更晚的剧情事实，应胜出——preview 行在前恰好实现该语义；未归档章为末章时无同向冲突。
- **D4 加载门控对齐章态**：引入 scopeKey（`chapterRef ?? vol:{N}`），剧情边就位前呈「加载中」，不闪开书设定半成品图；卷树未就绪（chaptersReady）前卷态不发投影请求。树/投影拉取失败静默退回开书设定边（既有章态同口径）。
- **D5 卷树补 `archived` 字段**：ChapterMeta 增 `archived: boolean`（list_volumes 已有），卷态用它圈定未归档章清单；卷号经 parseChapterRef 从 ref 解析，不新增字段。
- **D6 跨卷边过滤复用 visibleEdges**：preview 截至本卷末章天然不含后面卷的章，但收尾提案物化进设定的开书边可来自任意卷——既有 `p.vol <= volumeScope` 过滤继续兜这层，剧情边同规则，零新逻辑。

## Risks / Trade-offs

- 未归档章极多时（用户长期不归档连续写作）逐章拉取 N 次请求——现实流程归档在前沿 1–2 章窗口内，且为只读投影非关键路径；不在本 change 做聚合端点，留观察。
- 重写旧章（回草稿）期间其旧已采纳行与后归档章新行同向冲突时，D3 让后归档者胜——该窗口内本就属于过渡态，重归档后 stale 级联会自然收敛口径。

## Migration Plan

单组件数据分支改动，无存储/契约变化；随实现 PR 上线即生效。

## Open Questions

（无——口径已由用户 2026-09-29 拍板：随时对齐本卷剧情最新已确认关系。）
