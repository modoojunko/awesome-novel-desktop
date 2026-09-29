# c-rearchive-keep-adopted — 重新归档保留已采纳行（决策留给作家）

## Why

用户拍板（2026-09-29）：「决策留给作家」。真机实锤：重新归档（rows_only 重提）把本章
**已采纳**的章档行整体清掉重提——作者确认过的事实瞬间蒸发（关系图失线、故事状态消费
归零），直到再次人工确认才回来；每次重新归档都是一轮「清掉→重提→等确认」。已采纳＝
作家拍板过的事实，系统 SHALL NOT 替他清。

## What Changes

- rows_only 重提（重新归档／补提取）SHALL 保留 status=accepted 的章档行，只替换
  pending/rejected 行；首次归档（未归档章）不受影响（本无已采纳）。
- 新提取结果照常以待确认行出现；与已采纳行并存时由作者裁决（消费端 per-domain 去重
  已有「章近优先」，双行不破坏下一章提示词）。
- 重归档弹窗文案同步：不再是「清空并重提」，改为「已确认的保留，其余重提替换」。
- 收尾提案（伏笔/世界要素）不重跑、dossier_stale 清除、归档收口不动——均维持。

## Impact

- specs：chapter-dossier（变化分区归属 MODIFIED——重提保留语义＋场景更新）、
  workbench（归档确认含收尾计划预览 MODIFIED——警示文案）。
- 代码：dossier.py finalize_archive 一处＋ArchiveModal 文案；pytest＋vitest 同步。
