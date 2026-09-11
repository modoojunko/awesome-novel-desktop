## MODIFIED Requirements

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
