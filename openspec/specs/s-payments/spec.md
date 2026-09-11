# s-payments Specification

## Purpose
微信扫码支付地基（s-pay-foundation）：订单全生命周期状态机、冻结快照、到货-激活两段式、五分钟冷静期退款、补偿式一致性、日对账留痕、购买三态开关、前后端联合契约（附录 Z）与发票暂缓守卫。

## Requirements

### Requirement: 订单全生命周期状态机
订单（根对象）SHALL 以状态机管理生命周期：pending→paid→fulfilled 为主干；closed（可复活 closed→paid）/ exception（金额核对冻结）为分支；退款族 fulfilled→refund_pending（冷静期）→refund_processing→refunded。每次状态转移 SHALL 用单语句 CAS（WHERE 期望旧态）执行，非法转移在领域层拒绝。

#### Scenario: 同一订单并发回调只发货一次
- WHEN 微信回调与定时查单同时确认同一笔支付
- THEN 仅先完成 CAS pending→paid 的一方执行发货，另一方读到已 paid 走幂等分支
- AND codes 台账行恰好插入一行（order_no 部分唯一索引兜底）

#### Scenario: 关单竞态不丢钱
- WHEN 关单请求在途时用户完成支付
- THEN 关单必须先查单确认未支付才许置 closed；已支付的订单允许 closed→paid 复活并发货

### Requirement: 冻结快照与金额一致性
订单 SHALL 在创建瞬间冻结套餐事实（sku_id 引用 + sku_snapshot JSONB + amount_fen），后续 SKU 配置变更不影响已创建订单的解释、发货与退款折算。全链路金额 SHALL 使用 int 分；支付回调金额与订单金额不一致时订单 SHALL 进入 exception 终态并告警，绝不发货。

#### Scenario: 改价不影响已下单订单
- WHEN 用户以 ¥292 下单后运营将包年改价为 ¥350
- THEN 该订单的退款折算仍按快照 ¥292 计算，收银台轮询与详情页金额一致

#### Scenario: 金额不符冻结不发货
- WHEN 回调金额与订单冻结金额不一致
- THEN 订单进入 exception 终态并触发告警，绝不发货，等待人工处置

### Requirement: 到货-激活两段式
支付确认后系统 SHALL 立即落权益台账行（codes，状态 pending_activation），用户 SHALL 在「我的套餐」点「激活」才开始计时（起点=当前最远到期日，顺延衔接）。未激活行不计时、不占设备额度、退款全额、永不过期。tier 归属 SHALL 按已激活行中等级最高者。台账行插入（支付发货与管理员发放两条路径）SHALL 显式写入 UTC 口径的 created_at，MUST NOT 依赖数据库列默认值求值时区（生产曾致上海本地时间裸值被按 UTC 读、比订单时间快 8h）；存量行的历史偏差不回填（无计算依赖，仅治理增量）。

#### Scenario: 囤套餐
- WHEN 用户购买包年后选择"先存着"
- THEN 该行保持 pending_activation（不计时/不占额度）；用户随时可激活进入排队

#### Scenario: 发货台账行与订单时间同口径
- WHEN 支付回调完成发货插入台账行
- THEN 该行 created_at 与订单 paid_at 为同一 UTC 口径（秒级差），后续按北京时间展示两者一致

### Requirement: 退款五分钟冷静期
用户确认退款时系统 SHALL 立即冻结对应权益并按确认时刻锁定折算金额（秒级公式、四舍五入到分、不足 1 分拒退、未激活/排队中全额退）。冻结 SHALL 落为权益台账行的冻结态：该单已激活可用行（active）SHALL 置为 frozen——不再计入 tier 归属、到期合并与「生效中」展示（可用性暂停）；行上起算信息（grant_start/expires_at 等）SHALL 原样保留，取消后精确还原，激活顺延的排队终点 MUST NOT 因冻结改变。随后进入 5 分钟冷静期：期间用户可取消（解冻恢复使用、终点不变、不补偿、refund_status=canceled 终态）；到点由定时任务自动提交微信原路退款；提交后不可自助撤销。退款成功 SHALL 按 **权益相位** 回收对应订单来源码（仅该单，其余不重算），相位判定 SHALL 以**该单退款确认时刻（refund_requested_at，即折算金额锁定时刻）为锚**，与金额锁定同锚、不随重放时刻漂移：

