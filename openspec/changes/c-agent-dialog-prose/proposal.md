# 提案：助手对话框编排生成正文（c-agent-dialog-prose）

## Why

正文生成的「写法指引」由 P0 规则选择器挑选（kb/match.py `select_block`）：对「本章剧情」的认知只有 5 个封闭词表信号（场面/情绪/章位/角色/题材），剧情文本本身不进打分；无条件「手法」条目恒 0.5 分每章必进、还要填满 6 条配额——真机走查实锤「写法指引条目大多不适用（今昔对比塑军、会后分线等与素材冲突，不新增剧情）」，模型只能在思考里自我矛盾地拒绝执行。

boss 拍板：把「生成正文」整个挪进 AI 助手对话框——agent 判断取哪些素材（章纲/剧情/文风文笔/设定/角色/全书进展），过程与思考复用对话框组件（工具步卡/思考泡泡/计划卡）全程可见；agent 出结论卡（含**待生成正文的用户提示词全文**＋按剧情选中的文笔/写法条目），作家过目点「开始生成」后正文在正文区异步流式；生成的大模型调用上下文独立，对话框会话历史一律不夹带。

## What Changes

- **助手工具三件**（assistant 域）：
  - `kb_search_craft`（read）：按本章剧情确定性检索题材写法条目（候选域=写法块同源 `digest_candidates`，题材过滤内建；零命中明确回话，工具历史即记录）。
  - `read_write_prompt`（read）：读服务端组装的本章用户提示词全文（与 `GET /write/prompt` 同源逻辑）——结论卡提示词的基底，agent 不凭空拼装。
  - `draft_prose_plan`（card）：出「正文方案」结论卡＝选中条目清单（id/标题/理由）＋用户提示词全文＋已有正文警示。
- **write 链扩展**：`POST .../write` body 增 `kb_picks`（含键即 agent 模式：写法块按 agent 挑选的条目组装、跳过规则选择器；零有效条目＝无块，回退本书文风设定；run 落 `selector="agent"`）；不含键行为一字不变。
- **前端**：正文页「生成正文」chip 改 command 型进对话框；对话框新增 `prose_plan` 产物卡（条目清单＋提示词折叠全文＋开始生成按钮）；宿主桥接 `proseRef.startWriting(prompt, kbPicks)`；**AiModal 提示词预览弹窗入口退役**（组件与 `/write/prompt` 端点本版保留不挂载，挂账清理）。
- **能力端点**：`GET /api/novels/{id}/assistant/capabilities` → `{"dialog_prose": bool}`；env `ASSISTANT_PROSE_FLOW=off` 熔断——chip 回退直开（无 agent 编排，规则选择器照旧）。

## Capabilities

### 新增
- `assistant-dialog-prose`：对话框编排生成正文的完整行为契约（三段式/上下文隔离/未命中回退/熔断）。

### 修改
- `prose-writing`：ADDED「按助手挑选条目组装写法块」Requirement（agent 模式判定、重试字节一致、零命中无块）。

## Impact

- 后端：`assistant/tools_kb.py`、`assistant/tools.py`、`assistant/scopes.py`、`assistant/router.py`、`write/router.py`、`write/write_block.py`；新增测试。
- 前端：`lib/chatRegistry.ts`、`lib/ai.ts`、`lib/chatApi.ts`、`components/novel/chat/Aui2Dock.tsx`、`chat/CardBody.tsx`、`NovelWorkspace.tsx`、`workbench/ProsePane.tsx`。
- 行为变化：正文页默认入口改走对话框编排；旧弹窗链不删但不可达（挂账清理）；env 熔断回退路径与旧行为一致。
- 上下文隔离铁律：write 调用的素材=卡上展示、作家过目的那份提示词（既有 prompt 覆盖通道）；不新增任何从 assistant 会话读数据的路径；测试钉死。
