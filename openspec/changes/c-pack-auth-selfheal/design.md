# Design — c-pack-auth-selfheal

## Context

死锁链定诊（2026-10-20 Mac 真机 v0.36 实测，证据存记忆 c-pack-stale-token-deadlock）：

1. 本机 config.json 的 JWT `exp=2026-09-18`（无 uid 旧格式），早过期；
2. `browser_auth(silent=True)`（`client/backend/auth_local/service.py:558-560`）：`check-auth` 回 code 0 且响应不含令牌时，本地有令牌就无条件沿用（注释「保留本地有效令牌」，从不校验）→ tier/`last_login_at` 照写 → UI 恒显已登录；
3. `verify_session` 的 30 天检查看 `last_login_at`，而静默刷新每次重写成 now，永不触发；
4. 本地有令牌时 pair/exchange 分支被遮蔽；其失败返回 `{"code":1,"data":{"message":"请在桌面端重新登录…"}}` 不带 `session_invalid`，前端 `useAuthHeal` 直接忽略——重登信号死路；
5. 换钥 `prompt-pack/key` 带过期 Bearer → S 端 401「无效的令牌」→ `call_server_api` 把 HTTP 401 的 envelope（`code:-1`）与真不可达混同 → sync 全档降完落 `failed/reason=exchange`；
6. 前端 `FAIL_NOTES`（`PromptPackModal.tsx:42`）无 `exchange` 映射 → 通用网络文案。

约束：S 端 JWT 只在浏览器授权时现签落 grant，`pair/exchange` 只回存档 `grant.token`（`pairing.py:132`）——S 端不重签前，未经重新授权的用户换到的仍是死令牌；此过渡期行为必须诚实呈现而非掩盖。

## Goals / Non-Goals

**Goals:**

- 登录态自愈闭环：令牌过期 → pair/exchange 换新 → 落盘 → 包同步自动恢复（S 端重签上线后用户零操作）。
- 失败诚实化：认证类失败与网络/服务不可达在全链路（envelope → 同步器 reason → 弹窗文案/出口）可分辨。
- 配对终局失败有出口：清凭据＋结构化信号＋回登录页，防循环。

**Non-Goals:**

- S 端 pair/exchange 现签重写（另行立项，私有仓 change；本变更只保证过渡期行为可接受）。
- `verify_session` 的 30 天口径改造（令牌保持新鲜后该检查成为冗余但无害的兜底，不动）。
- 弹窗轮询对 `phase=missing/reason=min_client_version` 挂满 180s 的边缘呈现（独立小缺陷，另行处理）。
- 令牌临期主动预刷新（exp 临近窗口换新）——先不做，避免放大 S 端压力；过期即换已够闭环。
- 前端 401 统一踢出出口（`认证失效处理必须经统一出口`）的语义变更——本变更走结构化信号路径，不触碰 HTTP 401 拦截器。

## Decisions

**D1 令牌新鲜度判据＝本地解析 JWT payload 的 `exp`，不做签名校验。**
客户端无私钥，无法验签；exp 只用于「是否值得沿用」的本地判断，安全判定始终由 S 端完成（换钥 401 照拒）。实现为 `auth_local/service.py` 内小函数：三段式 JWT → base64url 解 payload → `exp` 与本地时间比对；不可解析/缺 exp 一律视同过期（宁换勿沿用，pair/exchange 幂等且廉价）。备选「调一次带鉴权端点试活」被否：多一次必败外呼、失败语义仍需本函数兜底，纯增延迟。

**D2 沿用分支改为「有效才沿用，否则落 pair/exchange」，复用既有 exchange 三分支。**
现 `service.py:558-573` 的结构（有本地令牌→沿用；无→exchange→成功/不可达/判败）保持不动，只把「有本地令牌」收紧为「有**有效**本地令牌」；过期令牌自然落进既有 exchange 路径——成功（D4 过渡期兜底）、code -1（静默保留现态）、判败（D3）三分支语义全部现成。不新增第四条路径。

**D3 配对终局失败＝清凭据＋结构化重登信号。**
exchange 判败（配对失败，S 端统一失败形态不可细分）且本地无有效令牌时：沿用 `service.py:640-647` 既有清理**全集**口径（token/username/expires_at/last_login_at/entitlement_fetched_at 清空，tier 置 none，entitlement/tier_catalog 置空，deletion_pending=False——评审 P3：枚举子集会留权益残值，踢出后 UI 仍渲染旧档），返回 `code:1 + data.pairing_broken=true` **独立失效标志**（评审定稿：不复用 `session_invalid`，两类清凭据原因在前端可分辨，登录页文案与诊断观测不串味）＋文案「登录状态已过期，请重新登录；本地作品不受影响」。安全性：本路径只在令牌已死时可达，清凭据不损失任何可用状态；challenge 失配的机器唯一出路就是重登（重授权会重 upsert grant）。
备选「不清凭据只提示」被否：UI 恒显已登录正是本次事故的误导根源。

