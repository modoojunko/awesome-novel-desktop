# Tasks — e2e-speedup-infra

## 1. 双端影响判定（规则要求的首任务）

- [x] 1.1 判定本 change 无用户可见界面改动（S端中间件容量参数 + C端 e2e 测试代码），不触两端共享段、无原型先行义务；结论记入 proposal「Impact」——已判定，无需设计工件。

## 2. S端限流 env 化

- [x] 2.1 `server/app/interfaces/middleware.py`：`RateLimitMiddleware.LIMIT` 改为启动时读 `RATE_LIMIT_LOGIN_PER_MIN`，int 解析失败/缺省/非正数回落 30；保留现注释并补一行 env 说明。
- [x] 2.2 S端单测（`tests/` 下 middleware 对应测试文件）：① 无 env 默认 30 ② env=600 生效 ③ env=abc/0/-5 回落 30。三例同文件。
- [x] 2.3 `docker-compose.yml`：S端后端服务 environment 注入 `RATE_LIMIT_LOGIN_PER_MIN: "600"`，注释说明仅测试栈生效。

## 3. C端 e2e sleep 换条件等待

- [x] 3.1 防抖落库类（实为 7 处：settings-forms ×5——含复查新发现的 1110 认知区、creation-flow ×1、foreshadow waitDebounce 助手×7 调用点）：`waitForTimeout` → `pollBackend` 后端轮询（helpers 新增）；foreshadow 用「700ms 无新 hooks PATCH＝串行队列排空」判据（networkidle 在已静默页会瞬时返回，实测踩坑已注释）。
- [x] 3.2 动画收敛类（6 处：design-parity 三件套、ui-spec-parity、landing-view）：`waitForTimeout(700–800)` → 终态元素 expect 自动重试或 `toPass()`。
- [x] 3.3 杂项类（其余 spec 的 120–2500ms）：逐条判断——等网络的改条件等待，等动效的改终态断言；`free-writing-flow` 节流窗口 1500ms 保留并注释「被测时序，非脆弱等待」。
- [x] 3.4 全量 grep 复核：`waitForTimeout` 仅剩「被测时序」注释标记的用例。

## 4. 回归

- [x] 4.1 S端：`pytest tests/` 375 passed / 1 failed——唯一红=test_web_api::test_success_tier_trial 为午夜时间穿越存量（expires_at=昨日+7 vs today 已翻日），主仓 main 同跑同红，与本 change 无关；新增 10 条限流单测全绿。
- [x] 4.2 C端：`tsc --noEmit` + `vitest` 全绿（e2e 目录不进 vitest，跑门禁确认无意外）。
- [x] 4.3 C端全量 e2e（worktree 隔离栈，单 worker）：136 passed / 1 failed（session-invalid :10 顺序依赖竞态=存量，基线全量同签名红、单跑 2/2 绿，见 c-session-flip-stability tasks 5.2）/ 14 skipped（parity 家族按设计跳过）；S端日志 `rate_limit_exceeded`=0（346 次登录全放行，基线为 53 次限流 28 条级联红）。wall clock 5.5m：与基线 4.4m 不可直接比——基线有 28 条被限流秒挂的假快；全绿集运行时 5.5m，再快需并行（用户已拍板暂不做）。
- [x] 4.4 门禁输出：C端 `design:lint` + `design:check` 全绿（parity 3 屏过，零像素漂移）；S端 `design:lint` 存量红（site-beian.ts 警徽 emoji，主仓同红、非本 change 引入）。无共享段改动，design-cross 不适用（依据 1.1 判定）。
