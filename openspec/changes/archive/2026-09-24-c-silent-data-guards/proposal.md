## Why

C端 有五个「失败即当空/当没发生」的点，其中一处是真实数据丢失路径：

1. **主线卡加载失败落空卡且可保存**（P1）：`useStoryArc` 加载失败时把 `EMPTY_ARC` 记为干净基线，表单显示为空；用户补两句点保存，whole-card PUT 把库里已有的全景/结局整卡覆盖。
2. 完本弹窗伏笔清单加载失败静默置空数组，用户在「无进行中伏笔」的假象下点完本确认。
3. 建卷/建章入口无双发闸（本轮新合入后入口从 3 处扩到 6 处）：双击即两次 `POST /volumes`，撞 `UNIQUE(novel_id, volume_no)` 报 500——与 dfceb17d 刚修的双发同签名。
4. `LicenseProvider` 的模块级 `cachedVerify` 在登出时不清理：换账号登录后最长约一分钟内，权益徽章与功能判定显示上一账号的档位。
5. 提示词总览页逐章串行请求（300 章的书 = 300 个串行请求），且卷章加载失败静默呈现为「没有卷章」。

共同点：失败没有可感知信号，用户基于假状态做决定——其中第 1、2 条会直接改写或误判数据。

## What Changes

- 主线卡：加载失败时进入失败态（err 语气 + 重试出口）并禁用保存，不再以空卡作可保存基线。
- 完本弹窗：伏笔清单失败时显式呈现并禁用完本确认钮。
- 建卷/建章：所有入口加 in-flight 闸（提交中置忙禁用），消除双发 500。
- 权益缓存：登出/换号时清除快照缓存与刷新节流状态。
- 提示词总览：取数改为批量或有界并行（不再逐章串行），失败显式呈现。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `storyline-settings`: 新增「主线卡加载失败不得整卡覆盖」要求。
- `foreshadow-settings`: 新增「完本核对清单失败必须显式」要求。
- `workbench`: 新增「建卷建章入口防重复提交」要求。
- `entitlement-sync`: 新增「权益缓存随登出/换号失效」要求。
- `prompt-crafting`: 新增「章提示词总览取数纪律」要求。

## Design Impact

- **受影响端**：C端（不触 S端）。
- **受影响的屏/弹层**：设定·主线卡（StoryArcForm）、完本确认弹窗（FinishModal）、空书架/空书落点卡与左栏加号等建卷建章入口（NovelWorkspace）、提示词总览页（PromptManagementPage）。
- **用到或新增的对象状态**：err 语气提示（失败态文案行 + 重试出口）、按钮置忙/禁用态（提交中）；均为既有词汇，不新增形态。
- **是否触碰两端共享段**：否（不触 base.css 令牌与 pill/notice/panel/f-err 家族定义）。
- **是否需要原型先行**：需要——失败态与置忙态在受影响屏上有像素增量；无对应原型的屏在 ADJUSTMENTS.md 登记「无原型基线」。
- **设计工件产出**：实现侧自查（复用既有 notice/按钮态词汇与 §13 文案口径），无需设计侧会话。

## Impact

- 前端：`useStoryArc.ts`、`FinishModal.tsx`、`NovelWorkspace.tsx`、`useWorkbench.ts`、`LicenseProvider.tsx`、`lib/auth.ts`、`PromptManagementPage.tsx`。
- 测试：相关 vitest 单测与 e2e（空书建卷/完本/提示词总览）更新。
- 无后端接口变更（服务端守卫维持现状，仅前端不再产生假状态）。