**D4 过渡期（S 端未重签）换得令牌仍过期＝照常落盘＋诚实失败。**
exchange 成功但换回的令牌 exp 仍过期（S 端回存档旧令牌）：落盘（它是 S 端能给的全部），不标记自愈成功，包同步照常触发并将在换钥处 401 → 弹窗认证失败出口引导重登。不做「换回仍过期就清凭据」：该用户 challenge 是配对的，重授权后即可自愈，清凭据反把「已授权」状态丢掉。

**D5 `call_server_api` HTTP 401 → envelope `code=401`，不再塌缩为 -1。**
非 JSON 体且 status=401（网关形态）同样归 401；5xx/HTML/超时/连接错误维持 -1。影响面核查：`call_server_api` 现有三个调用点——`check-auth` 与 `pair/exchange` 均免鉴权不会 401；`prompt-pack/key` 是唯一 Bearer 消费者。`browser_auth` 对 check-auth 的 `-1` 分支不受影响。

**D6 换钥 401 → 终态 `failed/reason=auth`，跳出降档循环。**
`sync_once` 的 `_tier_candidates` 循环中，code==401 直接 `_set_state("failed", reason="auth")` 返回——认证失败对全档位同真，降档四连是纯放大。403 降档、404 重取 latest 语义不变。

**D7 弹窗认证失败变体＝直驱重授权＋等待授权轮询，不走登录页（评审定稿）。**
`FAIL_NOTES["auth"]` 为完整独立句（如「登录状态需要刷新，请重新授权后再试。」）；failed 态且失败原因为 auth 时，footer 从「复制诊断信息＋重新获取」换为「复制诊断信息＋**重新登录**」（primary）。**「重新登录」SHALL NOT 仅导航回登录页**：登录页挂载即跑静默自动登录（`LoginPage.tsx:80-99`），过渡期静默自愈换回存档死令牌即 code 0 → `navigate('/novels')`——目标 cohort 会被原样弹回作品页，授权面不可达（评审 P1 实锤）。改为复用 `LoginPage.handleBrowserAuth`（`LoginPage.tsx:116-137`）同款流：`POST /auth/browser-auth`（非静默）取 `auth_url` 经壳层桥开系统浏览器；点击后弹窗转入**等待授权**态——短轮询 `/auth/check-auth`（口径同登录页，有轮询上限，超时提供手动复查出口），code 0 即原地重跑 probe/startRun 回到既有进度流（后端 `maybe_after_auth` 亦会自动触发同步，弹窗轮询状态至终态即可衔接）。文案过 §13：动词按钮、无内部术语、补救带可点击出口；auth 变体 SHALL NOT 拼接「手写不受影响，随时可以重试。」后缀（401 重试不会好，与被换掉的重试出口自相矛盾——评审 P2）。与 `tier_denied → 去升级` 的按 reason 换主出口先例同构。

**D8 前端消费＝独立标志 `pairing_broken`＋对称分支（评审定稿）。**
失效信号携独立标志 `data.pairing_broken=true`（不复用 `session_invalid`——「服务端会话作废」与「本机配对失效」两类清凭据原因在前端可分辨，登录页提示文案与诊断观测不串味）。`useAuthHeal` 增对称分支：与 `session_invalid` 同语义消费（清 localStorage 凭据＋`auth_notice` 持久化提示＋回 `#/login`）。本场景无登录页弹回问题：清凭据后本地无令牌，登录页静默自动登录要么换不出令牌、要么直接判败（配对仍失配），不满足自动登录条件，用户可看到登录/授权入口。防循环沿用既有口径。

## Risks / Trade-offs

- **S 端重签未上线前，存量过期用户仍需手动重登一次**（换回旧令牌 → 认证失败出口引导）。这是过渡期可接受中态：从「误报网络问题、无出路」变为「如实告知＋一键重登」。上线顺序建议：S 端重签先合先发（响应形状不变，纯后向兼容），C 端本变更随后发——顺序颠倒不致损，只是自愈闭环晚生效。
- **D3 清凭据依赖「仅死令牌可达」**：若未来 pair/exchange 出现新的判败形态（限流误判为配对失败等），可能误清有效会话。缓解：S 端配对失败走登录类限流清单（既有），且判定仅发生在「本地令牌已无效」前提内；实现测试须钉住「有效令牌永不进入该路径」。
- **时钟偏移**：本机时钟明显偏慢时 exp 校验会误判「仍有效」→ 走老路 401 → 认证失败出口，不出死锁；偏快则多一次无害 exchange。可接受，不做 NTP 级矫正。
- **`pairing_broken` 与 `session_invalid` 并行（D8）**：两个失效标志走同一前端清凭据/导航通道（对称分支），文案由后端下发区分；回归须各钉一条防串味。

## Open Questions

（无——评审后定稿：D8 取独立标志 `pairing_broken`；D7 认证出口定稿为直驱授权页＋等待授权轮询，不回登录页。）
