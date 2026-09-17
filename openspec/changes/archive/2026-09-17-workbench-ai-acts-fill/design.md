## Context

见 proposal.md — Why。约束：压缩复用 polish/expand 全链（提示词→服务→端点→对照预览→页内/右栏入口），不引入新模式语言；按需收尾复用已归档的 archive-reconcile 服务（只加 kinds 过滤＋一个端点）。

## Goals / Non-Goals

- Goals：把两个共用机器齐备的占位动作升级为真功能；为后续批次立可复制的模式（选区族＝同通道加模式；收尾族＝kind 参数化）。
- Non-Goals：冲突检测族/摘要建议族/提示词辅助族/补全缺失字段（下一批）；不做收尾产出的即时跳转（toast 指路即可）。

## Decisions

1. **压缩＝transform 第三模式而非新流程**：prompt 只换模板（`compress_text.prompt` 明确「保留关键信息与情绪落点、篇幅 50%-70%、不新增内容」）；预览组件三态文案扩展；失败/记账口径与既有端点逐字对齐。
2. **收尾 run 的 kind 参数化**：`start_reconcile_job(kinds=None)`——None 全量（归档触发路径不变），list 按类；端点校验 KINDS 白名单防脏类别写行；门控与 retry 同族（PRO＋模型）。
3. **三入口「归档后可点」**：产出只在「操作」页签可见（该页签仅归档章呈现收尾区），未归档可点会造出「看不见的提案」；故以 archived 门控，禁用而非隐藏（保留可发现性）。

## Risks / Trade-offs

- [单飞下按类触发被现跑任务吞掉（started=false）] → 提示文案明确「已有任务在跑」，产出照常轮询可见；不做队列（与归档触发同语义）。
- [压缩比例不稳定] → prompt 给区间（50%-70%）且对照预览可接受/放弃，风险由人工确认兜住。

## Migration Plan

零 schema 变更；纯代码回退。

## Open Questions

无（其余占位批次待用户优先级）。
