## 1. 后端（拆卷 volumes/ai_plan.py）

- [x] 1.1 `ExcludeItem` 模型＋`PlanLineBody.exclude`（≤9 条）；`_exclude_block` 中性禁令块（拼 material_blocks，模板零改动）
- [x] 1.2 `_drop_excluded_plans`（同轴且走向相似才丢）接入 options：首轮丢→不足 2 套触发既有重试（带排除原因）→重试后再丢
- [x] 1.3 pytest：撞车套丢弃、异轴同句保留（短串噪声守卫）、不足 2 套走重试、禁令块进 system

## 2. 后端（拆章 chapters/ai_plan.py）

- [x] 2.1 `DirectionsBody.exclude`＋`_exclude_block` 进素材；`_drop_excluded_directions`（同轴且 one_liner 相似才丢，keep_map 对齐名次映射）接入首轮与重试轮
- [x] 2.2 pytest：撞车卡丢弃且名次对齐、丢卡提示在场、不足 2 张走既有阶梯、禁令块进 system

## 3. 前端（会话跟目标走）

- [x] 3.1 `lib/drawSession.ts`：localStorage 存取＋appendExclude（3 批 9 条上限）＋key 构造（卷/章）
- [x] 3.2 `chapterPlanApi.directions`／`volumePlanApi.options` 增可选 exclude 入参
- [x] 3.3 `useChapterPlan`：批次 oneLiners 入 state；openAi 恢复优先（内存批→localStorage→重抽）；redraw 带排除；adopt 成功即清；freshRedraw 逃生口；ChapterPlanModal 增「从头再来」
- [x] 3.4 `useVolumePlan`：同构（open 同卷恢复；redraw 带排除；confirm 成卷即清；freshRedraw；PickCardsModal 增「从头再来」）
- [x] 3.5 vitest：重开不重抽（无第二次 API 调用）、redraw 请求体带 exclude、fresh 清空、adopt/confirm 后 storage 清空

## 4. 门禁

- [x] 4.1 后端全量 pytest 绿；ruff 零新增
- [x] 4.2 前端 vitest（触及文件）＋tsc 零错
- [x] 4.3 openspec validate --strict；spec 措辞与实现逐条对上
