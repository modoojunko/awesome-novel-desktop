# Proposal: s-code-redeem

## Why

运营侧已能用管理端 `/api/generate_code` 按档位（pro/max/…）手工生成激活码（卡密渠道、活动赠送、线下售卖），但用户拿到码后**没有任何兑换入口**：`POST /api/pay/codes/activate` 只认订单号，licensing 域的按码激活应用服务是孤儿（无端点调用）。第一波宣传在即，需要「发码→用户自助兑换开通」这条闭环跑通，PRO 档权限才能用激活码方式发放。

## What Changes

- **S端 新增激活码兑换端点** `POST /api/pay/codes/redeem`（登录态，body `{code}`）：校验码存在且状态为 unused → 绑定当前用户 → 按码行自带 tier/duration_days 起算（起点=既有顺延口径：现有 active/frozen 行最远到期日与今天取大）→ 写 grant_start/expires_at → 记 trade event（`codes.redeemed`）。兑换与被扫码并发以 CAS（status=unused 条件更新）保证只成功一次。
- **安全护栏**：端点加入 `RateLimitMiddleware.SENSITIVE_PATHS`（30/min/IP，防爆破猜码，`tests/test_rate_limit_bypass.py` 对拍同步）；`guard_identifiers(body=("code",))`；错误语义沿用既有域口径（无效的激活码 / 已被使用），未登录 4001。
- **S端「我的套餐」页新增兑换入口**：页头区「兑换激活码」→ 确认弹层如实转译后果（兑换即按顺延规则开始计时；激活码不属订单、不可退款）→ 成功后档位头汇总即时刷新（兑换行按既有手工码口径仅计入汇总、不入明细列表）；失败按错误语义给提示＋联系客服可点击出路。
- **权益生效零改造**：兑换产出的 active 行（user_id/tier/expires_at）被 check-auth 既有聚合链（`find_active_by_username`→`License.merge`→tier→features）自动纳入，C端 无任何改动。
- 明确不动：订单激活两段式（只认 order_no）语义不变；落地页「激活指南」文案不在本轮；管理端发码逻辑不变（tier/duration 仍按 TIER_POLICY 写死在码行）。

## Capabilities

### New Capabilities

（无——兑换是既有 codes 域对象上的新动作，落在既有支付/账户能力内）

### Modified Capabilities

- `s-payments`: ADDED「激活码兑换」Requirement——unused 码兑换端点契约（URI/请求/响应/错误语义）、CAS 防双兑、顺延起算、tier/duration 取自码行、trade event 留痕、限流护栏。
- `s-pay-account-views`: ADDED「激活码兑换入口」Requirement——我的套餐页兑换入口、确认弹层转译、成功刷新、错误出路。

## Impact

- **代码（S端 only）**：
  - `server/app/interfaces/web_api/payments.py`：新增 `/codes/redeem` 端点（复用 `_current_identity`/DomainError 口径）。
  - `server/app/application/payments/redeem_code.py`：新应用服务（或并入 activate_code 模块，见 design）。
  - `server/app/infrastructure/repositories/{base,sql,pg_http}/code_repo*`：新增 CAS 兑换方法（unused→active 条件更新，写 user_id/activated_at/grant_start/expires_at）。
  - `server/app/interfaces/dto.py`：`RedeemCodeRequest(code)`（`ActivateLicenseRequest(code)` 现为无引用死代码，顺带清理）。
  - `server/app/interfaces/middleware.py`：SENSITIVE_PATHS 增补。
  - `server/frontend/src/api/pay.ts` + `server/frontend/src/views/dashboard/LicensePage.vue`：兑换 API 与入口 UI。
- **测试**：pytest（兑换成功/重复兑换/他人已兑/无效码/顺延口径/trade event/限流对拍/4001）；vitest（LicensePage 兑换入口三态）；S端 e2e 视既有覆盖形态补一条 happy path。
- **数据**：零 DDL——codes 表既有列（tier/duration_days/status/user_id/grant_start/expires_at/source）全覆盖，兑换行 source 仍为 admin。
- **C端**：零改动（权益经 check-auth 快照自然生效）。
- **关联**：tier-plan-four-tiers（在途提案）未来落地四档时，兑换端点按码行 tier 自动兼容，无耦合。

## Design Impact

- **受影响端**：S端 only（C端 零改动）。
- **受影响屏/弹层**：「我的套餐」页（dashboard/LicensePage.vue）页头区新增兑换入口卡＋兑换确认弹层（复用 AppModal 两段式 .show 体系）。
- **对象状态**：无新增状态语言——复用既有 notice（info/warn/err）与 btn 词汇；兑换行在明细列表按既有「生效中」态渲染。
- **共享段**：不触碰两端共享的令牌/基础类（L1/L2），无 design-system 改动，无 design-cross 义务。
- **原型先行**：免（纯 S端 改动），按流程在 change 目录附截图对照。
- **设计工件产出**：实现侧自查。
