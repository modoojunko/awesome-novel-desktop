## 1. 前端（章纲两态）

- [x] 1.1 OgPane 查看态：一页纸只读（.fro 行、未填占位、缺口 chip）＋「编辑章纲／确认章纲／去写正文」ol-top 行；载入中占位
- [x] 1.2 OgPane 编辑态：既有表单不动，底部加「取消」（回退 ogSnapRef 最近落库值）
- [x] 1.3 ChapterWorkspace：ogEditing 状态（切章回落查看）；startOgEdit/cancelOgEdit/editAndFlash 接线；查看态缺口 chip 进编辑＋flash
- [x] 1.4 右栏 AI 起草／缺项补全成功后自动进编辑态；「去补填」toast 动作改 editAndFlash（查看态可达）

## 2. 前端（文风影子两态）

- [x] 2.1 StyleShadowPane：默认只读行（取值/理由文本）＋「编辑影子／完成」；编辑态解锁行内输入、添加行、还原；归档章编辑入口禁用
- [x] 2.2 book.css 补 `.ss-row .r`（只读理由文本档）

## 3. 测试

- [x] 3.1 vitest：ogPane.plotEdit 增两态用例；chapterWorkspace.plotFlow 五处交互先进编辑态；StyleShadowPane 增查看态/归档不开放用例
- [x] 3.2 vitest 全量对拍 main 基线：零新增失败（本机存量 28 失败两态一致），新增 3 用例全绿
- [x] 3.3 e2e 适配：helpers 就绪闸门改「编辑章纲」可见；workbench-features／plot／outline-ai-draft／chapter-plan／modals-pr5 交互先进编辑态
- [x] 3.4 e2e 隔离栈（ogro：5611/8611/19611）：六个受影响 spec 全绿

## 4. 门禁

- [x] 4.1 tsc 零新增错误（对拍 main 基线）
- [x] 4.2 openspec validate --strict
