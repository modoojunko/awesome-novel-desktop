## Why

storyline.html 审计出两类未落地的原型件：①中栏第 8 个「伏笔」页签（章内台账投影，本章埋下/回收高亮）——台账数据齐（真表＋章引用），只缺这个视图；②右栏「AI 辅助」面板的 storyline 形态（随选中页签切换的引导语＋统计卡＋动作清单）——C端右栏还是旧版 book.html 形态，不随页签切换。用户拍板（2026-09-17）：②要做；面板里尚未实现的动作先以「规划中」占位呈现，后续逐个补。同时补掉设定页签「截至本章」投影缺的书级设定条目（archive-reconcile 既有需求「开书设定＋按章序累积的既有设定」的实现欠账）。

## What Changes

- **中栏新增「伏笔」页签（全档位只读）**：列全书伏笔台账（编号/描述/埋点章/状态），**本章埋下或回收的条目高亮**；汇总「N 条 · M 条悬置（· 本章埋下/回收）」。序：角色关系之后、操作之前（原型顺序）。空态引导去「设定 · 伏笔」。
- **右栏「AI 辅助」面板随页签切换**：每页签＝引导语＋统计卡＋动作清单（章纲/正文/提示词/设定/文风/角色关系/伏笔/操作八态）。已实现的动作为真按钮（章纲的 AI 起草与剧情推演、正文的续写/润色/扩写工具保留原卡片形态）；未实现的动作以**禁用＋「规划中」标签**占位（用户拍板：先占位、后续逐个补）。已在中栏页签内提供的动作不在右栏重复（如文风调参）。
- **设定页签「截至本章」投影补书级设定条目**：world history/factions/extra 按 origin 章 ref 过滤到当前章（开书条目恒显示），补上 archive-reconcile 需求里的「开书设定＋按章序累积的既有设定」。
- 右栏在未选中章节（卷模式）时保持既有形态不变。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：ADDED 两条需求——「中栏「伏笔」页签（章内台账投影）」与「右栏「AI 辅助」面板（随页签切换；未实现动作占位）」；设定页签的「截至本章」投影扩展为含书级设定条目（见 tasks 1.4 证据）。

## Design Impact

- **受影响端**：C端（工作台中栏页签＋右栏面板）。
- **受影响屏/弹层**：书工作台（无新弹层）。
- **对象状态**：无新语气档——「规划中」沿用既有 `.tag-plan` 中性标签；伏笔状态沿用 悬置（warn 文字）/已收/已弃。
- **共享段**：未触碰（`.rail-assist`/`.rail-stats`/`.hp-*` 均 `.wb` 屏级作用域）→ 免 design-cross。
- **原型先行**：storyline.html 为该两件的事实源（hooksHTML / aiShell 各页签段）；ADJUSTMENTS #27 增补 ⑦⑧ 两条登记。

## Impact

- 前端：新 `HooksPane.tsx`、`AiAssistPanel.tsx`；`ChapterWorkspace`（页签 8 个＋railData 扩充 tab/ogStats/回调）、`Rail`（章节态挂面板；PRO 工具与免费规划中列表收窄到正文页签）、`SettingsChangelogPane`（lore 投影组）、`book.css`（三组样式）。
- 后端：零改动（全部复用既有端点：hooks/volumes/style-shadow/prompt-sources/characters graph/settings world）。
- 测试：新增 `storylineHooksAndLore.test.tsx`、`AiAssistPanel.test.tsx`（含占位禁用断言）；e2e 新增右栏随页签（⑨）与伏笔页签（⑩）两例。
