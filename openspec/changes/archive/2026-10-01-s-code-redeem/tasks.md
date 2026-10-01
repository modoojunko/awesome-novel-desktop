# Tasks: s-code-redeem

## 1. 双端影响判定（纯 S端，免原型）

- [x] 1.1 判定登记：本 change 仅触 S端（server/app + server/frontend/src/{api,views/dashboard}），不碰两端共享段（base.css 令牌/语义类、pill/notice/sk/panel/f-err 家族）与 C端 任何文件；无新增组件词汇/状态档位（notice 沿用 info/warn/err，按钮/弹层沿用既有 .btn/.AppModal 体系）——依据 proposal「Design Impact」段；S端 无原型基线，完成后在 change 目录附「我的套餐」页改动前后截图对照

## 2. 后端：兑换端点

- [x] 2.1 `dto.py`：删无引用死代码 `ActivateLicenseRequest`，新增 `RedeemCodeRequest(code: str)`；grep 全仓确认 `ActivateLicenseRequest` 零残留引用
- [x] 2.2 code_repo 三实现（base 抽象 + sql + pg_http）新增 `redeem_unused(code_id, user_id, grant_start, expires_at, activated_at) -> bool`：`WHERE code_id=? AND status='unused'` 条件更新（status→active、user_id、activated_at、grant_start、expires_at），实现套路对齐 `activate_pending`；单测覆盖两实现「首次 True＋行内容正确、二次 False＋归属/时间不被改写」（pytest -k redeem_unused 绿）
- [x] 2.3 应用服务 `application/payments/redeem_code.py::redeem_code`：输入归一（trim＋大写＋`AC-` 形态校验，不匹配/不存在→同一「无效的激活码」）、码行 must unused（否则「已被使用」）、顺延起点复用 `calc_grant_start`（active+frozen 家族）、时长取码行 duration_days、CAS 落库、trade event `codes:{code_id}:redeemed`（order_no=None，payload 带 tier/grant_start/expires_at/source=redeem）；返回 `{code_id, tier, grant_start, expires_at}`；单测：成功/重复兑/他人已兑/无效码/顺延衔接（有更远到期日时 grant_start=该日）/event 留痕（pytest -k redeem_code 绿）
- [x] 2.4 删除孤儿服务 `application/licensing/activate_code.py`（grep 端点/测试零引用后删）；全量 pytest 确认无隐性依赖（pytest server/tests 全绿）
- [x] 2.5 web 端点 `interfaces/web_api/payments.py` 新增 `POST /api/pay/codes/redeem`（`guard_identifiers(body=("code",))`＋`_current_identity` 4001＋DomainError 口径，错误码沿用 4004/4012 风格）；API 测试：未登录 4001、归一化（小写/带空格码可兑）、无效码统一文案（pytest -k codes_redeem 绿）
- [x] 2.6 限流护栏：`RateLimitMiddleware.SENSITIVE_PATHS` 增 `/api/pay/codes/redeem`（注释清单同步）；`tests/test_rate_limit_bypass.py` 对拍清单同步并跑绿（防漏测试通过）

## 3. 前端：我的套餐兑换入口

- [x] 3.1 `api/pay.ts` 新增 `apiPayRedeemCode(code)` 与响应类型（`{code_id, tier, grant_start, expires_at}`）；tsc --noEmit 零新错
- [x] 3.2 `LicensePage.vue`：页头汇总区加「兑换激活码」入口（动词按钮）→ AppModal（.show 两段式）输入码＋转译文案（兑换即按顺延规则开始计时；激活码不属订单、兑换后不可退款）→ 成功走既有刷新链（hero 必刷＋切「生效中」版）＋flash 提示；失败 msg 枚举映射（无效码/已被使用/其余兜底）＋联系客服可点击出路＋4001 走既有 401 口径。**实现更正：S端 前端无 vitest 基建（仅 node:test＋Playwright e2e），三场景落在 e2e/tests/license.spec.ts（mock 层新增 /api/pay/codes/redeem 处理器与 failRedeem），e2e license.spec 全绿**
- [x] 3.3 文案与词汇自查：无内部术语、语气词只用 info/ok/warn/err、按钮词全动词、无裸 hex/emoji 图形/未登记字号（design:lint 通过）

## 4. 回归

- [x] 4.1 S端 门禁：`server/frontend` `npm run design:lint` 全绿（无 design:check 义务——非 C端）；`vue-tsc --noEmit` 零错；`node scripts/design-cross.mjs` 不适用（未触共享段，判定依据=任务 1.1）
- [x] 4.2 后端全量：`pytest server/tests` 全绿（含 2.2–2.6 新增用例与限流对拍）；C端 无改动，`tsc --noEmit`/`design:check` 不适用
- [x] 4.3 隔离栈端到端自证（每会话独立环境）：后端 18901（tmp sqlite）＋vite 5175（VITE_PROXY_TARGET 指向）完成全链——管理端 /api/generate_code 发 2 张月付码→「我的套餐」UI 兑换（小写＋空白归一化）→toast＋档位头刷新（PRO·剩余 66 天=试用 6＋30＋30 顺延叠加）→重复兑换拒/无效码拒。截图 before/after-redeem.png 落 screenshots/。**冒烟实勘两裁定**：①码形态实为 AC-＋4 组（非 3 组），形态校验与全部样例已修；②兑换行按既有手工码口径不入明细列表（spec delta/proposal/design 已同步，mock＋e2e 镜像）。teardown 完成（端口清零、tmp 保留）