- **未激活**（unused/pending_activation）→ 置 revoked（既有行为）；
- **已激活·排队中**（active/frozen 且 grant_start 为空或 > 锚时刻）→ 置 revoked，并追加 `codes.revoked` 事件（event_key 以 `:queued` 后缀区分，payload SHALL 留存 grant_start/expires_at）；
- **已激活·已起算**（active/frozen 且 grant_start ≤ 锚时刻）→ 不收回，冻结行 SHALL 恢复 active（按秒折算保留剩余权益，恢复使用）。

折算公式与全额退/折算退款口径不变；冻结、解冻与收回动作 MUST 幂等可重入，且 MUST NOT 依赖修改表结构。

#### Scenario: 确认退款立即冻结
- **WHEN** 用户确认退款、订单 CAS 进入 refund_pending 成功
- **THEN** 该单已激活行置 frozen，授权聚合与我的套餐不再计入该行（不显示生效中）；grant_start/expires_at 不变，排队终点不变

#### Scenario: 冷静期取消
- **WHEN** 用户在倒计时内点「取消退款」且定时提交尚未执行
- **THEN** orders CAS refund_pending→fulfilled 先到者赢，该单 frozen 行解冻恢复 active（授权聚合恢复原档位与到期展示），权益解冻恢复使用，金额前科进 trade_events 留痕

#### Scenario: 冷静期到点与用户取消竞态
- **WHEN** 倒计时归零瞬间用户同时点取消
- **THEN** 先完成 CAS 者生效（取消赢则解冻恢复；提交赢则返回"已提交不可撤"4007）

#### Scenario: 排队中码随全额退款收回
- **WHEN** 某单的码已激活但 grant_start 在该单退款确认时刻之后（排队中，如排百年永久档之后，含确认退款时已被置 frozen 的行），该单退款成功
- **THEN** 该码 CAS 置 revoked 且追加 `codes:{code_id}:revoked:queued` 事件（payload 含 grant_start/expires_at）；退款金额为确认时刻锁定的全额（未起算口径），两判定同锚不因冷静期窗口翻转

#### Scenario: 已起算码退款后保留
- **WHEN** 某单的码 grant_start ≤ 该单退款确认时刻（已起算），该单按剩余时长折算退款成功
- **THEN** 该码不收回；若处于冻结态 SHALL 恢复 active，剩余权益继续有效

#### Scenario: 收回动作重放安全
- **WHEN** 退款成功路径因崩溃或重试被重放（三入口：R1 冷静期到点提交 cooldown_submit、R3 跟进、微信回调）
- **THEN** 已 revoked 的码再次执行收回返回 0 行且不报错、不重复追加事件（event_key 唯一键幂等）；重放前后相位判定同锚（refund_requested_at 为行上既有值）

#### Scenario: 取消退款不洗回已收回的码
- **WHEN** 某码已随历史退款被置 revoked，其后同单出现冷静期取消或任何重放
- **THEN** revoked 行不被恢复为 active（取消路径只做 orders CAS、解冻 frozen 行，从不触碰 revoked 行）

#### Scenario: 退款进行中码不动
- **WHEN** 某单处于 refund_pending / refund_processing（尚未 succeeded）
- **THEN** 其订单来源码不提前收回、不提前做相位判定（"不动"指收回与相位判定，不含冻结这一可用性暂停）；冻结不影响锚判定，到 succeeded 才按确认时刻锚一次判定

