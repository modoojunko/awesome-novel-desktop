# c-agent-effects：agent 写操作后前端实时刷新（Effect 系统）

## Why

agent 对话执行写类工具（确认章纲/归档/建卷章等）后，后端数据已变但**前端不知道要刷新**——左侧树还是旧状态、章节头还是草稿态。作家要手动刷新或切页签才能看到结果。boss 拍板（2026-11-17）：agent 操作必须实时反映在页面上。

## What Changes

- **Effect 系统**：每个写类工具声明 effect 元数据（domain/target），router 在 run_end 事件注入 effects 数组，前端按域精确刷新
- **Aui2Dock**：新增 onEffects 回调 + permission_required 分支（已补）+ dirty 保护（未保存编辑跳过刷新）
- **NovelWorkspace**：实现 onEffects 回调 → 按域刷新数据（复用已有加载函数）

## Capabilities

### 新增
- `assistant-effects`——agent 操作前端实时刷新

## Impact

- backend：assistant/tools.py（写工具加 effect 元数据）、assistant/router.py（_consume 收集 + run_end 注入）
- frontend：Aui2Dock.tsx（onEffects 提取 + onEffects 回调）、NovelWorkspace.tsx（refreshDomain 实现）
