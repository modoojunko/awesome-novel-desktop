# e2e-speedup-infra

## Why

C端 全量 e2e（148 条）单 worker 实测 4.4 分钟，且夜间 CI 连日全红。根因实锤：S端 `/api/web/login` 限流硬编码 30 次/分钟/IP，全量套件 68+ 用户密集登录必超——本地一轮触发 53 次 `rate_limit_exceeded`、级联带崩 28 条用例；昨晚 CI 86 次限流、79 failed。这是结构性红，不是偶发抖动。另有 33 处 `waitForTimeout` 固定等待共 ~34 秒，是「赌时间」的时序脆弱点，也是纯浪费的墙钟。

## What Changes

- S端 `RateLimitMiddleware` 的登录限流阈值从硬编码常量改为环境变量可配（如 `RATE_LIMIT_LOGIN_PER_MIN`，默认 30 不变）；仅本地 docker compose 测试栈注入高值，生产行为零变化。
- C端 e2e 全量 33 处 `waitForTimeout` 固定 sleep 换成条件等待（`expect.poll` 回读断言、`expect(...).toPass()` 终态断言）；唯一例外是 AI 连点防抖用例中的 1500ms——那是被测时序本身，保留并注释说明。
- 不做并行（`workers: 1` 维持）、不做 API 建书播种（用户裁定：界面测试必须走界面）——本 change 只还 CI 绿色基线并压掉赌时间等待。

## Capabilities

### New Capabilities
- `s-api-ratelimit`: S端 API 速率限制的容量口径——登录类敏感端点限流阈值可经环境变量配置，默认值与生产行为保持 30 次/分钟/IP 不变。

### Modified Capabilities

（无——e2e sleep 换条件等待是纯测试基建重构，不改任何产品需求。）

## Impact

- `server/app/interfaces/middleware.py`：`RateLimitMiddleware.LIMIT` 改读环境变量（含非法值兜底回默认 30）。
- `docker-compose.yml`：S端后端服务注入测试栈专用高阈值。
- `client/frontend/e2e/*.spec.ts`：12 个文件 33 处固定 sleep 替换。
- S端单测：钉住「无 env 时默认 30」与「env 注入生效」两条。
- 无用户可见界面改动（无视觉变更、无文案变更、不触共享段、无需原型先行）。
