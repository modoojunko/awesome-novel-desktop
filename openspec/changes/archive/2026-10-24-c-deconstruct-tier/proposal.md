# C端 拆书/导入三档切分（c-deconstruct-tier）

## Why

拆书工具（AI 拆书/任务/产物导出/产物建书）当前对所有登录用户开放，没有任何权益键与门禁；而 MAX 售卖页把「拆书成设定」列为 MAX 权益。权益与售卖两边互相矛盾：要么免费用户白用 MAX 卖点，要么卖点虚假。boss 2026-10-23 拍板按能力三档切分，把拆书正式纳入权益体系。

## What Changes

- 新增 feature key：`deconstruct`（PRO 起、trial 同权）、`deconstruct-import`（仅 MAX）。
- 门禁切分：正文导入免费不动；AI 拆书（新建/续拆/重试上传/导出 markdown）挂 `deconstruct`；拆书产物一键建书挂 `deconstruct-import`；任务清单/详情/产物预览/取消不设门。
- 前端：创建页与详情出口（建书/导出）可见＋锁定，锁点走对应档位升级弹窗。
- 旧权益快照兼容：隐式放行名单改为按 key 最低档（deconstruct=PRO、deconstruct-import=MAX），前后端同口径。
- 售卖面同步：S端 PlansPage/tierCopy/seed selling_points 把拆书改标 PRO 起、建书 MAX，去「即将上线」。

## Impact

- Affected specs: `tier-gating`（Feature capability registry 增两键）、`deconstruct-book`（新增档位门禁 requirement）
- Affected code: `client/backend/deconstruct/router.py`、`auth_local/{deps,service}.py`、`docs/contracts/entitlement-defaults.json`、`client/frontend/src/lib/features.ts`、`hooks/useTier.ts`、`components/tools/{CreateTaskPage,TaskDetailPage}.tsx`、S端 `server/app/config.py`、`seed_four_tiers.sql`、`PlansPage.vue`、`tierCopy.ts`
- 定案记录：memory entitlement-alignment-audit / deconstruct-tier-split（2026-10-23 grill 拍板）