#### Scenario: 冻结/解冻半截态自愈
- **WHEN** 冻结或解冻写码行前后进程崩溃（订单已退款中但行仍 active；或订单已结束退款流程但行仍 frozen）
- **THEN** 定时扫描幂等收敛：退款中订单的 active 行补冻结；已取消回 fulfilled 订单的 frozen 行补解冻；已退款（refunded）订单的 frozen 行按锚相位判定处理；每次自愈 SHALL 追加 `codes.frozen` / `codes.unfrozen` 事件（键含时间戳，重放不重复）；重跑扫描 0 行新增
### Requirement: 补偿式一致性（无事务环境）
生产环境（PostgREST 无多表事务）下所有多步写 SHALL 遵循：单语句 CAS + 唯一约束幂等键 + 补偿扫描自愈。每个崩溃窗口 MUST 有恢复路径：支付半截（paid 未发货）由 T2 扫描补发货；退款半截（refund_status=succeeded 但 orders.status≠refunded）由扫描 D 重放退款成功路径补回收（未激活行同批收回）；orders 已 refunded 而订单来源码仍 active+排队中（以该单 refund_requested_at 为锚判定）的漏网由 R3 扫描 E 收敛：CAS 收回并追加 `:queued` 事件——既收敛存量漏网行，也兜底未来漏网。回调处理 MUST 全量可重入（CAS 输但已成功→继续剩余步骤）。

#### Scenario: 退款完成中途崩溃
- WHEN refund_status→succeeded 后、codes revoke 前进程崩溃
- THEN 扫描 D 发现该半截态并重放回收步骤（幂等），最终 orders→refunded 且全链一致

#### Scenario: 存量排队中漏网行自愈
- WHEN 历史退款成功单（orders 已 refunded）的订单来源码仍为 active 且 grant_start 为空或 > 该单 refund_requested_at（如 2126/2028 起算的存量 3 行）
- THEN R3 扫描发现并 CAS 收回、追加 `:queued` 事件；重跑扫描 0 行新增（幂等）

#### Scenario: 自愈不误伤已起算权益
- WHEN 扫描遇到退款成功单但其码 grant_start ≤ 该单 refund_requested_at（已起算）
- THEN 不收回、不产生事件，该行保持 active（按秒折算保留剩余权益的既定口径）

### Requirement: 日对账与资金留痕
系统 SHALL 每日拉取微信账单与内部账逐笔三键比对（商户单号/交易单号/金额），不平即 Server酱告警；所有状态变化 SHALL 追加 trade_events（append-only，数据库触发器拒绝 UPDATE/DELETE，留存≥10 年）。月度计税报表 SHALL 排除演练白名单用户。

#### Scenario: 漏回调由对账兜底
- WHEN 一笔支付成功但回调与补偿扫描均未触达
- THEN 日对账发现微信侧有此单而内部账为 pending，记入 mismatch_detail 并告警

### Requirement: 购买入口三态开关
购买入口 SHALL 支持 off（默认，入口隐藏）/ rehearsal（仅白名单用户可下单，计税与对账排除白名单）/ on 三态；生产 mock 演练期 SHALL 处于 rehearsal；dev 注入端点 SHALL 强制 Admin 鉴权且仅在 mock 模式注册。

#### Scenario: 演练不污染税表
- WHEN rehearsal 态下白名单用户产生 mock 订单
- THEN 月度计税报表与日对账排除该用户的数据

### Requirement: 前后端联合契约
API 端点/DTO/错误码 SHALL 以 backend-detail-design.md 附录 Z 为唯一版本：错误码=数字码+前端映射表（HTTP 200+data.code）；对外 URL/API 只用业务标识（order_no/sku_key），内部 FK 用代理 id；微信单号=完整值下发+前端脱敏渲染。

#### Scenario: 错误码映射唯一
- WHEN 后端返回 data.code=4007
- THEN 前端按附录 Z.1 映射表唯一解析为 REFUND_ALREADY_SUBMITTED 并渲染对应提示

### Requirement: 发票功能暂缓守卫
发票功能 SHALL 整体暂缓：invoices 表随建但 API/前端全部不实现；相关代码以注释占位留恢复点，启用时另行立项。

#### Scenario: 暂缓期无发票入口
- WHEN 用户浏览任一订单详情
- THEN 不出现获取发票按钮与发票区块，后端发票端点返回 404

### Requirement: 订单列表按状态筛选与真分页
我的订单列表接口 `GET /api/pay/orders` SHALL 支持服务端筛选与真分页：`status` 参数接受逗号分隔的订单状态白名单（pending / paid / fulfilled / refund_pending / refund_processing / refunded / closed / exception），筛选与计数同口径；`page` / `page_size` 分页返回，响应 SHALL 含 `total`（符合筛选条件的全量笔数）供前端「已显示 X 笔 · 共 Y 笔」计数。不带 `status` 时返回全部状态。筛选仅作用于现有列，MUST NOT 引入 schema 变更。

