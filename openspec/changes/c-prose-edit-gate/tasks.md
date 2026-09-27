## 1. 前端

- [x] 1.1 ProsePane：`editing` 门控 contentEditable 与输入守卫；查看态顶行「正文 · 字数/空章」＋「编辑正文」（归档/排队/旧稿锁不出现本行）
- [x] 1.2 ChapterWorkspace：`proseEditing` 状态（切章回落）；AI 生成确认（aiWriteSignal）/顶栏续写恢复/重写确认/章纲「去写正文」四条链自动进编辑态

## 2. 测试

- [x] 2.1 vitest：NovelWorkspace 输入链路先进编辑态
- [x] 2.2 e2e：helpers.writeFirstChapter 进编辑态；chapter-rewrite／free-writing-flow／modals-pr5／creation-flow／settings-forms 各触点先点「编辑正文」
- [x] 2.3 vitest 全量对拍 main 基线零新增失败；e2e 隔离栈全绿

## 3. 门禁

- [x] 3.1 tsc 零新增错误（对拍 main 基线）
- [x] 3.2 openspec validate --strict
