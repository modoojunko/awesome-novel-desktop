# Design — e2e-speedup-infra

## Context

诊断结论（2026-09-16，实测）：

- 限流：`server/app/interfaces/middleware.py` `RateLimitMiddleware`，`SENSITIVE_PATHS = {"/api/authorize", "/api/web/login"}`，`LIMIT = 30`（类常量，注释记载「5→30：吸收 E2E 套件的登录突发」），`WINDOW = 60` 秒滑动窗口，仅 POST。全量套件 68+ 用户登录突发必超，本地 53 次、CI 86 次触发。
- 固定 sleep：`client/frontend/e2e/` 12 个 spec 共 33 处 `waitForTimeout`，合计 ~34s。三类用途：①防抖 PATCH 落库（900–1200ms ×7）②page-enter 动画收敛（700–800ms ×6）③落地页动效/节流窗口等杂项（120–2500ms ×20）。

## Goals / Non-Goals

**Goals**
- 全量 e2e 0 次限流触发，夜间 CI 恢复绿色基线。
- 固定 sleep 归零（唯一例外：被测时序本身），消灭「赌时间」脆弱点。

**Non-Goals**
- 不做 worker 并行（用户拍板方案 B）。
- 不做建书 API 播种（用户裁定：界面测试必须走界面）。
- 不改限流算法/窗口/路径清单，只开放阈值口径。

## Decisions

1. **env 名取 `RATE_LIMIT_LOGIN_PER_MIN`**：值域=每 60 秒每 IP 允许的 POST 次数，与现常量语义逐字对应，读值处 `int(env)` 包 try/except 回落 30。生效时机=进程启动（类属性求值），不做热更新。
2. **只对测试栈注入**：`docker-compose.yml` 的 S端后端服务 environment 里加 `RATE_LIMIT_LOGIN_PER_MIN: "600"`。生产部署链路（CloudBase EnvParams、CI 镜像）不带该变量 → 默认 30，生产零变化。600 的取值依据：全量 68+ 登录集中在 ~264s 内，并行组内的短时峰值约 30/s，留 2 倍余量。
3. **sleep 替换三分类**（逐条保留原注释意图）：
   - 防抖落库 → `expect.poll(() => 回读 GET, { timeout })` 断言落库值；
   - 动画/渲染收敛 → `expect(locator).toPass()` 或对终态元素的常规 expect 自动重试；
   - 被测时序（AI 连点只发 1 请求的节流窗口）→ **保留** 1500ms 并注释「被测时序，非脆弱等待」。
4. 单测两条：默认值 30；env 注入生效。非法值兜底并入默认值用例。

## Risks / Trade-offs

- 测试栈高阈值只防「误伤自己」，防爆破能力由生产默认 30 承担——可接受，该 env 生产不可见。
- `expect.poll` 依赖条件最终成立，若产品回归会以 timeout 形式暴露（与原 sleep 的「假绿」相比是改善，但单条失败耗时上升）——poll timeout 沿用 Playwright 默认 5s，用例内不另设长超时。

## Migration Plan

一步落地，无数据/契约迁移。合并后首轮本地全量 + 次日 nightly 即为验收场。

## Open Questions

（无）
