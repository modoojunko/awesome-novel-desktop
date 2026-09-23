## Why

S web 前端与 S 后端之间目前**没有任何活体契约检查**：e2e 全部自动挂 mock（`server/frontend/e2e/fixtures.ts` 的 auto fixture），CI 环境根本没有 19000 后端；后端单测又用 MockTransport 假装 PostgREST。结果是「后端删路由/改 DTO 字段」在 S web 侧全绿通过，只能靠 nightly C端 e2e 间接撞到或线上探针发现。09-23 复审同时指出 C↔S 共享契约（check-auth / devices）只有 entitlement 一处有机器可查的 fixture 单源。

## What Changes

- S web e2e 新增**真后端活体冒烟档**：独立 spec 目录（直接用 `@playwright/test` base，不挂 auto mock），走 vite proxy 打真后端；`S_LIVE_BASE_URL` 未设时整组 skip（照 UP11_DATA_DIR 先例，避免误连共享栈）。
- nightly 工作流承载活体档：起 S 后端（sqlite 本地库）→ 设 `S_LIVE_BASE_URL` → 真跑冒烟 spec。
- 契约 fixture 单源推广：照 `docs/contracts/entitlement-defaults.json` 先例，为 check-auth 响应契约建 fixture＋两端对拍测试。

## Capabilities

### New Capabilities

- `s-contract-live-check`: S web↔S 后端契约的活体冒烟与契约 fixture 单源。

### Modified Capabilities

（无）

## Design Impact

- 不适用：本 change 只增加测试与 CI 承载，无产品界面改动。

## Impact

- `server/frontend/e2e/live/`（新增活体冒烟 spec）、`server/frontend/playwright.config.ts`（如需 projects 区分）。
- `.github/workflows/server-frontend-ci.yml` 或 e2e-scheduled（活体档接线）。
- `docs/contracts/check-auth.example.json`（新）＋两端对拍测试各一。
