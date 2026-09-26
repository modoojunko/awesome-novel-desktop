# c-shelf-request-budget — 书架请求预算守卫：阈值 flake 根治（诊断先行）

## Why

书架空闲期请求预算守卫（`shelf-request-budget.spec.ts`，c-session-flip-stability 口径：空闲 3 秒 /api ≤8，本职是抓壳层重挂风暴——实测风暴态 ~20 请求/3 秒）出现**阈值型 flake**：隔离栈全量 e2e 三跑两红（空闲窗 9 > 8）、单独跑绿、CI 语义 retries=1 下重跑即绿。守卫在预算边缘失去判别力：9 与 8 的差值不是风暴，是某个未定位的启动期请求。盲调预算会把守卫废掉，盲改应用可能掩盖真实的多余请求——所以本 change **诊断先行**，结论落地前先拿到请求时间线证据。

全量明细（失败跑实测）：`check-auth ×5、update-check ×4、verify ×4、db-migration/candidates ×3、auth/config ×3、novels ×1、legacy-db/status ×1`（含加载期；空闲窗内的 9 个构成待诊断）。

## What Changes

- **Phase A 诊断（本 change 的硬交付物）**：在应用侧给书架启动链的每个 /api 请求打**发起方标记**（调用点 → 请求 URL → 相对书架首屏 ready 的毫秒偏移），产出一份可复核的时间线报告；对失败跑与通过跑各采一轮，**用证据点名第 9 个请求是谁、由谁触发**。
- **Phase B 按结论三选一落地**：
  - 结论＝「应用确有多余/重复请求」（如同一段落内 verify/check-auth 反复重打、candidates 重复扫描）→ **消请求**（合并调用点/加去重/收窄重试），不改预算数字；
  - 结论＝「请求都合法，只是启动链比立预算时多了一步」（如 db-generation 的候选扫描、legacy-db/status 探针均为 #464 后新增）→ **校准预算**并在测试注释里写明新请求的来源依据；
  - 结论＝「合法但窗口相位请求」（周期性 poller 跨界落入 3 秒窗）→ **对齐窗口口径或钉住 poller 相位**，预算数字视对齐结果决定是否调整。
- 两种结论都要求：修完后**全量 e2e 连跑三绿**（预算用例零失败零 flaky）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend-auth-heal`: 「书架空闲期请求预算」场景——预算数字 SHALL 按本 change 的诊断结论校准（校准说明＝时间线证据，进测试注释与本 change 归档记录）；重挂风暴的判别力 SHALL 保留（风暴态 ~20 请求/3 秒必须仍然必红）。

## Impact

- `client/frontend/e2e/shelf-request-budget.spec.ts`；Phase B 消请求路径可能触达 `NovelListPage`/启动握手相关 hooks（以诊断结论为准）。
- 不触碰书架的任何用户可见行为。

## Design Impact

- 诊断插桩为 e2e/开发侧手段，不进生产构建；无 UI 变化、无原型需求；不触共享段。
