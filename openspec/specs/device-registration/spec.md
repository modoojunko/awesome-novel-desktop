# device-registration Specification

## Purpose

S端 设备注册（authorize 时写 `device_registry`）的去重与竞态契约：以 `(user_id, fingerprint)` 为去重键做 upsert，展示字段随每次授权刷新；并发竞态输掉插入时回落更新而非 500 或留重。幻影行清理与唯一约束核查的运维口径见 `docs/ops/device-registry-dedupe.md`。

## Requirements

### Requirement: 注册按 (user_id, fingerprint) 去重 upsert

authorize 的设备注册 SHALL 以 `(user_id, fingerprint)` 为去重键：键已存在 SHALL 更新 hostname/os/os_arch/last_active_at/updated_at 并保留原行 id 与 bound_at（首绑时间）；键不存在 SHALL 新建行。同一设备重复授权 MUST NOT 产生新行，设备列表 total_count MUST NOT 因此增长。

#### Scenario: 同指纹重复授权复用记录

- **WHEN** 同一用户以同一 fingerprint 再次完成浏览器授权
- **THEN** `device_registry` 行数不变，该行 hostname/os/os_arch/last_active_at 被刷新，id 与 bound_at 保持不变

### Requirement: 注册竞态撞唯一约束回落更新

注册「先查后插」的间隙被并发请求抢先插入同键行、插入撞唯一约束（PG 23505）时，SHALL 回落为对该键行的更新并正常返回；MUST NOT 向调用方返回 500，MUST NOT 留下重复行。唯一约束缺失的部署上 SHALL 退化为直接插入（行为不劣于本 change 之前）；非约束的数据库错误 SHALL 按既有异常路径上抛。

#### Scenario: 并发授权竞态输家回落更新

- **WHEN** 两个并发授权同时通过存在性检查，后插入者被 `(user_id, fingerprint)` 唯一约束拒绝（23505）
- **THEN** 后插入者对该键行执行更新并返回授权成功，`device_registry` 仍只有一行

#### Scenario: 非约束错误原样上抛

- **WHEN** 注册插入因其他数据库错误失败（如类型漂移 22P02）
- **THEN** 错误不被吞也不误判为竞态，按既有异常路径上抛
