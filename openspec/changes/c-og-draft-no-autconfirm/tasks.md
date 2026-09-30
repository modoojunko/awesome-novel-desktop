## 1. 原型先行（ADJUSTMENTS 登记替代）

- [x] 1.1 `docs/design-c/prototypes/ADJUSTMENTS.md`：新增本 change 段（撤回确认入口＋confirm 弹层为应用侧扩展，原型未建模不入 parity）＋修订旧自动确认登记条（「仅显式保存草稿/确认章纲触发自动确认」→「保存草稿只保存；确认仅走确认章纲」）。完成证据＝登记 diff。

## 2. 后端撤回端点

- [x] 2.1 `chapters/router.py` 增 `POST /chapters/{chapter_ref}/unconfirm`：404 章／书不存在；409 已归档（`row.status=="archived"`）；已草稿幂等 ok；否则 `chapter["status"]="draft"`→`save_chapter` 统一写入口＋`row.status="draft"`＋`row.confirmed_at=None`，返回 `{ok, status:"draft"}`。完成证据＝pytest 新例（确认→撤回→outline_status 派生正确／归档 409／幂等）。

## 3. 前端

- [x] 3.1 `useOutline.ts` 增 `unconfirmChapter(ref)`（api.post＋失败 toast，与 confirmChapter 同层）；接口类型同步。完成证据＝tsc 绿。
- [x] 3.2 `ChapterWorkspace.tsx`：`handleSaveDraft` 删自动确认段（保存→「草稿已保存」）；接 `onUnconfirm` prop 链（调 unconfirmChapter→reloadStatus→refetchTree→toast「已撤回确认，章纲回到草稿态」）。完成证据＝单测断言保存草稿后 confirmChapter 零调用。
- [x] 3.3 `OgPane.tsx` 查看态：`done-note` 行内加「撤回确认」ghost 小按钮（仅 confirmed 态）→ confirm 弹窗（「撤回后章纲回到草稿态，可随时重新确认」＋出口「保留确认／撤回」）→ `onUnconfirm()`。完成证据＝单测：confirmed 态按钮出现、弹窗出口两分支。

## 4. 测试与门禁

- [x] 4.1 单测适配：`chapterWorkspace.plotFlow.test.tsx`（confirmChapter mock 链）、`useOutline.test.tsx` 增 unconfirm 用例；新用例钉「保存草稿不触发 confirm」「撤回确认全链」。完成证据＝vitest 全绿（存量红除外）。
- [x] 4.2 e2e 口径矫正＋新钉：`outline-ai-draft.spec.ts:174`「已保存并确认章纲」→「草稿已保存」（后读 status=draft）；`workbench-features.spec.ts:193` 同；任一 spec 增「确认→撤回确认→徽标消失＋确认按钮恢复」段。完成证据＝隔离栈 e2e 全绿。
- [x] 4.3 门禁：`tsc --noEmit`＋全量 vitest＋`npm run design:lint`＋后端 pytest（新例）＋`openspec validate c-og-draft-no-autconfirm --strict`。完成证据＝各命令输出结论。
- [ ] 4.4 PR（标题不带硬编码 PR 号）＋合并后归档 sync specs（workbench MODIFIED）；演示栈换包＋bundle 特征串自证。
