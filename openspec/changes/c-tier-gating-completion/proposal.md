## Why

四档套餐 10-05 已上线，但 10-06 全量审计实锤 **6 处门禁未达标**：三个规格明文「原免费只读例外上移标准档」的 AI 端点（章自检/卷体检/盘点只读）后端仍是免费例外通道；文风蒸馏（MAX 件）挂的却是标准档 key 且前后端均无 `style-quant` 锁点；端点→key 对拍守卫因框架懒路由**空转恒绿**——这正是上述漂移没被 CI 抓住的原因。另有 `POST /api/novels` 死标注与 `ai-backfill` 回填端点真调 AI 却裸奔。后果：免费/标准档可越过套餐边界白嫖付费能力（BYOK 前提下），与「AI 能力按档逐层解锁」的定价承诺不符。

## What Changes

- **后端补 3 处失守门**（规格见 tier-plan-four-tiers 的 tier-access/volume-plan-ai/chapter-plan-ai delta，本次只补实现）：
  - `POST /chapters/ai-selfcheck`（章自检 AI 短评）→ `chapter-review`（标准档起）；
  - `POST /volumes/{ref}/ai/check`（卷体检）→ `ai-plan`（标准档起）；
  - `POST /chapters/{ref}/cast/ai-review`（人物盘点只读）→ `ai-plan`（标准档起）。
- **前端自检按钮真正拦截**：免费档点「AI 看一眼这一章」不再发起请求（规格：SHALL NOT 发起调用），改走统一升级出口；原「需开通」胶囊保留。
- **挪 2 处 key**（口径与 features.ts / entitlement-defaults v2 对齐）：
  - `POST /settings/ai/style-distill/{action}`（文风蒸馏）`settings-ai-fields`→`style-quant`（MAX）；文风面板右栏「蒸馏我的文风」行按 `style-quant` 加行锁，标准档及以下置灰＋「MAX 专属」；
  - `POST /settings/ai/style/{action}`（文风三区 AI）`settings-ai-fields`→`style-suggest`（标准；档位结果不变，纯语义/403 文案归位）。
- **守卫测试修复＋升级为双向对拍**：扫描必须穿透 starlette ≥1.6 的 `_IncludedRouter` 懒路由包装（原 `isinstance(route, APIRoute)` 遍历恒空）；断言「已挂 key 的端点必挂 `require_ai_access`」防死标注，并锁定关键 key 的消费点齐全。
- **删除死标注**：`POST /api/novels` 的 `@ai_feature("ai-plan")`（无门依赖、零行为，留着会误导后来人补门误伤免费建书）。
- **`workflow/ai-backfill` step1/step2 挂 `ai-plan`**（评审待拍板 #12 收口：确定性 AI 提取＝建书辅助 AI，与 `/ai/suggest-meta` 同档；status/confirm 纯状态写入不挂）。**BREAKING**：对直接调用方 403 语义生效；当前仓库无客户端消费点，实际零冲击。

明确不做：不改档位矩阵与 key 词汇表本身；不动 `ai-check`（六类冲突检测已按 10-05 终拍挂 `ai-generate`/PRO）；不做入口隐藏（入口一律可见，只加锁）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `tier-access`: 新增两条要求——「端点门禁对拍守卫」（扫描须真实覆盖全部路由＋已挂 key 必挂门）与「导入回填 AI 步骤门禁」（ai-backfill step1/step2 归 `ai-plan`，status/confirm 不挂）。三个只读端点收门与文风 key 归属的规格已在 tier-plan-four-tiers 落定，本 change 不重复立法。

## Impact

- `client/backend`：`chapters/ai_plan.py`、`volumes/ai_plan.py`、`chapters/ai_cast.py`、`settings/ai_router.py`、`novels/router.py`、`workflow/router.py`
- `client/backend/tests`：`test_ai_feature_registry.py`（修复＋双向断言）、`test_ai_feature_http.py`（新端点档位钉子）、受影响存量测试的档位种子（style/volume/cast/chapter-plan 族）
- `client/frontend`：`hooks/useChapterPlan.ts`＋`components/novel/workbench/ChapterPlanModal.tsx`（自检拦截）、`components/novel/workbench/SettingsView.tsx`（蒸馏行锁）、对应 vitest
- `client/frontend/e2e`：`style-quant.spec.ts` 种子 trial→max、`chapter-plan/cast-review/volume-plan` 补档位断言
- 无 S端/发布链改动；无 DDL；无新 key
- 文档顺带：tier-plan-four-tiers 的 volume-plan-ai/workbench delta 两处与 10-05 终拍冲突的口径（六类检查、文风建议 key）在其归档 sync 前对齐（见 design §5）

## Design Impact

- 受影响端：仅 C端（桌面客户端）。
- 受影响屏/弹层：①拆章弹窗（ChapterPlanModal）手写卡底条「AI 看一眼这一章」——免费档点击由「照跑」改为升级引导；②设定视图·文风面板右栏「蒸馏我的文风」行——标准档及以下置灰＋档位提示。卷体检/盘点只读前端已锁，仅后端补门，无界面变化。
- 对象状态：沿用既有行锁口径（rail-locked/置灰＋「需开通／需 PRO／需 MAX」提示，AiAssistPanel 行锁与 `upgradeHintOf` 单源先例），不新增状态词。
- 两端共享段：不触碰。原型先行：不需要（无新视觉形态，锁态复用既有样式）。
- 设计工件产出：实现侧自查。
