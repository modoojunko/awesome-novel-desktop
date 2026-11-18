# c-agent-nav：AI 助手控制作家页面——说切就真切

## Why

走查实锤（2026-11-18 截图）：作家说「把页面切到正文」，助手回「页面切到正文了，聚焦 vol-1-ch-7」——**中栏一动不动**。模型没有切页能力，纯靠话术假装切了（幻觉执行），比不回应更糟。boss 总纲（2026-11-17）：agent 操作涉及翻页、编辑、保存的，要在页面上看到操作效果——翻页是 Phase 1（c-agent-effects 只做了 refresh 域刷新）缺失的一环。

开源调研（docs/design/agent-nav-design.md §2）：AG-UI 协议/CopilotKit 的「前端工具」范式（schema 服务端声明、前端真实执行、结果回喂模型）是行业标准做法；整体引入需换 agent 运行时＋dock，不成比例。本 change **借设计不借代码**：effect 契约词汇对齐 AG-UI，留未来适配器门。

## What Changes

- **新工具 `switch_tab`**（读类免授权）：agent 接到「切到正文/看章纲」类指令时调用；服务端只做页签白名单校验并生成 navigate effect，工具 summary 回喂模型（模型知道成败，不撒谎）
- **navigate effect 中途立即应用**：step_end 时即时下发 SSE effect 事件，前端**立刻翻页**（agent 还在说话时页面就切过去），不等 run_end；refresh 仍按 Phase 1 在 run_end 批量刷
- **域封闭**：switch_tab 只进章节七页签域（ch:og/prose/settings/relations/hooks/actions/style）；卷纲/设定/预览页签的助手看不到它——域外从源头杜绝乱切
- **前端真实切页签**：NovelWorkspace 收到 navigate effect → 守卫（在章节工作台）→ 信号驱动 ChapterWorkspace 切 tab（aiWriteSignal 同款计数器模式）；dock 线程随页签重绑走既有 fleet 机制
- **话术契约**：工具描述写死——调用前话术不许预告「已切」，只能说「我切过去」；切成没切成由系统做。治「说切了没切」的幻觉

## Capabilities

### New Capabilities
- `assistant-nav`——agent 页面导航：agent 可请求切换作家当前看到的章节页签，前端真实执行并回喂

### Modified Capabilities
<!-- 无：不改 writing-assistant 既有 Requirement；effect 契约由 assistant-effects 演进，navigate 是新增 action 值不破坏既有 refresh 语义 -->

## Impact

- 受影响端：C端（双端共享段不触碰；S端无关）
- 受影响屏/弹层：工作台·章节（七页签：章纲/正文/设定/角色关系/伏笔/操作/文风）；右栏助手 dock（新增 effect 事件透传）；无新增弹层
- 对象状态：页签激活态沿用既有「on」态语言（§5 状态语言总表），零新增状态；无语气词新增
- 是否触碰两端共享段：否；不碰令牌档位/组件词汇/状态语言 → 不声明 design-system
- 原型先行：否（纯行为接线，无新视觉；设计稿 docs/design/agent-nav-design.md 已评审）
- 设计工件：实现侧自查（无新组件形态）
- 用户可见文案：工具话术遵循 §13（页签用作家词汇「正文/章纲」，无内部术语）；页签切换失败话术带出口（「打开一章后我再帮你切」）
