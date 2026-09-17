## Context

见 proposal.md — Why。触发点：storyline 三期的回退/旧稿支线功能让「章可以不属主线」，而书架列表聚合（`novels/router.py` 的 `/api/novels` enrichment）是除卷章树外唯一一处没跟这个新概念对齐的统计。约束：单用户单机 SQLite；书架卡片与开书落点必须同结论（novel-workspace 契约既有硬要求）。

## Goals / Non-Goals

- Goals：三处书级统计（书架字数/章数/归档数）与工作台卷章树、右栏全书字数统一为「只算主线」。
- Non-Goals：支线章正文的存储与可读性（已由三期契约保证，不动）；支线区在书架上的单独展示（不存在，也不新增）。

## Decisions

**在聚合查询里过滤而非引入计数列**：`chapters.ghost_of IS NULL` 直接加进 `/api/novels` 的聚合 where（一处）。备选：给 novels 表加缓存列——否决（同对象第二份存储，且回退时要维护缓存一致性，违反既有「章表＝唯一事实源，novel 上的列只是缓存」的注释口径）。

## Risks / Trade-offs

- [用户希望「知道稿子还在」但卡片数字变小] → 支线正文在书内可读；如需「另有支线 N 字」的显式展示，属后续产品项（拍板时已记为可选项 b，本次未做）。
- [其他隐藏统计面遗漏] → 已核：卷章树（`volumes/service.py` 已过滤）、工作台全书字数（树派生，自动跟随）、书架聚合（本次修复）三处为仅有的消费面。

## Migration Plan

无 schema 变化；纯查询过滤，代码回退即还原。

## Open Questions

无。
