## 1. 前端实现

- [x] 1.1 `OgPane.tsx`：`archived` prop（props 注释引 c-archived-readonly＋后端 409 依据）；查看态门改 `!editing || archived`；查看态动作区（撤回确认/去写正文/确认章纲/编辑章纲）`!archived` 条件渲染。验证：单测「归档查看态四入口不在场、一页纸本体保留」「编辑态残留强制回查看态」过
- [x] 1.2 `ChapterWorkspace.tsx`：prose 分支只读横幅提取为 `archivedBanner` 常量，`chTab === "og"` 同挂；**横幅撤「恢复编辑」按钮，文案指路「重写本章」**；OgPane 传 `archived={archived}`；`startOgEdit`/`editAndFlash` 归档短路；`handleUnarchive` 与 railData `unarchive` 上抛随旁路退役删除。验证：集成「归档章横幅指路重写、四入口不在场、无恢复编辑」「缺口 chip 哑火（无保存草稿表单）」过
- [x] 1.3 解锁链退役：`NovelWorkspace` `requestAi` 归档分支改兜底 toast 指路重写，删 `showUnlock`/`pendingAiRef`/`handleUnlockConfirm`/`UnlockModal` 渲染；`modals.tsx` 删 `UnlockModal` 组件；`AiAssistPanel` 正文页签「生成正文/续写建议」归档 `disabled`＋hint「已归档 · 重写走『操作』页签」；`RailChapterData.unarchive` 字段与 `useChapterData.unarchive` 方法（零消费者）删除。验证：全仓 grep 零残留引用＋`tsc --noEmit` 零错

## 2. 测试

- [x] 2.1 vitest 单测：`ogPane.plotEdit.test.tsx` Host 扩 `archived`/`confirmed`/`onUnconfirm`，新增「归档章章纲只读」组 2 用例；`AiAssistPanel.test.tsx` 新增「归档章写入锁死」组（write/continue 禁用＋hint＋点击不上抛）
- [x] 2.2 vitest 集成：`chapterWorkspace.plotFlow.test.tsx` mount 加 `archived` opt（每次挂载新建 wb 桩不污染模块级），新增组 2 用例；全量 `npx vitest run` 1165/1165 绿（101 文件），tsc 零错
- [x] 2.3 e2e：`free-writing-flow.spec.ts` ⑥ 归档流搭车——章纲横幅指路重写、恢复编辑不在场、动作区不在场；正文页签 `ai-write-btn`/续写建议禁用、无「解除只读」弹窗；`modals-pr5.spec.ts` ② 由「解锁链」整段改写为「归档章写入锁死」（横幅指路＋右栏禁用＋og 同锁＋无弹窗），`ensurePromptAccess`/`E2E_FAKE_KEY` 随解锁链退役删除
- [ ] 2.4 e2e 隔离栈实跑（`playwright test --list` 221 条编译过；既有归档相关用例已人工核对：chapter-rewrite 开归档章仅查页签可见性＋重写解锁链路不变；design-parity 只比书架/预览屏）

## 3. specs

- [x] 3.1 delta：workbench 三处 MODIFIED（整段自主 spec 机械提取后改）——「章纲页签查看/编辑两态」（归档恒只读条款＋场景）、「右栏『AI 辅助』面板」（动作清单解锁链表述→归档禁用＋hint；生成正文入口场景同步）、「正文页签查看/编辑两态」（恢复编辑语义退役→唯一路径重写本章；场景「恢复编辑后落查看态」→「归档章写入锁死」）。验证：`openspec validate c-archived-readonly --strict` 过
- [ ] 3.2 归档批 sync 回主 spec（随归档 PR，本仓惯例实现/归档分批）
