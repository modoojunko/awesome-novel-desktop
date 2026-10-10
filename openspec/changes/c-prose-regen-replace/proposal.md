# Change: c-prose-regen-replace

## Why

用户反馈（2026-10-10）：生成正文之后再点「生成正文」，不会清空已有正文，而是追加——章节越生成越长，作者没有「重写这一章」的心理预期。产品拍板：正文生成改为**替换语义**（一次生成＝一章终稿，重复生成＝清空重写）；因为清空是破坏性动作，在进提示词弹窗（AiModal）**之前**先出确认弹窗，点名「重复生成正文会清空当前正文」并指明找回路径＝版本历史（生成开始前先把当前正文落盘，保证版本历史里必有清空前的「自动保存」快照——`_write_version_snapshot` 对每次正文实质变化落库都写快照，承诺成立）。作者点确认后才正常进入提示词弹窗。

「追加」语义随本变更退役：右栏动作行描述、AiModal 提示行（原「生成内容将追加到本章末尾」）同步改「替换」口径。「去刷新提示词」软提示出口是只看/刷新意图，SHALL NOT 被生成确认拦住（弹窗内提示行仍告知替换后果）。

## What Changes

- `client/frontend/src/components/novel/workbench/modals.tsx`：新增 `RegenConfirmModal`（重新生成确认：点名清空当前正文＋字数、指路版本历史；`testid=regen-confirm`）；`AiModal` 新增 `hasProse` prop，提示行按「替换／写入」双口径出文案。
- `client/frontend/src/components/novel/NovelWorkspace.tsx`：生成意图入口（右栏「生成正文」等 `requestAi({kind:"write"})`）加门禁——`railData.wordCount > 0` 先开 `RegenConfirmModal`，确认后才 `setShowAiModal(true)`；「去刷新提示词」出口传 `skipRegenConfirm`。
- `client/frontend/src/components/novel/workbench/ProsePane.tsx`：`startStream` 改替换语义——开始前 `store.flush()`（快照前置，重写链同款）→ 整档清除（**不入撤销史**：⌘Z 确定性地回空稿、与生成快慢无关——e2e 隔离栈实测，快生成会与收尾写回落进 history 分组窗直跳旧正文）→ 从空文档流式写入；`finishStream` 正文终态＝生成物（`streamBaseRef` 追加合并退役）。
- `client/frontend/src/components/novel/workbench/AiAssistPanel.tsx`：生成正文动作行描述改「生成／替换本章正文」。
- e2e：`prompt-pipeline.spec.ts` 两处适配——`openModal` 助手兼容确认门禁；「可整体撤销」用例改钉替换语义（旧正文清空、一次撤销回空稿）。
- 单测：NovelWorkspace 门禁三态（有正文先确认／取消零副作用／空章直进）、AiModal 提示行双口径、proseStream 替换链（旧正文清空、终稿＝生成物、一次撤销回空稿）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：新增「重新生成确认（清空重写门禁）」Requirement（入口门禁＋替换写入语义＋flush 快照前置＋刷新提示词出口豁免）；「正文编辑器核心契约」的撤销语义与「正文生成中的现场保护」的半截落库措辞按替换口径修正。

## Impact

- C端前端四文件＋两个测试文件；无后端/端点/schema 变化（版本快照链既有能力，`_write_version_snapshot` 已覆盖每次正文落库）。
- 行为变更：重复生成从「追加」改「清空重写」（有确认门禁兜底）；旧正文找回路径＝版本历史（弹窗文案与 spec 双钉）。
- e2e 全量需在隔离栈复跑（本提交只静态适配了 prompt-pipeline 两处；其余 spec 的生成链均从空章起步，不经门禁）。
