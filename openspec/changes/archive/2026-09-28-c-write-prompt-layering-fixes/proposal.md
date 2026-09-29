# Proposal: c-write-prompt-layering-fixes（补录——分层上线后的真机修复批次）

## Why

c-write-prompt-layering（#551，归档 #553）上线后真机使用暴露两处回归与两处体验缺口，均走直修 PR 合入（未开 change），此处补录归档在案：#554 分段归一、#555 流式镜像、#556 split 位移 +2（粉碎根修）、#558 流式跟随滚动、#559 章末切点。

## What Changes

- 生成产物分段归一（段间空行→单换行）＋提示词契约补分段规范（#554）。
- 流式插入镜像后端归一——流式所见＝落库最终态（#555）。
- 流式/粘贴写入段落 split 位移 +1→+2——根修流式文本粉碎（#556，真机正文后半段粉碎成单字行的根因）。
- AI 流式写入自动跟随滚动——生成到页末写作区跟着滚（#558）。
- 输出契约加「章末切点」——征兆断章，禁总结式收尾（#559）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——prose-writing 已在 #553 归档时同步；本批次为模板文案与前端写入行为修复，未改既有 Requirement 语义）

## Impact

`prompts/write_chapter.prompt`、`write/chapter_writer.py`、`write/router.py`、`write/auxiliary.py`、`settings/render.py`、`prompt/context.py`、`settings/ai_router.py`、`ProsePane.tsx`、`proseDoc.ts` 及测试/golden；归档遗留（e2e 补跑、真机验收、WIP 接驳、渲染器收编）随主归档条目 c-write-prompt-layering 的遗留清单跟踪。
