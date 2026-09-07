# S端 退款实体升格 方案稿（停审批口 · 前置 Change A）

> **【已搁置 2026-09-07】** 本册为《套餐升级按秒补差》（同批搁置，见 docs/prd/s-pay-upgrade-proration-design.md）的前置地基；上游搁置后本册失去触发场景一并封存。两轮评审（后端架构师打回项+前端工程师复核）的修正已全部折入，将来重启退款实体化时直接复用。

日期：2026-09-07
状态：**待用户审核，未开工**
定位：**Change B《套餐升级按秒补差》（docs/prd/s-pay-upgrade-proration-design.md）的前置地基**。本册先行、行为等价迁移，B 册的两腿退款落在本册地基上（1 个 refund_no 实体 + 2 条腿）。

触发：09-07 用户拍板——退款升格为独立域实体（refund_no 主体 + N 资金腿），推翻 08-29「不设独立退款单」的域模型层裁定（升级场景首次出现 1 退款:N 订单，旧前提破了）。IA 评审裁定 UI 呈现不变、不加菜单。

---

## 1. 目标与非目标

**目标**：退款成为有主体性的域对象——流程、状态、历史全挂 refund_no 实体；下挂 N 条资金腿（腿=订单+金额+微信退款单号+腿状态）；存量单腿退款 = N=1 的特例，**行为逐字节等价迁移**。

**非目标**：
- 前端零新页面零新菜单（IA 评审定版：退款实体有身份无视图，refund_no 作凭据位透过订单露出）
- 折算公式（refund.py 纯函数）、微信交互口径（out_refund_no=订单号）、冷静期节奏全部不动
- 不做多笔合并退款等新功能（实体模型为它留了位，本期不做）

## 2. 表设计（真 DDL，生产 PG 手工维护走 MCP applyMigration + pg_gate 登记）

```
refunds（退款实体 = 流程主体）
  refund_no   text  PK        # "R" + YYYYMMDD(UTC) + '-' + 12hex，String(32)（对齐 gen_order_no 生成法）
  user_id     bigint
  status      text            # cooldown → processing → succeeded / canceled / abnormal
                              # （沿用现有 orders.refund_status 枚举值，语义同源）
  initiated_by_order_no text  # 属主单：用户从哪单发起（升级退款=升级单号）
  reason      text            # 用户原因/运营标注
  operator    text            # 操作者审计（user:{id}/admin，承接 orders.refund_operator）
  total_fen   int             # 合计应退 = Σlegs（界面"一笔退款"口径的唯一数据源）
  requested_at / accepted_at / cooldown_ends_at / refunded_at / updated_at

refund_legs（资金腿 = 执行明细）
  id          bigint PK
  refund_no   text            # → refunds.refund_no
  order_no    text            # 腿挂在哪笔订单（out_refund_no=order_no 不变）
  amount_fen  int             # 本腿金额
  status      text            # pending → submitted → succeeded / failed，终态另有 canceled
                              # （canceled=实体取消时未提交腿同批置入，不占额度——取消后可再申请）
  wx_refund_id text           # 微信退款单号
  not_enough_count int default 0  # 微信退款余额不足重试计数（承接 orders.refund_not_enough 口径）
  created_at / refunded_at

索引：refund_legs(refund_no) / refund_legs(order_no)
      refunds(status, cooldown_ends_at) partial WHERE status='cooldown'（R1 到点提交承重）
      refunds(user_id, status)
      **部分唯一索引 uq_refund_legs_live(order_no) WHERE status IN ('pending','submitted')**
      ——并发串行化点（拍板：取消后可再申请，有效腿唯一；撞线=既有"退款已在进行中"错误）
```

- 两表而非单表 JSON 腿（待拍板项 1，建议两表）：按订单查腿是高频路径（订单详情/对账），JSON 包含查询在 pg_http 下别扭
- pg_gate：EXPECTED_DEFAULTS/REQUIRED 增补两表登记；启动自检随迁移生效

