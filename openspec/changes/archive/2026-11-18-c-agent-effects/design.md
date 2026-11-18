# c-agent-effects 设计

## Effect 产生：注册表元数据声明式

每个写类工具在注册表条目里声明 `effect_domain`/`effect_target_from`（从 args 取哪个字段当 target）。router 的 `_consume` 在处理 `step_end` 事件时检查写类工具的注册表元数据，将 effect 追加到 `run_effects` 列表。run_end 事件自动携带 `effects` 数组。工具函数不需要手动构建 effect。

## Effect 消费：Aui2Dock → onEffects → NovelWorkspace

Aui2Dock 在 run_end 分支提取 `e.effects`，逐条调 `onEffects` 回调。NovelWorkspace 的 `refreshDomain` 按 domain 调已有的加载函数（refreshChapters/refreshVolumes 等）。dirty 时跳过。

## 非目标
- 版本回退（硬地板候选）
- 正文写流收编（终态链路）
- 实时 mid-run 刷新（Phase 3 远期）
