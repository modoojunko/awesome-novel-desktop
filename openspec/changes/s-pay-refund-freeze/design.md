## Context

- 领域层 `app/domain/licensing/license.py` 的 `License.merge` 已跳过 `frozen` 行（注释即设计词汇表：待激活/排队中/消耗中/退款冻结/已回收），但全代码库无任何写路径产出 frozen——接线缺失。
- 退款流程三段式（均 `app/application/payments/refund_flow.py`）：`request_refund`（订单 CAS fulfilled→refund_pending，进冷静期）→ `cooldown_submit`（R1 到点提交，refund_pending→refund_processing）→ `complete_refund`（succeeded＋收回）。`cancel_refund` 冷静期取消（refund_pending→fulfilled）。
- 生产为 PostgREST 无多表事务（补偿式一致性）：单语句 CAS＋唯一键幂等＋补偿扫描自愈；每个多步写 MUST 有崩溃恢复路径。
- pg_http `code_repo.revoke_queued_for_order` 因客户端限制拆两支无条件 CAS（grant_start is.null 一支＋gt.anchor 一支）取并集；TOCTOU 安全前提是 grant_start 不可变（冻结不触碰 grant_start，前提保持）。
- R1 定时已降为小时级（08–23 整点，09-04 成本治理），自愈收敛窗最长约 1 小时。
- S端 前端「我的套餐」明细行已渲染行的状态字段；S端 e2e 全 mock，发现不了后端缺冻结，契约/单测必须补位。

## Goals / Non-Goals

**Goals:**
- 确认退款即冻结：可用性、tier、生效展示立即排除该行；取消精确还原；到账按锚相位收回或恢复
- 两个新崩溃窗口（冻结半截/解冻半截）有幂等自愈
- spec 措辞对齐：冻结与「不提前收回」不再冲突

**Non-Goals:**
- 不改 orders 状态机、不动折算公式与金额锁定锚
- 不改排队/激活顺延计算（冻结行 MUST 继续计入排队终点，只有可用性判定排除）
- 不动 R1 小时级节奏（冻结自愈延迟≤1 小时可接受，等同今日现状）
- C端不改造（license API 自然生效）

## Decisions

- **D1 冻结载体=codes 行 status（含 status_detail）置 frozen**，非读路径派生。理由：领域词汇表与 merge 已预留、规格取消场景明写"解冻"（动作语义）、任何直读 codes 的消费方（admin 视图、设备额度等）自动一致。备选"读路径按订单退款态派生"虽零写入零崩溃窗，但多消费方一致性差且与既有领域设计相悖，否。
- **D2 冻结范围=该单 active 行**；unused/pending_activation/revoked 不动（前两者本就不可用/无额度）。status 与 status_detail 同步置 frozen，解冻一律还原 active；因冻结不触碰 grant_start/status_detail 排队语义，取消后展示与排队位精确还原（active↔frozen 对偶）。
- **D3 写序=先 orders CAS 后 codes 写**（冻结与解冻均同序，CAS 输则不触碰码行，与取消竞态天然安全）；由此产生两个半截态由扫描 F 幂等收敛：S-A=退款中（refund_pending/refund_processing）订单存在 active 行→补冻结；S-B=已取消回 fulfilled 且 refund_status=canceled 的订单存在 frozen 行→补解冻。refunded 订单的 frozen 行不走 S-B（防止把该收回的排队行洗活），归 complete_refund/R3 锚判定管。自愈动账本：每次收敛追加 `codes.frozen`/`codes.unfrozen` 事件，键含秒级时间戳（一单可多轮退款，固定键会吞账；CAS 赢者才记账，重放不重复）。
- **D4 pg_http/sql CAS 扩展**：`revoke_queued_for_order` 两支 CAS 的 status 条件扩为 `in.(active,frozen)`；已起算恢复复用 `unfreeze_for_order`（frozen→active 无条件 CAS——排队/未激活行已被收回，剩余 frozen 行即已起算行，无需独立方法）。sql（sqlite）repo 同步同语义实现，保持双实现 parity。
- **D5 展示零后端聚合改动**：`License.merge` 已跳过 frozen；明细端点按行状态透出，前端对 frozen 渲染「退款处理中」徽标（pill-warn 词汇，既有胶囊形态），未知状态按原文渲染防御（statusText/statusSub 双兜底）。
- **D6 排队计算取"active+frozen 全家族"**：`find_active_by_*`（active-only）喂 tier/设备/授权等可用性消费方保持不变（fail-safe 排除 frozen）；两处激活顺延基准（payments/activate_code、licensing/activate_code）改为 `find_all_by_username` 后按 `status in (active,frozen)` 过滤——冻结行继续占排队位，取消退款后终点不变。

## Risks / Trade-offs

- 冻结写崩到 R1 下次收敛之间（最长约 1 小时）套餐仍生效——与今日现状等同，可接受；自愈幂等，重跑 0 新增。
- S端 e2e 全 mock，测不出后端漏接线——以单测＋契约测试（双实现 CAS 条件对拍）补位，回归必须全绿。
- 前端对 frozen 是新状态——防御性回退已入 scenario，避免后端先行/前端滞后窗口白屏。

## Open Questions

- 无（冻结范围、写序、自愈归属均已在方案评审拍板）。
