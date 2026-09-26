## Context

预算守卫（`shelf-request-budget.spec.ts`，规格住 `frontend-auth-heal`「壳层会话翻转不重挂无关组件」）出现阈值型 flake：隔离栈全量 e2e 三跑两红（空闲窗 9 > 8）、单独跑绿、CI 语义 retries=1 重跑即绿。失败跑的全量明细：`check-auth ×5、update-check ×4、verify ×4、db-migration/candidates ×3、auth/config ×3、novels ×1、legacy-db/status ×1`（含加载期；空闲窗内的 9 个构成未知——明细打印的是整窗累计 map，不含空闲子集）。本 change 的 c-og-slim-v2 相关改动（章纲字段）零书架启动链足迹，基线栈对照实验也证明同批红均为既有。

## Goals / Non-Goals

**Goals**
- 拿到书架启动链的**请求时间线证据**：每个 /api 请求的发起调用点、相对首屏 ready 的毫秒偏移，失败跑与通过跑各一份。
- 点名空闲窗第 9 个请求是谁、由谁触发，并按结论落地（消请求或校准预算）。
- 全量 e2e 三连绿（预算用例零失败零 flaky）。

**Non-Goals**
- 不做盲调预算（9>8 就把 8 改 10 而给不出依据＝校准到噪声）。
- 不动壳层会话翻转的既有修复（恒挂载语义）。
- 诊断插桩不进生产构建的行为路径。

## Decisions

**D1 诊断手段＝e2e 侧时间线采集 + 应用侧发起方标记，两份证据对齐。**
- e2e 侧：`shelf-request-budget.spec.ts` 增加临时「时间线模式」（env 开关）：记录每个 /api 请求的 `URL + 相对首屏 ready 的偏移 + stack 摘要`（`page.on('request')` 不可得调用栈，改在应用请求栈的出口处打标记）。
- 应用侧：中心请求栈的请求出口（`lib/api`）在 `import.meta.env.DEV || 时间线开关` 时给每个请求挂 `X-Req-Tag` 头（调用点符号名）或以 `performance.mark` 记录——e2e 从请求头读标记即可对齐「哪个调用点发的」。
- 备选被否：只看 Network 面板人工数（不可复核、进不了归档）。

**D2 结论二选一的判定门（写死在 tasks，防漂移成「调完数字就收工」）**：
- 时间线显示同一调用点在空闲窗内重复触发 → 消重复（合并调用点/去重/收窄重试），预算数字不动；
- 时间线显示是 #464 之后新增的合法启动请求（db-generation 候选扫描、legacy-db/status 探针类）→ 预算校准为其稳态值＋测试注释记录来源 change。
- 两门都走完仍 9>8 → 回到本 change 追加诊断，SHALL NOT 以无依据调参收场。

**D3 插桩的实现形态**：`lib/api` 请求出口已有统一封装（认证失效统一出口所在层），标记挂在同一层；生产构建由 env 开关关闭，包体零影响。调用点符号名的穿参成本：数十处调用点逐个传参不现实，改用 DEV 下 `Error().stack` 反解调用帧（`request()` 入口取 `new Error().stack`，解析第二层函数名），e2e 侧从 `X-Debug-Req-Tag` 头读——零穿参成本、生产构建关 env 后零开销。

## Risks / Trade-offs

- [时间线只在失败跑才有意义] flake 与时序相关 → 诊断跑至少一次「红」一次「绿」各采一份，对比空闲窗差异而非绝对值。
- [X-Req-Tag 头进后端日志] → 后端不记录未知头，无泄露面；头名加 `X-Debug-` 前缀并仅诊断模式携带。
- [自定义头触发 CORS preflight] → e2e 走 nginx 同源代理，不跨 origin，无 preflight；但若诊断标记头落在非代理 origin 上，会自己制造 preflight——设计已覆盖（仅同源诊断模式携带）。
- [诊断结论推翻 D2 预设] → 判定门只认证据；若第 9 个请求是合法新增，校准并归档依据。
- [check-auth ×5 本身可疑] → spec 还 stub 了它，5 次大概率是壳层重挂（消重复门的典型目标）；诊断时间线 SHALL 能区分「同一调用点重复触发」与「多个调用点各触发一次」。

## Migration Plan

Phase A 诊断（1 个提交，含时间线开关与采集脚本）→ 结论写入本 change 的 design 附录 → Phase B 按结论落地 → 全量 e2e 三连绿 → 归档。

## Open Questions

（无——判定门已扩至三门，诊断结论落在三门之内。）
