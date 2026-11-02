# Proposal: c-kb-field-labels

## Why

boss 实报（2026-11-02 截图）：知识库详情抽屉的字段名直接显示英文键（archetype / gender / background…），应显示中文。前一版按「通用、不为角色单独搞字段显示」实现了原键平铺——机制没错，缺的是**通用的中文标签层**。

## What Changes

- 新增 `src/lib/kbFieldLabels.ts`：**一张键 → 中文标签字典**，任何概念（文风/文笔/世界/角色/手法）同一套查找；同一键在不同概念语义不同时按概念消歧（role：角色＝定位、文风＝声音角色）；字典未收录的键回退原键（不编造）。
- 角色档案八格与认知十一格**复用角色域唯一事实源** `characterModel.ts`（后端 `settings/character_model.py` 的逐字镜像），不手抄第二份标签。
- 枚举值同挂中文（世界分区 stage→世界舞台、槽位 slot 值域、口癖严重度、布尔 true/false→是/否），未知值回退原值。
- 抽屉渲染接入：`dt`＝中文标签、`dd`＝中文值；仍是同一套通用渲染，SHALL NOT 为某概念定制布局。

## Impact

- specs: knowledge-base（MODIFIED 知识库浏览界面——详情抽屉场景由「键名原样」改为「中文标签＋未知键回退」）
- 代码：lib/kbFieldLabels.ts（新）＋KnowledgeBasePage 抽屉接入＋coverage-contract 登记
- 测试：kbFieldLabels.test.ts（字典/消歧/枚举/回退 7 钉）＋抽屉断言改中文＋未知键回退钉
