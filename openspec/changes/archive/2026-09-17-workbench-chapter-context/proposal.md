## Why

storyline.html 原型审计的收尾两项（原型有、C端无）：①归档确认弹窗缺「收尾计划预览」——原型归档卡先列出「归档后 AI 在后台做哪几件事、写回都要逐条确认、未确认不参与后续提示词」，作者在按下归档前对后果有完整预期；②「角色关系」页签缺按章投影——原型在图上高亮「本章新建或变化的关系」，边行带来源章与状态（开书设定/随剧情演变/基于旧设定），并列「还没连线」的孤立角色。两项均无产品待拍板项，直接按原型补齐。

## What Changes

- **归档弹窗·收尾计划预览**：ArchiveModal 增「归档收尾」区——PRO 列出后台五件事（提取本章设定变化/更新角色关系/登记伏笔/识别世界要素/概括角色状态变化）＋「归档即刻生效、提案逐条确认、未确认不参与后续提示词」说明；免费档说明「归档即刻生效，不产生收尾提案」。
- **角色关系页签·按章投影**：RelationsGraphPane 接当前章 ref——本章新建/变化的关系（`origin_chapter` 命中）在图上高亮（线加粗着色）并在列表行加「本章」标注；边行补来源章（`第 N 章 · 题名` / 开书设定·全书统一）与状态列（开书设定/随剧情演变/基于旧设定——来源章 stale 时）；图下补「还没连线：…」孤立角色行。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：ADDED 两条——「归档确认含收尾计划预览」与「角色关系页签按章投影（本章高亮/来源与状态/孤立点）」。

## Design Impact

- **受影响端**：C端（工作台弹窗与角色关系页签）。
- **对象状态**：无新语气档；「本章」高亮用 accent 家族；状态列沿用 开书设定/随剧情演变/基于旧设定 文案（与设定投影一致）。
- **共享段**：未触碰 → 免 design-cross。
- **原型先行**：storyline.html `archivePlanHTML` 与 `relsHTML` 为事实源；ADJUSTMENTS #27 增补 ⑩。

## Impact

- 前端：`modals.tsx`（ArchiveModal 预览区）、`RelationsGraphPane.tsx`（章上下文投影＋题名/角标取数）、`ChapterWorkspace.tsx`（透传 isPro/chapterRef）、`book.css`。
- 后端：零改动（复用 graph 与 volumes 既有端点）。
- 测试：`src/__tests__/workbenchExtras.test.tsx` 4 例；e2e chapter-rewrite 补归档预览断言。
