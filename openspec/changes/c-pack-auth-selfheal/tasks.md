# Tasks — c-pack-auth-selfheal

## 1. 原型先行（C端 弹窗失败态认证变体）

- [x] 1.1 `docs/design-c/prototypes/list.html`：demo-bar「写作能力弹窗 · 5 态」增「认证失败」变体及其等待授权子态——失败态完整独立文案「登录状态需要刷新，请重新授权后再试。手写不受影响。」（无「随时可以重试」后缀），footer＝「复制诊断信息」（ghost）＋「重新登录」（primary）；等待授权子态示轮询提示与超时后的手动复查出口。验证：浏览器打开原型经 demo-bar 切换可见该变体与子态
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 尾插登记条目（c-pack-auth-selfheal：变体动机＝换钥 401 死锁定诊，认证类失败主出口换「重新登录」，与 tier_denied→去升级同构；追加式尾插，勿动既有条目）。验证：条目在册且既有条目零改动

## 2. C端 后端：登录态自愈（auth_local/service.py）

- [x] 2.1 新增令牌新鲜度解析：三段式 JWT → base64url 解 payload → 校验 `exp`；不可解析/缺 `exp` 视同过期。单测钉五态：有效／过期／缺 exp／非 JWT／payload 畸形。验证：pytest 新用例绿
- [x] 2.2 `browser_auth(silent=True)` 沿用分支收紧为「有效才沿用」：过期令牌落 pair/exchange；换新成功落盘并照常触发 `maybe_after_auth`；换回令牌仍过期照常落盘（不标记自愈成功）；exchange code -1 静默保留现态。单测钉四臂：过期+exchange 成功／过期+exchange 不可达／有效令牌不发起 exchange／换回仍过期。验证：pytest 新用例绿
- [x] 2.3 配对终局失败路径：exchange 判败且本地无有效令牌 → 按**既有失效清理全集**同款清凭据（`service.py` 既有失效清理口径：token/username/expires_at/last_login_at/entitlement_fetched_at 清空，tier=none，entitlement/tier_catalog 置空，deletion_pending=False——评审 P3：枚举子集会留权益残值，踢出后 UI 仍渲染旧档）＋返回独立失效标志 `data.pairing_broken=true`（D8 评审定稿，不复用 `session_invalid`）＋文案「登录状态已过期，请重新登录；本地作品不受影响」。单测钉：清理字段全集；**有效令牌永不进入该路径**（守卫钉）；`pairing_broken` 与 `session_invalid` 提示文案互不串味。验证：pytest 新用例绿
- [x] 2.4 `call_server_api`：HTTP 401（含非 JSON 401 体）→ envelope `code=401`；超时/连接错误/5xx HTML 维持 `code=-1`。单测钉三态。验证：pytest 新用例绿，存量 check-auth/pair-exchange 用例零改动绿

## 3. C端 后端：换钥同步（prompt_pack/sync.py）

- [x] 3.1 `sync_once` 换钥循环：code==401 → `_set_state("failed", reason="auth")` 即刻返回，不进入降档候选；403 降档、404 重取 latest 语义不变。单测钉三态：401 即断（不发起降档换钥）／403 照旧降档／404 照旧重取。验证：pytest 新用例绿

## 4. C端 前端（PromptPackModal）

- [x] 4.1 `FAIL_NOTES` 增 `auth` 映射（完整独立句，如「登录状态需要刷新，请重新授权后再试。」）；failed 态且失败原因为 auth 时 footer 换「复制诊断信息」＋「重新登录」（primary，带 `data-testid="pack-go-login"`）；**auth 变体 SHALL NOT 拼接「手写不受影响，随时可以重试。」后缀**（评审 P2：401 重试不会好，与被换掉的重试出口自相矛盾）。「重新登录」直驱重授权流（评审 P1）：`POST /auth/browser-auth`（非静默）取 `auth_url` 经壳层桥开系统浏览器（`LoginPage.handleBrowserAuth` 同款），**SHALL NOT 仅导航 `#/login`**（登录页静默自动登录会把失效令牌 cohort 自动弹回作品页，授权面不可达）；点击后弹窗转等待授权态：短轮询 `/auth/check-auth`（有轮询上限，超时给手动复查出口），code 0 即原地重跑 probe/startRun 回既有进度流。文案不含 401/令牌/换钥等内部术语。验证：vitest 新用例——auth 失败呈现独立文案与双出口且无「随时可以重试」后缀；非 auth 失败维持「重新获取」既有出口；点击重新登录发起 browser-auth 开授权页而非路由跳转；等待授权轮询 code 0 后回到进度流；超时出现手动复查出口

## 5. S 端联动协调（跨仓，不在本仓实施）

- [ ] 5.1 S 端私有仓另立 `s-` 前缀 change：pair/exchange 凭 challenge 验明设备后**现签**新 JWT（`sign_jwt(username, uid, ver=user.token_version)`）并回写 grant.token，响应形状不变；上线顺序建议 S 端先行（纯后向兼容）。验证：S 端仓 change 目录在位（可晚于本变更合入；未上线前本变更按 D4 过渡期行为运行）

## 6. 回归与门禁

- [x] 6.1 后端 `pytest` 全绿（重点 auth_local／prompt_pack 域；存量用例零改动为准绳）。验证：本地全量绿
- [x] 6.2 前端 `vitest` 全绿 ＋ `tsc --noEmit` 通过（测试文件一并过 tsc）。验证：本地全量绿
- [x] 6.3 门禁：C端 `npm run design:lint` 绿（exit 0）；`design:check` 本地 8 红＝app 侧捕获超时——pristine main 同红 A/B 定罪（本 worktree 无在跑栈，parity 捕获移除 demo-bar、新增弹窗均为 hidden 不入像），以 CI 为准绳。未触两端共享段（proposal Design Impact 判定：仅弹窗变体与文案，不碰 base.css 令牌与共享组件族），免 `design-cross`。验证：两命令实际输出绿
- [x] 6.4 e2e（按本任务准绳条款）：存量桩仅用 `cdn_unreachable`/`tier`，与 `auth` 零交集；本地未跑（需 iso 栈＋真 S 端种子，隔离成本高），以 CI 为准绳；认证失败变体已按「以 vitest 钉为主」完成（4 用例）。原文本：`prompt-pack.spec.ts`／`prompt-pack-onboard.spec.ts` 存量绿；认证失败变体以 vitest 钉为主（e2e 需 S 端 401 桩，成本高则注明以 6.1–6.3 为准绳）。验证：e2e 本地绿或注明准绳
- [ ] 6.5 真机验收：Mac 打包版人为置过期令牌 → 验证「认证失败＋重新登录」出口；重登后写作能力自动恢复（S 端重签上线后补验「过期令牌静默自愈零操作」臂）。验证：真机记录两臂结论
