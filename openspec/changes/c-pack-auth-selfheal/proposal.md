# Proposal — c-pack-auth-selfheal（写作能力换钥登录态死锁修复）

## Why

写作能力包的换钥链存在登录态死锁（2026-10-20 Mac 真机 v0.36 实测复现全链）：本地 JWT 过期后，静默自愈无条件沿用旧令牌（`browser_auth(silent=True)` 注释「保留本地有效令牌」但从不校验），pair/exchange 换新兜底被该分支遮蔽、其失败信号（code 1「请重新登录」）又被前端 `useAuthHeal` 忽略（无 `session_invalid` 标志不消费）——结果界面恒显「已登录」，而一切带鉴权的 S 端调用（当前唯一消费者＝写作能力换钥）持续 401，且 `call_server_api` 把 401 与「S 端不可达」同塌缩为 code -1，同步器只能落 `reason=exchange`，前端无文案映射，用户看到的是误导性的「网络或服务暂时不可用」。真机并实锤：用户在浏览器完成重新授权后，客户端仍沿用旧令牌，连成功重登都无法自愈。

## What Changes

- **C端 静默自愈校验令牌新鲜度**：沿用本地令牌前解析 JWT payload 校验 `exp`（无签名校验，仅本地判新旧；不可解析视同过期）；过期即走 pair/exchange 换新令牌并原子落盘，随后按既有钩子触发包同步——用户重新授权过即全自动自愈，零操作。
- **配对终局失败透出重登信号**：pair/exchange 明确失败（非不可达）且本地无有效令牌时，按既有清理全集清凭据并携带独立结构化失效标志（`pairing_broken`，与既有 `session_invalid` 区分）回登录页（持久化提示，作品不受影响）；前端 `useAuthHeal` 增对称分支消费，防循环。
- **401 语义分离**：`call_server_api` 将 HTTP 401 透传为 envelope `code=401`，不再与「不可达」（code -1）混同。
- **换钥同步不降档**：换钥收到 401 → 终态 `failed/reason=auth`，SHALL NOT 按档位降档重试（认证失败与档位无关，降档四连只会放大失败）。
- **弹窗失败态认证出口**：写作能力弹窗失败态新增「认证类失败」变体——文案为完整独立句（不拼「随时可以重试」后缀、不出现内部术语），主出口「重新登录」**直驱重授权流**：打开系统浏览器授权页＋弹窗转等待授权轮询（有上限、超时可手动复查），授权完成原地恢复进度流；评审定稿不回登录页——登录页静默自动登录会把失效令牌用户自动弹回作品页，授权面不可达。保留「复制诊断信息」。
- **S 端联动另行立项**（不在本仓）：pair/exchange 现只回授权时存档的旧令牌（`grant.token`），令牌 30 天过期后存量用户换到的仍是死令牌；S 端 change 应改为现签新 JWT（凭 challenge 验设备后重签＋回写 grant）。未落地前的过渡期，本变更保证：换得过期令牌时按认证失败诚实呈现，不误报网络。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend-auth-heal`：ADDED——静默自愈不得沿用过期令牌；配对失败重登信号的清理与前端消费。
- `prompt-pack-delivery`：MODIFIED——「提示词包获取与安装（C端）」换钥 401 语义（终态 auth、不降档）；「写作能力引导弹窗（首装/更新/手动）」失败态认证类出口与文案。

## Impact

- `client/backend/auth_local/service.py`：`browser_auth(silent=True)` 令牌新鲜度分支、`call_server_api` 401 透传。
- `client/backend/prompt_pack/sync.py`：换钥 401 → 终态 `auth`。
- `client/frontend/src/hooks/useAuthHeal.ts`、`client/frontend/src/components/novel/license/PromptPackModal.tsx`。
- 原型：`docs/design-c/prototypes/list.html`（写作能力弹窗 demo-bar 增认证失败变体）＋ `ADJUSTMENTS.md` 登记。
- S 端私有仓 `server/app/interfaces/client_api/pairing.py`（另行 change，本仓 tasks 仅挂协调项）。
- 兼容性：S 端未重签期间存量过期用户换钥仍得旧令牌 → 按认证失败引导重登（可接受的中态，不再误导）；S 端重签上线后静默自愈闭环，用户零操作。

## Design Impact

- **受影响端**：C端（本仓）。S端 仅联动立项，不改本仓任何文件。
- **受影响屏/弹层**：「写作能力」引导弹窗失败态（新增认证失败变体：完整独立文案＋主出口「重新登录」直驱授权页＋等待授权子态）；登录页消费既有 `auth_notice` 持久化提示（`pairing_broken` 清凭据路径，既有形态，无新组件）。
- **对象状态**：弹窗 `failed` 态新增按 reason 分派的出口变体（与既有 `tier_denied → 去升级` 同构）；文案 err 语气沿用既有 `pm-warn`，不新增第四种胶囊形态、不新增语气词。
- **两端共享段**：不触碰 base.css 令牌与 pill/notice/sk/panel 家族。
- **原型先行**：需要——`list.html` 弹窗 demo-bar「写作能力弹窗 · 5 态」增「认证失败」变体，`ADJUSTMENTS.md` 尾插登记条目。
- **设计工件**：实现侧自查（变体级改动，无新布局无新组件）。