## 3. 状态机与读写重锚

- **状态机搬家**：refund_flow.py 四函数（request_refund / cancel_refund / cooldown_submit / complete_refund）读写锚从 orders.refund_* 列改为 refunds/legs；orders 的 refund_* 列族**降为派生缓存**（列表 tab 筛选 + 行展示消费），流程每步同批更新（pg_http 无事务 → 先实体后缓存 + trade_events 兜底自愈；前端流程真相只读实体——IA 评审 P1-5）
- **R1 定时提交**（/api/cron/scan-orders，冷静期到点提交；R3=/api/cron/scan-refunds 为提交后跟进，勿混）：扫描条件从 orders 改为 `refunds WHERE status='cooldown' AND cooldown_ends_at<=now`；提交时对该实体**全部 pending 腿**逐笔调微信，微信提交 reason 读实体 reason 列（N=1 即现有行为）
- **扫描 F 自愈**：半截态对账锚实体（实体 submitted 但腿 failed → 腿级重试；缓存与实体不一致 → 缓存重建）
- **拒退口径**：REASON_* 全集不变；「每笔订单仅办理一次退款」的判断改为**每单至多一条有效腿**
- **trade_events**：refund_no 列已存在，事件主键从 order_no 扩为可挂 refund_no

### 3.1 断点续传与幂等（崩溃窗口全表）

四层保障：**①意图先行**（外部调用前状态先落库，processing=有未完成工作的标记）；**②微信幂等**（out_refund_no=订单号，重提交同号返回原受理、不重复退钱——钱侧的续传键）；**③腿级粒度重试**（只重跑 failed/pending 的腿）；**④多道网**（R1 到点提交 + R3 跟进 + 扫描 F 巡检半截态 + T4 日终对账兜底）。

| 崩溃点 | 崩溃瞬间落库状态 | 恢复动作 | 资金安全 |
|---|---|---|---|
| 实体建行后、缓存更新前 | cooldown 已落、缓存旧 | 缓存可重建（投影） | 未碰微信 |
| 标记 processing 后、微信调用前 | processing + 腿 pending | 扫描 F 重驱动提交 | 未调微信 |
| 微信已受理、腿写库前 | 本地腿仍 pending | 重提交同 out_refund_no → 微信幂等返回原受理 | 不重复退款 |
| 腿A 成功、腿B 提交前 | 腿A succeeded、腿B pending | 只重试腿B | 各腿独立 |
| 全腿成功、实体未收口 | 腿全 succeeded、实体 processing | 收口扫描补 succeeded + 缓存同步 | 金额正确 |

取消竞态：冷静期取消与 R1 到点提交并发 → 实体状态 CAS（cooldown→canceled vs cooldown→processing），输的一方自动停。

## 4. 迁移与回填（cohort≈0，一次回填成本 ≤1 天）

1. DDL（applyMigration）→ pg_gate 对拍
2. 回填**物化全部非 none 退款态**：succeeded 单→实体(succeeded)+succeeded 腿；**cooldown 单→实体 cooldown+腿 pending；processing 单→实体 processing+腿经微信查单回核落 submitted/succeeded**（部署瞬间的在途单不回填会三道网失明卡死——评审 P0）；已 canceled 历史不回填（无后续流程依赖，显式声明）；部署清单另加"在途退款=0"预检双保险
3. 对拍验收：回填后逐单核对 orders 投影列 = 腿合计、状态语义一致
4. 回滚预案：功能等价替换无开关——部署前全量 pytest 门禁（现行铁律）+ 部署后退款端点探针；数据层双写期间实体表可弃（缓存仍是旧全量），回滚=回镜像

## 5. 行为等价验收（A 册的红线）

