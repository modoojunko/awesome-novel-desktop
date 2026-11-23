# 提案：退役提示词预览弹窗与死右栏（c-retire-prose-aimodal）

## Why

`c-agent-dialog-prose`（#1131 已合）把生成正文挪进对话框方案卡后，AI 提示词预览弹窗（AiModal）没有任何入口；它连同只被它/旧右栏 Rail 链持有的组件与端点成为死代码——留着会误导后续维护（以为还有弹窗入口）且每天被 tsc/测试/覆盖契约拖着走。

## What Changes

- **前端删死件**：
  - `AiModal`（workbench/modals.tsx 内组件）＋其测试；`GET /write/prompt` 的前端调用随弹窗消失。
  - 右栏渲染面：`Rail.tsx`／`AiAssistPanel.tsx`／`WriteBlockPanel.tsx`（旧右栏已不在树中）＋连带测试与覆盖契约条目；`RailChapterData` 类型迁 `workbench/railData.ts`（去 `writeBlock`/`promptSavedSignal` 死字段）。
  - `lib/promptSources.ts`（无消费者）与写法块前端回调链（`onWriteBlock`/`WriteBlockPayload`/`write_block` 事件解析；后端 SSE 照发，不改协议）。
- **后端删死端点**：`GET /write/prompt`（`assemble_write_prompt` 单源保留，助手 `read_write_prompt` 工具继续用）。
- **不动**：`/prompts/write` 存稿端点（写链自动存稿仍用）、后端 `write_block` 事件、e2e 旧弹窗用例（存量已随入口退役失效，真机走查另行重写——挂账）。

## Capabilities

### 修改
- `prose-writing`：MODIFIED「基于确认提示词生成」——弹窗措辞退为方案卡/直开路径口径；删去「刷新预览」「旧整包分级提示」两个已无 UI 的场景；存量行复用与代际回落守卫语义原样保留。

## Impact

- 前端：`components/novel/workbench/{Rail,AiAssistPanel,WriteBlockPanel,railData,modals,ChapterWorkspace,ProsePane}`、`lib/{ai,promptSources}`、`coverage-contract.ts`、相关测试。
- 后端：`write/router.py`（删端点）、`chapter_writer.py`/`assistant/tools.py` 文档落点措辞。
- 行为零变化：所有被删代码均不可达（无渲染入口/无调用方）。
