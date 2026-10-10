# Tasks: c-prose-regen-replace

## 1. 确认弹窗与文案

- [x] 1.1 `modals.tsx` 新增 `RegenConfirmModal`（title 重新生成正文；正文点名「清空当前正文」＋字数；指路「版本历史」；`testid=regen-confirm`；取消/继续生成）
- [x] 1.2 `AiModal` 增 `hasProse` prop：提示行「清空并替换本章现有正文，旧正文可从版本历史找回」／空章「生成内容将写入本章」；退役「追加到本章末尾」
- [x] 1.3 `AiAssistPanel` 生成正文动作行描述改「生成／替换本章正文」

## 2. 入口门禁

- [x] 2.1 `NovelWorkspace.runAiAction`（write 分支）：`railData.wordCount > 0` → `setShowRegenConfirm(true)`；确认 → AiModal；取消 → 零副作用
- [x] 2.2 `requestAi` 增 `opts.skipRegenConfirm`；「去刷新提示词」toast 出口传 true

## 3. 替换写入

- [x] 3.1 `ProsePane.startStream`：`void store.flush()`（快照前置）→ 整档清除（**不入撤销史**，e2e 实测整改 62a9de4e）→ size===0 守卫下垫段/取插入点 → 流式
- [x] 3.2 `ProsePane.finishStream`：正文终态＝生成物；`streamBaseRef` 退役
- [x] 3.3 验证 prosemirror 整档删除留下的空段即流式脚手架（insertContentAt 收尾不留尾随空段）

## 4. 测试

- [x] 4.1 NovelWorkspace 门禁三用例（先确认／取消零副作用可重入／空章直进）
- [x] 4.2 AiModal 提示行双口径两用例
- [x] 4.3 proseStream 替换链三用例（终稿＝生成物且旧正文清空；一次撤销回空稿；瞬时生成同拍确定性）
- [x] 4.4 e2e `prompt-pipeline.spec.ts`：`openModal` 兼容门禁；撤销用例改钉替换语义
- [x] 4.5 e2e 隔离栈复跑（regen-e2e 独占栈）：写作流四 spec 31/31；全量 239 例＝188 过＋19 skip（既有门控组）＋32 红——**32 红经 A/B 定罪为存量**（origin/main 构建同六 spec 同样 32 failed/8 passed，失败簇全在弹窗域：卷规划/拆章/剧情/盘点/引导/UP-11，取数 503 与本 change 无关）
- [x] 4.6 e2e 隔离栈实测揪出撤销语义快慢漂移 → 清空改不入撤销史（62a9de4e）＋新增「停止留半截→版本历史找回」常驻钉（b408b668）

## 5. 归档（另行 PR）

- [ ] 5.1 specs sync：workbench 三处（ADDED 门禁 requirement＋两处 MODIFIED 逐字对拍）
- [x] 5.2 全链预验（e2e 常驻钉 b408b668 在隔离栈真链通过：确认→替换写入→停止留半截→版本历史找回）；真机抽检留给作者随手一次
