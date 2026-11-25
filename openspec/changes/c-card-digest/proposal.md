## Why

2026-11-25 真机（设定·简介页）：作家说「你帮我起草简介」，工具把结果 `str(dict)` 硬切到 400 字回给模型——三条候选只装下「第一条全文＋第二条开头」，模型对作家说「第二个被截断了」，还数错了总条数。同一天排查发现另有 8 个设定域产卡工具只回一句「已出卡，过目后采纳」，卡里写了什么模型完全不知道，作家一追问「两条差在哪」就只能编。

根因：规格里「给模型看的摘要与给人看的卡职责分离」被实现成了「摘要＝回执、卡＝内容」。这在读类工具上成立（细节可以重读），但产卡工具的产物只进 UI、模型没有回读通道——摘要成了唯一却残破的信息源。

顺带查实一个死工具：`lore_suggest` 传空 body 调必填 `chapter_ref` 的端点，永远 400；就算调通，pick 卡按 `name/rationale` 映射也会把 `{key,value,set}` 丢掉。

## What Changes

- 新增共用摘要渲染 `client/backend/assistant/card_digest.py`：候选逐条（标题＋正文）、报告问题逐条＋达标计数、长文给全文；**单卡 1500 字封顶**，超限按条截并明写「其余 N 条在卡上看」，绝不 `str(dict)` 上对话。
- 设定域 12 个产卡工具摘要全部人话化：简介 draft/check、题材四问、伏笔 draft/check、章纲补全、世界观起草/体检、主线四能力、卷级体检、命名、两个发散、角色草案（确认卡保持现有口语收口）。
- `read_settings` 分区读取预算 800→2000 字；世界 yaml 存在但八格全空时回「（世界设定还没有内容）」，不再回空串。
- 工具步折叠行改取摘要首行（仍 220 字上限），不再把候选正文硬切半句。
- **BUG 修复** `lore_suggest`：参数加可选 `chapter_ref`（缺省取当前写作前沿章），无章可提时回人话失败语；pick 卡保留 `key/value/set/origin`，展示字段映射为 `name/rationale`，不再丢信息。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `writing-assistant`：工具结果摘要的职责分离口径——摘要 SHALL 是产物卡内容的人话提炼（候选逐条/问题逐条/长文正文），单卡 1500 字上限，超限明确标注；工具步折叠行取摘要首行。
- `assistant-tools`：世界观 lore 建议工具可实际调用——接受章引用（缺省当前写作章），pick 卡保留 `key/value/set` 供作家过目。

## Impact

- 代码：新增 `client/backend/assistant/card_digest.py`；修改 `assistant/tools_settings.py`、`assistant/tools.py`、`assistant/tools_cards.py`、`assistant/loop.py`；新增 `tests/test_assistant_card_digest.py`。
- 接口/数据：无 API、DB、前端卡片契约变更（卡片 payload 结构不变；伏笔体检卡的 `draft` 文本由 `str(dict)` 改人话行）。
- 成本：单卡摘要最多 1500 字（约 1000 tokens），低于一次重新起草的调用成本（真机一次 1706 in/615 out）；不设上限会推高每轮窗口占用，且长会话压缩时工具结果仍会被压到 400 字（compact.py），长摘要只是「晚一点被砍」。

## Design Impact

无用户可见界面结构改动：不涉及 design-system 令牌、组件词汇与状态词表，不需要原型先行，C端实现侧自查即可。仅两处既有文案内容变化——工具步折叠行（由硬切正文改为摘要标题行）、伏笔体检卡正文（由 `str(dict)` 改为逐条人话行），均沿用现有气泡/文本卡形态。
