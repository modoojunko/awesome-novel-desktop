## Context

见 proposal.md — Why 与「待拍板」。约束：原型 storyline.html 为事实源（readActionsHTML/applyRewrite/m-ch-confirm）；C端 是「正文自动保存」模型（无原型的一次性写作窗口），重写流程须映射到既有 保存/归档/解锁 链路；**零 schema 变更**优先（指纹门禁对任何模型变更会触发整库留档，原地迁移尚未立项）。

## Goals / Non-Goals

- Goals：给「推翻重写一章」一个安全流程（旧稿有留存、下游有提示），并把「基于旧设定」做成派生语义。
- Non-Goals：不改回退/支线既有语义；不做重写撤销；不做 AI 重写建议（占位不动）。

## Decisions（设计层定案；评审问题逐条以结构消除，非补丁）

1. **旧稿去向＝支线章（评审双方支持）**：版本历史每章上限且正文一变就写，快照会被后续自动保存挤出，且无「点开只读看」的面；支线全量复用 /ghosts/ghost_of/只读锁。
2. **内容寻址旧稿 ref**：`{ref}-r{sha256(正文)[:8]}`——同内容重放同 ref，唯一键天然幂等；取消「MAX+1 取号」与竞态重试。展示无需序号（每次快照唯一）。
3. **「基于旧设定」＝章自身状态列 `chapters.stale`**（弃时间戳派生）：重写事务对下游（≥源章位置、有正文）置位；本章单写入口保存清除。为承接**新增列**，前置实现「指纹门禁纯增量迁移」（见 4）——这同时解除其它加列功能的连带。
4. **指纹门禁差异分类**：`archive_if_legacy(db, fp, metadata)`——指纹一致=current；不匹配且旧库表/列 ⊆ 新库 → additive_migration（create_all＋幂等 ALTER＋启动后刷新指纹戳，数据保留）；否则沿用三件套留档。
5. **主线性单源 `chapters/scope.py`**：主线语义查询唯一构造入口（frontier/树/统计/revert/rewrite 五消费面登记在册）；frontier 漏滤导致旧稿抢占主线的 P0 由此结构性消除。
6. **ref 解析单源 `lib/chapterRef.ts`**：判别联合（mainline|ghost|null）；调用方必须显式处理 ghost（旧实现 null 返回致点旧稿静默无响应）；**源码守卫测试**禁止别处出现裸 `-ch-(\d+)` 正则。`chartRef` 白名单（NovelWorkspace）同步改走单源。
7. **合成端点＋flush 先行**：`POST .../rewrite` 一次事务（快照＋解锁＋下游置位）；前端确认前 `useChapterData.flush()`（1.5s 防抖窗口不得丢段）；重写态不落组件状态（由「本 ref 存在 `-r` 快照」派生语义、刷新不丢）。
8. **产物寻址单源**：`belongs_to_ref`（边界感知）替换 prompts/archives 的子串匹配。
9. **角标三呈现面**：树行 `.tag-stale`（虚线中性，§5 常态徽标禁警示色）；设定投影顶部提示；右栏「操作」统计由 NovelWorkspace 由树计算注入（props 链路，不给面板加请求）；正文保存成功→刷新树消角标。

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
