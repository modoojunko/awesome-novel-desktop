# c-prompt-tab-retire — 提示词页签退役：查看/编辑/存稿收编生成正文弹窗

## Why

用户 2026-09-27 拍板：章页面「提示词」页签去掉；「每次最新提示词在哪查看」需要三层明确落位
（状态／全文／落库），能力一个不丢（主链路的看→改→润色→生成在弹窗内本已闭环）。

## What Changes

- **页签退役**：章工作台八枚→七枚（章纲/正文/设定/文风/角色关系/伏笔/操作；全档一致，原 PRO-only 隐藏口径下线）。
- **三层落位**：① 状态＝正文页签 AI 助手卡作用域行「本章提示词 自动组装/已自定义 · 组装来源 N 字」；
  ② 全文＝生成正文弹窗（每开重新组装；只查看不生成＝取消，零副作用）；
  ③ 落库＝弹窗新增「存为本章提示词」（PUT prompts/write；不点＝仅本次生成用）。
- **精修收编**：「补全负向约束/精简提示词」移入正文页签能力行（提案制弹窗不变）。
- **退役件**：PromptPane.tsx、PromptManagementPage.tsx（整章单卡/种子提示词）、.psrc 六来源 chips 详情、
  页签徽标；`prompt-panel` feature key 保留（后端 entitlement 快照仍下发，暂无前端消费者）。
- **信号链**：promptSavedSignal（NovelWorkspace→ChapterWorkspace→Rail→AiAssistPanel），润色/存稿后状态行刷新。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 「右栏「AI 辅助」面板」（正文页签能力行补精修两行；重复动作措辞随页签退役更新）；
  「卷/章页签结构同位」（章页签顺序七项，全档一致）；「提示词精修」（场景中「提示词页签刷新」改状态行）；
  新增「章提示词查看与存稿（生成正文弹窗承载）」。

## Impact

- 前端：ChapterWorkspace/AiAssistPanel/Rail/NovelWorkspace/modals.tsx（AiModal 存稿行）；删两组件与死 CSS。
- 门禁：tsc、vitest 871、build、design:lint、隔离栈 9 文件 e2e 48 条（含 rebase #516 后）——全绿
  （PR #518，squash=88efc995）。
- 零数据面改动；生成/精修链路不变。
