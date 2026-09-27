## Context

见 proposal.md。纯界面重组，三条约束：右栏数据通道被多处消费（只撤渲染不撤通道）；「本章进度」块
从未立过 requirement（本次以 ADDED requirement 固化退役后口径）；头部徽章行已在 c-og-rail-declutter
定过六枚口径，本次扩为八枚须同步改写该条目。

## Goals / Non-Goals

**Goals**：四项去重落位；零 render-loop 风险（`onRailData` 效果不动）；e2e 同批钉住。

**Non-Goals**：其余页签统计卡；卷视图；原型同步。

## Decisions

- **D1 徽章口径**：完成度＝`Math.min(100, round(wordCount/planWords))`，planWords 缺失不渲染；
  本书总字数沿用 NovelWorkspace 汇总的 `bookWords`（与原 mini 统计同源）。
- **D2 编辑入口让位**：右栏就地编辑退役，章纲「本章目标字数」格是唯一 UI 编辑点（同一数据字段，
  非功能损失）；`setTargetWords` 仍在数据通道上。
- **D3 归档卡提示语退役**：右栏「本章已归档 · 只读查看」卡与头部「已归档」徽章重复；归档动作
  入口在操作页签首卡（c-og-rail-declutter），提示语无增量信息。

## Risks / Trade-offs

- 归档/进度的「提示性文案」（再写 N 字…）随块退役——达成状态由完成度徽章承载。
- 本书总字数随树刷新节奏更新（原 mini 统计同款时序，非新退化）。

## Migration Plan

纯前端同批切换，无迁移。
