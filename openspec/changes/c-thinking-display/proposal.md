# c-thinking-display

## Why

推理模型的思考期是「黑箱等待」：正文首字前只有「模型思考中」＋计时，作者分不清模型在正常推理还是卡死（c-prose-thinking-timeout 判死前尤其如此）。c-inline-think-strip 已把 MiniMax 系内联思考从正文剥离，剥离掉的思考材料正好回流为可见进度；DeepSeek/Qwen/Kimi 的 `reasoning_content` 与 anthropic 的 `thinking_delta` 同样已在客户端层到达、只差透出。

## What Changes

- 客户端层 `chat_stream()` 新增**思考事件通道**：`StreamEvent` 增思考类别，三个来源统一汇入——openai 内联 `<think>` 段（剥离状态机改为边剥边透出）、openai `reasoning_content` 增量、anthropic `thinking_delta`。正文事件口径不变：交付文本零思考、tokens 记账不变。
- 生成正文链路把思考事件转发到前端（SSE 增思考事件形态）；前端在「首字前」等待呈现中**流式显示思考**（弱化样式、随思考滚动），首个正文片段到达即收起（可展开回看）。
- 首字守卫语义不变：思考事件不算首字、不撤守卫（沿用 c-inline-think-strip 口径）。
- 思考呈现为覆盖层：不进入正文文档、不参与撤销历史／自动保存／字数统计／朱雀检测（与阶段呈现同口径）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `ai-client`：**ADDED**「思考增量按独立事件通道交付」——三个来源统一为思考事件；正文事件零混入；不消费思考事件的调用方行为不变。
- `workbench`：**MODIFIED**「生成阶段进度呈现（首字前）」——等待期在「模型思考中」阶段流式呈现思考内容（弱化行内样式），退场/停表/非文档口径不变（「正文生成中的现场保护」按名引用该 requirement，无需单独改）。

## Impact

- 后端：`client/backend/ai_client.py`（StreamEvent 思考类别、openai 剥离状态机透出、reasoning_content、anthropic thinking_delta）、`client/backend/write/router.py`（SSE 事件形态）。
- 前端：正文生成弹窗/生成区（思考流式区＋收起交互）。
- 测试：ai-client 三来源事件钉、SSE 转发钉、前端呈现/退场/非文档钉。

## Design Impact

- 受影响端：**仅 C端**（S端 不涉）。
- 受影响屏/弹层：工作台正文页签的生成区（正文版心内等待呈现区域，即「生成阶段进度呈现」同一位置）；无新增弹层。
- 对象状态（对照状态语言总表）：等待呈现新增「思考流式可见」子态（弱化行内文案，沿用无框行内呈现口径）；退场态不变（首字到达/失败/停止三出口）。
- 两端共享段：不触碰（base.css 令牌与 pill/notice 家族零改动；仅正文版心内的行内呈现样式）。
- 原型先行：需要——`prototypes/workbench.html` 的生成区思考呈现样式先行＋ADJUSTMENTS.md 登记偏差（由实现侧会话产出，随 apply 首任务执行）。
- 文案口径：思考区标识用「思考中」（动词性、无内部术语）；不出现 SSE/事件等内部词汇。
