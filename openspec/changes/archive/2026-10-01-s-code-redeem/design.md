# Design: s-code-redeem

## Context

管理端发码（`POST /api/generate_code`，码行写入 tier/duration_days/status=unused/source=admin）与订单激活链路（`application/payments/activate_code.py`，只认 order_no）都已在线，中间缺「凭码兑换」一跳。licensing 域现存一个按码激活应用服务（`application/licensing/activate_code.py`），但**无任何端点/测试引用**（孤儿），且口径偏旧：username 字符串、不写 grant_start、无条件 UPDATE（双兑竞态会改写归属）、不记 trade event。权益聚合链（check-auth → `find_active_by_username` → `License.merge` → TierRepo/ENTITLEMENT_DEFAULTS）对 active 行自动生效，兑换无需触碰。

## Goals / Non-Goals

- Goals：unused 码 → 登录用户一键开通对应档位；防爆破、防双兑；与订单激活共用顺延口径与台账展示。
- Non-Goals：不改订单两段式；不改管理端发码；不做码批次/核销报表；不做 C端 兑换入口；landing「激活指南」文案不动。

## Decisions

1. **端点与命名**：`POST /api/pay/codes/redeem`（登录态），应用服务 `application/payments/redeem_code.py::redeem_code`。动词 redeem 与订单激活 activate 语义分离（activate=到货两段式第二段；redeem=无订单凭码开通）；URI 沿用实存域对象 `codes`（对齐 s-payments 命名 Requirement，零借词）。
2. **新服务、不复活孤儿**：兑换逻辑写进 payments 侧新模块，与订单激活同口径（user_id int 直传、grant_start 起算、trade event）；`application/licensing/activate_code.py` 孤儿**删除**（无引用，留着即双源漂移陷阱）。
3. **CAS 防双兑**：code_repo 新增 `redeem_unused(code_id, user_id, grant_start, expires_at, activated_at) -> bool`——`UPDATE codes SET ... WHERE code_id=? AND status='unused'`，返回 False 即「已被使用/已兑」。不复用 `activate`（无状态条件，竞态下双写互覆）也不复用 `activate_pending`（条件是 pending_activation，订单码专用）。sqlite（SQLAlchemy update）/pg_http（PostgREST 条件 patch 计数）双实现，与 `activate_pending` 同套路。
4. **起算与时长**：起点复用 `payments/activate_code.calc_grant_start`（active+frozen 全家族取最远到期日，与 today 取大）；时长用**码行自带 duration_days**（发码时已按 TIER_POLICY 写死），兑换侧不再查 tier_policy——码行即合同，四档改造（tier-plan-four-tiers）未来改 TIER_POLICY 不影响已发码。
5. **trade event**：`event_key=f"codes:{code_id}:redeemed"`（唯一键天然幂等），`event_type="codes.redeemed"`，`order_no=None`（trade_events.order_no 可空，已核）、payload 带 tier/grant_start/expires_at/source="redeem"。
6. **护栏**：`guard_identifiers(body=("code",))`；输入归一（trim＋大写）后不匹配 `AC-` 形态直接按「无效的激活码」返回（与不存在同错误，不泄露形态）；`RateLimitMiddleware.SENSITIVE_PATHS` 增 `/api/pay/codes/redeem`（凭据校验类同桶 30/min/IP；`tests/test_rate_limit_bypass.py` 对拍清单同步，防漏）。未登录沿用 `_current_identity` → 4001。
7. **DTO**：`dto.py` 的 `ActivateLicenseRequest(code)` 是无引用死代码，删除；新增 `RedeemCodeRequest(code: str)`。
8. **UI 落位**：LicensePage 页头汇总区加「兑换激活码」入口（链接按钮词=动词「兑换」）→ AppModal（复用 .show 两段式体系）内输入码＋如实转译（顺延起算/不可退款）→ `apiPayRedeemCode`（pay.ts）→ 成功 toast＋档位头汇总刷新；失败 msg 枚举映射（invalid/used/4001），notice 语气只用 info/warn/err，出路=联系客服链接。**兑换行不入明细列表**（隔离栈冒烟实勘裁定：s-pay-account-views 既有口径「手工码仅计入档位头汇总」不破坏，成功反馈=toast＋汇总变化；mock 与 e2e 已镜像该口径）。

## Risks / Trade-offs

- [license-redirect「激活码 UI 全部移除」旧钉与新入口冲突] → 已裁定：钉子本意=8.3 拆除的「激活新码」裸输入直兑形态不复活；s-code-redeem 的确认弹层制兑换为新官方入口。e2e 改钉「激活新码」按钮 count=0＋「兑换激活码」入口可见，并先等页面渲染再断言（原写法「数到 0 即绿」存在空转变绿竞态，实勘探针证实）。
- [兑换端点被爆破猜码] → SENSITIVE_PATHS 限流＋码空间 36^16（AC-xxxx-xxxx-xxxx）＋失败不留锁定态。
- [pg_http 侧条件 patch 计数语义与 sqlite 不一致] → 单测两实现各自断言返回值与行状态，套路对齐 `activate_pending` 既有测试。
- [删除孤儿服务碰隐性依赖] → 已 grep 端点/测试零引用；删除后全量 pytest 兜底。
- [兑换行 source 仍标 admin 与订单行难区分] → 本轮不动 schema（source 列已有）；trade event source="redeem" 已可审计，报表需求出现再立项。

## Migration Plan

零 DDL、纯增量端点＋页面入口，随版发布即用；回滚=撤端点路由与页面入口（码行数据无迁移）。上线顺序：后端先行（端点+限流对拍），前端入口随后（同一 PR 内则无窗口期问题）。

## Open Questions

（无——错误文案口径、入口落位已按既有页型定死；若运营需要「码未兑换前作废时间」再立项，不阻塞本 change。）