- 全量 pytest + e2e 绿，现有退款用例零修改语义通过
- 演练三条链：申请→冷静期→取消；申请→冷静期→提交→到账；提交遇 not_enough 重试
- **N=1 UI 逐字节等价**：订单详情时间线/退款申请页截图对拍（IA 评审红线——换的只是读取锚）
- T4 对账跑一轮，mismatch=0
- 派生缓存一致性：实体状态与 orders.refund_* 同批落库（验收含"列表退款 tab 与详情状态不打架"用例）

## 6. 改动面

| 层 | 文件 | 改动 |
|---|---|---|
| infra | pg_schema.py + alembic + applyMigration | +refunds / +refund_legs 两表，pg_gate 登记 |
| application | refund_flow.py | 四函数读写重锚 + 腿执行器（单腿=循环特例）+ 缓存同批写 |
| application | scan_orders.py | R3 扫描与扫描 F 重锚实体 |
| interface | payments.py | 退款申请/取消/进度端点走实体；响应字段形状**保持不变**（后端组装投影，前端无感） |
| domain | refund.py | 纯函数不动；拒退判断入参补"该单有效腿数" |
| infra | reconcile.py | T4 退款行匹配改经 legs（out_refund_no=order_no 不变） |
| 前端 | 全部 | **零改动**（本册红线） |
| specs | s-payments | 退款域模型重述（实体+腿），等价 scenario 全量保留 |

## 7. 待拍板项（未反对按默认建议执行）

1. refunds + refund_legs 两表 vs 单表 JSON 腿（建议：两表，按单查腿高频）
2. 存量回填脚本 vs 惰性兼容（建议：回填，cohort≈0 一次清干净，不给实体模型留历史歧义）
3. orders.refund_* 派生缓存保留 vs 删除（建议：保留——列表筛选/行展示零改动，域真相在实体）
4. 生成法：refund_no 用 "R" 前缀 + 日期 + 12hex（建议：是，与 order_no 同族可读）

## 8. 评审折入与拍板记录（2026-09-07，前后端工程师评审后）

**用户拍板三项**：
1. **取消后可再申请**——"一笔订单同时只能有一条有效腿"；腿增 canceled 终态（取消时未提交腿同批置入、不占额度）；并发串行化点=部分唯一索引 uq_refund_legs_live(order_no) WHERE 有效态；法条「每笔订单仅办理一次退款」释义为"成功办理，取消不算"
2. **冷静期缩水存量缺陷随本变更修复**（行为变化显式宣告）——现网 pg_http 分支到点扫描漏 `cooldown_ends_at<=now` 谓词致实际 1~2 分钟即提交，重锚后回归规定满 5 分钟；补 pg_http 谓词回归用例
3. **pay-ops 五个运维动作全部重锚新台账**——full_refund/offline_settled 走回填同款补建函数，abandon_unfreeze 走实体 CAS→canceled，retry_refund/scan_not_enough 改腿上 not_enough_count；禁再直写 orders 退款列

**技术修正（按评审建议执行，无需拍板）**：驱动器口径修正为 **R1（/api/cron/scan-orders 到点提交）+ R3（/api/cron/scan-refunds 跟进）**，探活双端点；腿 submitted=微信受理确认后落库，意图先行由实体 processing 承担（消"卡死 submitted"窗口）；派生投影列清单**含 orders.status 主状态列**（前端 tab/pill/分支全消费它）；回填物化全部在途态+部署预检；refunds 加 operator 审计列；幂等出处改引 APIv3；响应**零新增键**（refund_no 凭据位露出归 B 册）；对拍 7 端点穷举+键集合 diff 空集；验收法改"基线截图+DOM diff+动态时刻掩码"（e2e mock 不动、不作等价证据）；演练须 DB_BACKEND=pg_http 口径；"列表与详情不打架"改收敛时限口径（≤1 扫描周期、禁资金误导展示）；preview 与 request 同锚实体；dev_inject/notify 回调/deletion_service（零改动备案）/invoices 类型防呆/backend-detail-design 同步入任务清单。