#### Scenario: 按状态筛选返回对应订单
- WHEN 已登录用户请求 `GET /api/pay/orders?status=paid,fulfilled&page=1&page_size=20`
- THEN 只返回状态为 paid 或 fulfilled 的订单，按创建时间倒序，`total` 为该筛选条件的全量笔数

#### Scenario: 未知状态值不致命
- WHEN `status` 含未知值（如 `status=paid,foo`）
- THEN 未知值被忽略，按剩余合法状态筛选；全部值均未知时返回空列表而非报错

#### Scenario: 分页追加口径
- WHEN 同一筛选条件下请求 `page=2`
- THEN 返回按创建时间倒序的第 21~40 条，`total` 不变；前端据此判断「加载更多」是否还有下一页

#### Scenario: 未登录与无用户照旧拒绝
- WHEN 未登录或用户不存在
- THEN 返回 `code=4001`，与现有口径一致

### Requirement: License 总览接口命名对齐域对象

用户权益聚合总览接口的 URI 与代码符号 SHALL 取自实存域对象名（`license`），MUST NOT 引入域外词（如 membership）。接口返回内容为当前登录用户的 License 聚合视图（有效档位、最远到期、剩余时长、待激活数、订单来源套餐行计数）；明细列表由独立分页端点承载（见「License 明细与快照字段层对齐域对象 code」）。

#### Scenario: 我的套餐总览走 license 路径

- **WHEN** 已登录用户请求 `GET /api/pay/license`
- **THEN** 返回 `code=0` 与 License 聚合视图（tier / remaining_sec / remaining_desc / max_expires_at / pending_count / code_count）
- **AND** 未登录请求返回 `code=4001`

#### Scenario: 旧路径过渡别名

- **WHEN** 客户端仍请求 `GET /api/pay/membership`
- **THEN** 返回与 `GET /api/pay/license` 完全相同的聚合视图
- **AND** 该别名已随 s-pay-license-naming 收尾移除（现为终态行为：旧路径 404）

#### Scenario: 旧页面链接重定向

- **WHEN** 已登录用户访问前端旧地址 `/dashboard/membership`
- **THEN** 重定向到 `/dashboard/license` 并渲染同一 License 总览页
- **AND** 历史激活码地址 `/dashboard/license` 直接命中该页（原重定向规则由真身页取代），导航与各跳转入口全部指向新地址

#### Scenario: 前端符号单一命名

- **WHEN** 检查 S端 前端源码（router / api 客户端 / 视图组件）
- **THEN** 该资源的类型、请求函数、页面组件、路由名一律命名为 license 语义（LicenseView / apiPayLicense / LicensePage / route name `license`），仓库内存量 membership 符号仅剩历史文档表述

### Requirement: 激活动作接口命名对齐域对象 code

订单来源套餐的激活动作接口 URI 与代码符号 SHALL 取自实存域对象名（`code`，ActivationCode/codes 表），MUST NOT 使用域外借词（grant/entitlement）。激活语义（订单号换权益开始计时）、错误码与响应体字段口径保持不变。

#### Scenario: 激活走 codes 路径

- **WHEN** 已登录用户请求 `POST /api/pay/codes/activate` `{order_no}`
- **THEN** 行为与原 grants/activate 完全一致：到货态订单的台账行转为 active、返回 `{code_id, grant_start, expires_at, tier}`，非到货/不可激活错误码不变

#### Scenario: 旧路径过渡别名

- **WHEN** 客户端仍请求 `POST /api/pay/grants/activate`
- **THEN** 返回与 `POST /api/pay/codes/activate` 完全一致的结果
- **AND** 该别名为过渡兼容，前端线上包零引用后 MUST 移除

#### Scenario: 应用层符号单一命名

- **WHEN** 检查后端应用服务与接口层符号
- **THEN** 激活用例统一命名 activate_code（模块/函数/handler），仓库内存量 grant/entitlement 借词仅剩过渡别名一处

### Requirement: License 明细与快照字段层对齐域对象 code

