## Why

卷下拆章（c-chapter-plan-ai，本轮合入）自带一条 **P0 数据丢失路径**与一条 P1 脏写路径，均在保存链上：

1. **回改保存清空正文与子表**：`chapterPlanApi.saveEdit` 只发五个剧情字段的**局部 PUT**，而后端统一写入口对缺失键按空写（`prose = data.get("prose") or ""`、子表 `clear()` 后按 data 重建）——在有正文的章上「改这一章 → 保存这一章」会清空正文、字数归零、章纲子表全清。入口可达：章纲树铅笔行、卷工作台派生视图行（含已归档章）。
2. **读卡失败留上一章草稿且可保存**：`openEdit` 失败路径不清 draft、保存钮仍可用——保存即把上一章的五段写进目标章（叠加第 1 条连正文一起清）。

另有四处状态卫生问题：进场锚兜底因 token 计数器串台而不可达（换卷残留上一卷进场）、回改保存成功却提示「已排上」、自检请求无 token 守卫（晚到响应覆盖新卡面）、搬运发起失败把 409 当普通错误（死分支）。

## What Changes

- `saveEdit` 改「读全量 → 合并五段 → 全量 PUT」（与章纲保存链同路），缺键不再清空既有内容；相应前端契约测试改口径。
- `openEdit` 失败时清空 draft 并禁用保存，仅留重试/关闭。
- 进场锚 catch 改比正确计数器；`open*` 时清 `entry`（不残留上一卷）。
- 回改保存回执改为「已保存」语义（与「排上」区分）。
- AI 自检加 token 守卫与按钮 busy。
- 搬运发起失败的冲突识别按 HTTP 409（不再靠文案子串匹配）——与 c-db-version-hardening 同批协调。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plan-ai`: 新增「回改保存必须保全既有内容」「读卡失败不得脏草稿可保存」「进场锚与自检的竞态守卫」「保存回执与实际动作一致」四条要求。

## Design Impact

- **受影响端**：C端（不触 S端）。
- **受影响的屏/弹层**：拆章弹窗（ChapterPlanModal，手写/回改态）、卷工作台派生视图行、章纲树行。
- **用到或新增的对象状态**：err 语气提示与置忙/禁用态（保存钮）；回执文案（「已保存」vs「已排上」）——既有词汇，无新增形态。
- **是否触碰两端共享段**：否。
- **是否需要原型先行**：需要——保存钮禁用态与回执文案在卡面底条有像素增量，对照卷下拆章原型与 `ADJUSTMENTS.md` 登记。
- **设计工件产出**：实现侧自查（复用既有底条按钮态与文案口径）。

## Impact

- 前端：`lib/chapterPlanApi.ts`、`hooks/useChapterPlan.ts`、`components/novel/ChapterPlanModal.tsx`、`components/novel/NovelWorkspace.tsx`、`components/novel/LegacyMigrateModal.tsx`（409 判定）。
- 测试：`__tests__/chapterPlan.test.tsx`（「缺字段按空写」契约测试改口径）、e2e 拆章链路。
- 后端不改（写语义维持「显式全量 PUT」；前端改为发全量）。
