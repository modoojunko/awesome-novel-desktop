## Why

2026-11-21 写作助手真机对话实录暴露三类可复现的行为缺陷：

1. **协议裸泄**：模型输出形态为 `"action": "draft_arc", "tool": "", "args": {}}` 的裸片段（无 `===ACT===` 哨兵、首字符不是 `{`）。`stream_slice` 只冻结首字符 `{`／反引号与哨兵后的内容，`parse_action` 无哨兵时整段按 final 交付——协议片段原样上屏，并被写回会话历史，下一轮模型开始为自己的坏输出道歉重跑。
2. **说了没做**：把工具名填进 `action` 槽（`"action": "draft_arc"`）且叙述非空时，`_action_from_parsed` 判为「自愿收口」返回 final，重试只对 degraded 生效——本轮静默结束。「三件事落库」只发了一个动作，用户拿到的是承诺不是结果。
3. **承诺越界**：叙述说「落库」「我起笔写卷一开头」，但 `draft_arc` 是只产卡、不写书的工具，注册表里没有任何正文生成工具（`ch:prose` 域只有 `switch_tab`）。进模型的工具清单只列「有什么」，不列「没有什么」，也不说产卡不等于落库。

多意图请求目前没有进度载体：一条消息里三件交付物，循环只按单步动作推进，做完一件即可收口，没有任何东西检查另外两件。

## What Changes

- **动作协议硬化**：协议形状检测从「首字符 `{`／含哨兵」扩展到「任意位置出现 `"action"`／`"tool"`／`"args"` 键的裸片段」；命中即按 protocol_error 处理（冻结、不进正文、可重试）。
- **非法动作确定性修复**：`action` 槽误填已注册工具名时，修复为 `tool=该名` 并归一 `args`（含嵌套 `action`），不再静默收口。
- **protocol_error 独立重试**：与 final/degraded 分离，重试一次；仍失败只交付清理后的叙述，坏文本 SHALL NOT 上屏、SHALL NOT 写回会话。
- **能力边界由注册表派生**：工具清单追加边界块——清单外不存在、正文生成不在对话里、产卡类工具不得说「已落库／已写入／我写完了」。不改提示词包，不升 pack 版本。
- **多意图任务计划**：新增 `update_plan` 工具（只改会话内计划，不写书、不吃授权）；计划快照经新 SSE `plan` 事件下发并逐步落盘；dock 渲染计划卡（四态）；`run_end` 携带未完成计数，掉线重开可恢复。
- **`draft_arc` 入参分层**：拆 `material`（素材）与 `constraints`（写法约束，只影响怎么写）；`input` 保留为兼容别名；工具层以分隔块拼给既有能力核；产物卡回显本次约束。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `writing-assistant`：新增动作协议鲁棒性与「承诺—执行一致」要求；新增注册表派生能力边界；新增多意图计划与逐项进度；`update_plan` 纳入循环护栏与事件契约。
- `assistant-chat-ui`：修改「全模型逐字流式」——第三种协议形状不落正文、不写回历史；新增计划卡呈现与四态收口。
- `assistant-tools`：新增 `update_plan` 工具与域挂账；新增起草工具入参分层（`draft_arc` 的 `material`／`constraints`）。

## Impact

- **后端**：`client/backend/assistant/actions.py`（形状检测／修复／protocol_error）、`loop.py`（重试判据／plan 事件／run_end）、`tools.py`（`update_plan`、能力边界文本）、`tools_cards.py`（`draft_arc` schema）、`prompts.py`（边界块拼装）、`router.py`（SSE `plan` 事件）、`session_store.py`（plan 事件行与恢复）。
- **前端**：`Aui2Dock.tsx`（plan 事件消费与计划卡）、`CardBody.tsx`（约束回显标签）、`chat.css`（复用既有语义类，不新增形态）。
- **API**：新增 SSE 事件 `plan`（增项，旧客户端忽略）；`draft_arc` 参数新增 `material`／`constraints`（`input` 兼容）；`run_end` 新增 `planIncomplete` 计数（增项）。
- **会话文件**：新增 `kind=plan` 事件行（增项，旧读端按未知事件跳过）。
- **提示词包**：零改动、不升 pack 版本（边界块与约束分隔均在 C端代码内组装）。
- **测试**：`test_assistant_actions.py`（无哨兵裸片段、action 槽填工具名）、`test_assistant_loop.py`（protocol_error 重试、plan 事件、run_end 计数）、`test_page_scopes.py`（`update_plan` 挂账）、前端 `Aui2Dock.test.tsx`（计划卡四态与恢复）。

## Design Impact

- **受影响端**：C端；S端零参与。
- **屏／弹层**：写作台右栏助手 dock（全页签共用）；`draft_arc` 产物文本卡。
- **对象状态**：计划项四态映射 `docs/ux/design-language.html` §5 状态语言总表——未开始＝未填（中性）；在做＝进行中（warn）；做完＝已确认（ok）；没做成＝阻断缺项（err，仅当该件是作家点名的交付物）。不新增第四种胶囊形态。
- **共享段**：不触碰 `base.css` 令牌、基础组件类与 `pill/notice/sk/panel/f-err` 家族；计划卡只复用既有 chat 卡面骨架与语义类。
- **原型先行**：更新 `docs/design-c/drafts/ai-novel-c端-写作助手对话框-原型.html` 与设计说明，补计划卡四态与收口未完成态。dock 不在 `design:check` 像素 parity 基线内，无需改基线；`ADJUSTMENTS.md` 无对应屏，不新增登记项。
- **设计工件产出**：实现侧自查＋原型补态（无设计侧会话）。
- **文案**：按 §13 人话口径；按钮用动词；不引入 success/danger 语气词。