套餐明细分页端点、总览行计数字段、订单详情权益快照 SHALL 以实存域对象名（`code`）命名：`GET /api/pay/license/codes`、总览字段 `code_count`、订单详情快照 `fulfillment`（到货——订单状态机 fulfilled 的名词化，零新词；本单到货产出的码行激活状态投影，引用非订单属性）。旧 URI/旧字段以过渡别名与双发兼容，前端线上包零引用后 MUST 移除。`grant_start` 为 codes 表既成列名连同响应字段裁定保留（"起算日"既成名，不入本轮）。

#### Scenario: 明细分页走 codes 路径

- **WHEN** 已登录用户请求 `GET /api/pay/license/codes?page=1&status=pending_activation`
- **THEN** 行为与原 license/grants 完全一致：items 行含 code_id/order_no/tier/duration_days/status/activated_at/expires_at/grant_start，total 为筛选全量计数，未知 status 白名单外值忽略
- **AND** 未登录请求返回 `code=4001`

#### Scenario: 总览计数与订单快照双发过渡

- **WHEN** 已登录用户请求 `GET /api/pay/license` 与 `GET /api/pay/orders/{order_no}`
- **THEN** 总览同时返回 `code_count` 与 `grant_count`（同值），订单详情同时返回 `fulfillment` 与 `grant`（同内容）
- **AND** 双发为过渡兼容，前端线上包零引用旧字段后 MUST 移除

#### Scenario: 旧分页路径过渡别名

- **WHEN** 客户端仍请求 `GET /api/pay/license/grants`
- **THEN** 返回与 `GET /api/pay/license/codes` 完全一致的结果
- **AND** 别名为过渡兼容，前端线上包零引用后 MUST 移除

#### Scenario: 字段层符号单一命名

- **WHEN** 检查前后端源码
- **THEN** 明细行类型/仓储方法/分页函数一律命名 code 语义（LicenseCode / LicenseCodePage / apiPayLicenseCodes / find_order_codes_page / list_license_codes），grant 借词仅剩 grant_start 既成字段与过渡别名/双发字段

### Requirement: 商品目录数据驱动三档矩阵

GET /api/pay/skus（公开商品目录）必须返回足以渲染「档位 × 时长」矩阵的全量配置，档位、时长、价格、折扣、权益卖点、上下架状态全部来自数据库配置，前端零硬编码；运营改库即生效，改套餐不发版。

#### Scenario: 档位卖点随配置下发

- **WHEN** tiers 表某档 selling_points 配置为 JSON 数组（如 `["AI 生成正文（流式）","设定与章纲融入 AI"]`）
- **THEN** 该档 tiers[] 返回 `selling_points` 为解析后的字符串数组（非原始 JSON 串）；未配置时返回空数组

#### Scenario: planned 档返回但不可购

- **WHEN** 某档 status='planned'（如 MAX 未上架）且其 SKU 均 on_sale=false 或不存在
- **THEN** 该档仍出现在 tiers[] 且 `is_planned: true`、`is_live: false`；其 SKU 不出现在 skus[]（pg_http 与 sqlite 双分支过滤口径一致：on_sale 且所属档 status='live'）；live 档 is_planned 恒为 false

#### Scenario: retired 档不返回

- **WHEN** 某档 status='retired'
- **THEN** 该档不出现在 tiers[]，其 SKU 亦不出现在 skus[]

#### Scenario: 档位与规格级字段齐备

- **WHEN** 目录正常返回
- **THEN** tiers[] 每行含 `key/label/is_live/is_planned/selling_points`；skus[] 字段与既有契约一致（只增不删，时长名称由 period 映射在调用方侧单源）；既有字段语义与取值不变

#### Scenario: 折扣徽标单源

- **WHEN** 某 SKU discount_permille=900
- **THEN** 该 SKU `discount_display` 为「9折」；时长 tab 徽标、卡面折扣角标均以该字段为唯一文案来源，前端不自行计算折扣文案

#### Scenario: 契约只增不删

- **WHEN** 旧客户端按旧字段消费目录
- **THEN** 既有字段（purchase_enabled/agreement_version/tiers[].key/label/is_live/skus[].* /popular_sku）全部保持原语义返回，无删除、无改名
