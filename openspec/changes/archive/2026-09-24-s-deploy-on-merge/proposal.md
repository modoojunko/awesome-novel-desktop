## Why

S端 发布链路「合 main 不部署、tag 才发」使 main 与线上可以无限期错位（复审 P3：规格归档≠已上线，前端改动无预览面）。仓库已存在独立的 **test 云环境**（`d1ghsr86ra814c12c`，托管 `novel-s-web-ai-novel-test` 静态站与 C端 更新源 CDN）——合 main 后把 S 前端自动发布到该站，即可让 main 的前端立即可见可验，且**完全不触碰生产**。

## What Changes

- 新增工作流 `.github/workflows/s-web-test-deploy.yml`：push 到 main（paths 限 server/frontend/**、brand/**、本 workflow）→ 以生产同款配方构建（VITE_API_BASE=生产后端、备案 secrets → .env.production.local）→ `tcb app deploy novel-s-web-ai-novel-test --env-id d1ghsr86ra814c12c`。
- 后端**不在**自动发布范围（仍 tag 手动发生产）；生产 `novel-s-web`/`novel-s-server` 零接触。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——纯 CI/发布基建，skip_specs: true。）

## Design Impact

- 不适用：无产品界面改动。

## Impact

- 新增 `.github/workflows/s-web-test-deploy.yml`；无产品代码改动。
- 复用既有 `secrets.TCB_API_KEY`（账号级凭据，可跨环境）与 `vars.TCB_BACKEND_DOMAIN`、`secrets.VITE_BEIAN_*`；不新增 secrets。
- ⚠️ test 环境的托管应用标识取自既有 URL（`novel-s-web-ai-novel-test`）；若平台侧标识不同，首跑即失败且仅改一行。
