## Why

卷下拆章出卡的**结构性失败重试分支不带任何素材**：`ai_chapter_directions` 首次调用出卡不足 2 张触发重试时，重试只发 system 模板＋一句「请给出 2 到 3 个剧情方向（只输出 JSON）。」——卷纲四问、已拆章节、核心人物、世界铁律、世界观、进场、位置规则、排除清单全部丢失。模型两手空空便凭空编造，2026-10-05 实测用户看到的是与全书设定毫无关系的攻城戏卡（人物韩彻/陆秉全库不存在）。同源日志显示该路径**占历史出卡调用近一半**（30 次主调用对应 27 次重试），且重试是串行的第二次全量生成——一次抽卡从约 7 秒翻倍到约 14 秒，慢和跑偏是同一病灶。此外触发重试的失败原因（`cause`）只拼进重试提示词、不落日志，事后无法定位首调用为何失败。

## What Changes

- **重试复用主调用完整 user 消息**：结构性重试的提示词 SHALL 携带与首调用相同的素材块（⓪位置→⑩世界观）、位置片段、第 N 章引导句与排除清单（D21），仅在 system 尾部追加失败原因提示（既有降温阶梯不变）。
- **失败原因落日志**：触发结构性重试时服务端记录 cause 与尝试序号（仅日志，不出现在卡面）。
- **拆章抽卡 busy 态加阶段进度**：「正在想」态在既有转圈文案下增加阶段列表（复用 `.ex-steps` 词汇与 GEN_STEPS 先例），由前端计时推进，降低 7–14 秒黑盒等待的体感；不引入新状态、新语气档、新组件形态。
- **回归钉子**：后端测试断言「第 N 次重试请求的 user 消息必须含素材标记」，杜绝裸重试回归。
- **不做**：校验松紧度调整（结构性失败率为何约 50% 需先有 cause 日志数据，另立 change）；模型/端点更换；生成流式化。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plan-ai`：三条 Requirement 变更——
  1. 「三方向互斥的验收与降级阶梯」：重试 SHALL 携带完整素材与排除清单；失败原因落日志；
  2. 「拆章素材包与输出契约」：素材包适用域扩至每一次重试调用（重试与首调用同一素材，素材空缺即缺陷）；
  3. 「AI 抽卡四态」：①正在想态增加阶段进度列表（复用既有 `.ex-steps`／进行中 词汇，无新增状态档）。

## Design Impact

- **受影响端**：仅 C端（S端无此弹窗）。
- **屏/弹层清单**：章工作台「拆第六章」抽卡弹窗（`ChapterPlanModal.tsx`）的**正在想（busy）态**；其余三态（出卡失败/只出两套/三方向）不动。
- **对象状态**：仅用既有状态——busy（`ra-spin`＋「进行中」）与完成（`ex-steps em.ok`）；对照状态语言总表 §5，**无新增状态档、无新增对象形态**。组件语气词表（info/ok/warn/err）不动，文案无按钮改动、无内部术语。
- **两端共享段**：不触碰（`.ex-steps` 定义在 C端 `src/design/book.css`，非 base.css 共享段；不需 design-cross）。
- **原型先行**：需要——`docs/design-c/prototypes/book.html` 拆章抽卡 busy 态补阶段列表，在 `ADJUSTMENTS.md` 登记（偏差原因：实现与原型同批落地）。
- **设计工件产出者**：实现侧自查（复用 `.ex-steps` 既有词汇，无新视觉决策）。

## Impact

- **后端**：`client/backend/chapters/ai_plan.py`（重试循环 589–607 行：重试 user 消息改为与首调用同源组装；cause/attempt 日志）；提示词模板 `prompts/chapter_split.prompt` 不改。
- **前端**：`client/frontend/src/components/novel/workbench/ChapterPlanModal.tsx`（busy 态阶段列表）；CSS 复用 `design/book.css` 既有 `.ex-steps`，预计零新增或极少量布局行。
- **设计资产**：`docs/design-c/prototypes/book.html` ＋ `prototypes/ADJUSTMENTS.md` 登记。
- **测试**：`client/backend/tests/test_chapter_plan_ai_t3.py`（重试阶梯用例扩展断言：重试请求含素材标记；既有 fake.calls 断言可能需同步）；`client/frontend/src/__tests__/chapterPlan.test.tsx`（busy 态阶段列表）；相关 e2e（`split-busy` testid 既有用例回归）。
- **行为兼容**：无 API 契约变更（响应形状不变）；无存量数据迁移；出卡质量与延迟向好，无破坏性改动。
