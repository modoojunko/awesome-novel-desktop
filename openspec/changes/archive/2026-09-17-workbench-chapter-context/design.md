## Context

见 proposal.md — Why。事实源＝storyline.html `archivePlanHTML`（弹窗预览）与 `relsHTML`（关系页签按章投影）；约束：零后端改动（graph 边已带 origin_chapter；volumes 已带 stale 角标）。

## Goals / Non-Goals

- Goals：作者在归档前对后台动作用完整预期；关系页签从「全书一张图」升级为「本章在全书里的位置」。
- Non-Goals：不做关系页签的编辑入口（原型 canAdd 属后续）；不改归档语义与收尾服务。

## Decisions

1. **预览为信息性静态块（不发请求）**：五件事与 KINDS 单源对齐（文案固定列出）；PRO/免费两态由 isPro 决定。备选＝按 book 模型就绪动态文案——否决（弹窗期多一次探测不值）。
2. **本章高亮用「边 origin_chapter === 当前章 ref」**：与全书图同一数据源（graph 端点），零后端改动；来源题名与「基于旧设定」角标从 volumes 既有字段取，失败静默降级为仅章号。
3. **孤立点在图下以文本行呈现**（原型口径），不引入第二种图形语言。

## Risks / Trade-offs

- [题名取数失败时来源列退化为「第 N 章」] → 可接受（信息不缺失，仅少题名）。
- [边高亮在节点密集时视觉拥挤] → 同章边数量天然有限（单章新增关系极少）；且列表行同步标注。

## Migration Plan

纯前端；回滚即回退提交。

## Open Questions

无。
