## Context

见 proposal.md — Why 与「待拍板」。约束：原型 storyline.html 为事实源（readActionsHTML/applyRewrite/m-ch-confirm）；C端 是「正文自动保存」模型（无原型的一次性写作窗口），重写流程须映射到既有 保存/归档/解锁 链路；**零 schema 变更**优先（指纹门禁对任何模型变更会触发整库留档，原地迁移尚未立项）。

## Goals / Non-Goals

- Goals：给「推翻重写一章」一个安全流程（旧稿有留存、下游有提示），并把「基于旧设定」做成派生语义。
- Non-Goals：不改回退/支线既有语义；不做重写撤销；不做 AI 重写建议（占位不动）。

## Decisions

1. **旧稿去向＝支线章（后缀 ref），而非版本历史**：与原型「移入旧稿支线、可随时点开」一致，也与回退产生的支线同桶（作者只有一个「旧稿」心智模型）。备选＝复用版本历史——实现更小，但版本历史是「本章的恢复点」、支线是「脱离主线的稿」，语义不同；且原型明确支线化。
2. **重写＝快照先行＋原位续写**：确认即落快照（旧稿此刻确定），章保持可编辑（归档章走既有解锁链）；不引入「写作窗口」新面。作者在原文上改，归档即重写归档。
3. **「基于旧设定」派生零新列（评审修正）**：stale(X) = ∃ 更早主线章 Y：Y.updated_at > X.updated_at 且 Y 存在重写快照。备选＝加 `chapters.stale` 列——否决（指纹门禁「列名+类型哈希」下加列＝升级整库留档的连带；布尔还需在「本身被改」时清除，派生天然自洽）。**前置条件：正文写路径显式刷新 updated_at**（现 onupdate 条件触发不可靠，见 Risks）。查询实现：单次查全部章（含 ghost_of/updated_at/created_at/volume/chapter）→ 内存按 (vol, ch) 排序算「前缀最大快照时间/上游最大修改时间」，勿逐章 EXISTS。
4. **角标呈现面**：树行（中性虚线标签 `.tag-stale` 家族）、设定投影布尔、右栏「操作」统计计数（走现有 props 链路，**不给 AiAssistPanel 加请求**）；关系图边虚线（原型 gedges .stale）与设定行 warn 底色本期不做（Non-Goals，随关系图数据带 stale 时同批）。
5. **合成端点 `POST /chapters/{ref}/rewrite`（评审新增）**：一次事务完成「正文 flush（前端先调 `useChapterData.flush()`）→ 快照落旧稿支线 → 归档章解锁（unarchive 同批）→ 返回源章与旧稿 ref」；端点侧拒绝：无正文章 409、源章为 ghost 409、重复确认幂等吸收（同源最新快照正文相同且 <30s 返回既有）。
6. **ref 解析单源（评审新增）**：新增 `lib/chapterRef.ts`（`parseChapterRef`/`isGhostRef`），替换 `useWorkbench.parseRef` 与工作台 6 处 `-ch-(\d+)$` 取号；`focusNode` 接受 `-r\d+` 后缀。

## Risks / Trade-offs

- [多次重写产生支线堆积] → 后缀 r{n} 明确序号；支线只读、随包；不做自动清理（与回退支线同策略）。
- [updated_at 不可靠：条件 onupdate（等字数改写/纯空白保存不刷新）＋秒级精度] → 正文写路径**显式赋值 updated_at**（评审 P0），并补「等字数改写后角标消失」用例。
- [重写已归档章后 frontier 被旧稿快照抢占（同一章号、未归档、ref 排序在前）] → **frontier_info 前置补 `ghost_of IS NULL` 过滤**（评审 P0，已复核实码；本变更首项任务）。
- [归档章重写需解锁，流程多一步] → 复用既有解锁链与文案（「解除只读」），不新增概念。

## Migration Plan

无 schema 迁移；功能开关即代码回退。旧稿支线为新增数据，回滚后按普通支线章处理（只读）。

## Open Questions

- （已决）关系图边虚线与设定行 warn 底色本期不做，随关系图数据带 stale 时同批。
- （已决）重写不限端点章（原型不限）。
