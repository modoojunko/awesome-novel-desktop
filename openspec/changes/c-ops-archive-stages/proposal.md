# Proposal: c-ops-archive-stages（归档卡三段进度：提取 → 确认 → 完成）

## Why

归档受理后，进度面只有操作页签归档卡里一行静态「AI 提取中 · 本章已锁定……」：提取是一次 AI 调用（30–90 秒），期间该行不变、无阶段可辨；提取完成后卡片直接翻成「重新归档」按钮，产出了多少提案、还剩几条没确认，卡上无处可看（计数只活在设定/关系页签与弹窗警示里）。作者提出在归档按钮处做分阶段进度展示。

实勘：所需的全部数据前端已有——提取态＝`archiveJob`（3 秒轮询），待确认计数＝dossier GET `progress`（归档态常驻拉取），零后端改动。提取是一次 AI 调用、行落库前无中间量，进行中的诚实信号＝已运行秒数（不做假百分比）。

## What Changes

- **归档卡三段进度条**（提取 → 确认 → 完成）：
  - 提取段：受理后 active（带已运行秒数走针）；失败 fail（红）；跳过/未提取 skip；已提取 done。
  - 确认段：`待确认 N 条`（active）／`提案已处理`（done）；未归档时不点亮。
  - 完成段：已归档点亮。
  - 提取中说明行去掉与进度条重复的「提取中」字样，只保留锁定与产出落点说明。
- 新组件 `ArchiveStages`（含 `useElapsedSec` 走秒 hook）；样式挂 book.css `.arch-stages`。
- 零后端、零 DDL；既有 testid（archive-extracting/archive-btn/archive-retry/archive-skip/archive-backfill/archive-reextract）全部保留。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：「中栏「操作」页签与收尾进度」——归档进度细化为三段进度条（提取/确认/完成＋已运行秒数＋待确认计数），新增对应 Scenario。

## Impact

- 前端：`ChapterWorkspace.tsx`（rearchive 扩 pending＋卡片渲染）、新 `ArchiveStages.tsx`、`design/book.css`。
- 测试：vitest `archiveStages.test.tsx`（状态矩阵＋走秒）；e2e `chapter-dossier.spec.ts`（已归档条含待确认计数＋逃生阀失败态）。
- 非目标：其他页签的进度镜像；提取百分比/分域进度（后端无中间量）；完成后新 toast（既有终态 toast 不动）。
