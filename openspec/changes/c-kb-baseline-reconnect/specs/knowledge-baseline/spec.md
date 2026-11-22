## ADDED Requirements

### Requirement: 撤回机制退役与官方基线接回

官方基线的版权撤回机制（2026-11-11 撤回时代引入）SHALL 退役其**自动**触发面，保留其**手动**合规急刹能力，使 CDN 上通过签名验收的基线包（v5 起）能被客户端正常同步消费：

- **清理范围按版本收窄**：自动清理（启动钩子、迁移搬运后、备份恢复后三调用点共享同一计划）SHALL 只删除 `pack_version` 低于接回版本的官方基线行及其派生（书级副本、晋升条目）——被撤回版本的条目 SHALL NOT 回充，接回版本及以后的行 SHALL NOT 被任何自动路径删除。
- **撤回戳退役自动打点**：清理完成路径 SHALL NOT 无条件打 `kb_baseline_retired=1`/版本归零——仅当本次真清了低于接回版本的行时才维持撤回语义；`is_retired` 判定保留（手动打戳＝合规急刹，全局停同步）。
- **一次性接回过渡**：存量客户端（已盖 retired 戳）SHALL 在升级后自动完成接回——幂等清除 retired 戳＋落接回标记，无需用户动作；过渡后周期复查 SHALL 自然拉取 CDN 当前签名包应用（验签、整层替换、pack_version 记账等既有口径不变）。
- **撤回清单硬闸**：被撤回版本的 `src_key` 清单 SHALL 永不回充（清理计划侧永久持有）。
- **迁移搬运后与恢复备份后**：从旧槽搬运/旧备份恢复带回的低版本行 SHALL 被清理（合规），接回版本及以后的行 SHALL 存活（不再依赖「清后重同步」自愈）。

#### Scenario: 启动钩子不再清接回后的行

- **WHEN** 客户端已同步 v5（基线层存在 pack_version=5 的行）且应用重启
- **THEN** 启动钩子 SHALL NOT 删除 pack_version=5 的行，SHALL NOT 重盖 retired 戳；官方精选层内容保持完整

#### Scenario: 存量客户端自动接回

- **WHEN** 已盖 retired 戳的存量库升级到含本 change 的版本并启动
- **THEN** retired 戳被幂等清除＋接回标记落库；周期复查拉取 CDN 签名包（v5）整层替换应用；`/api/kb/baseline/status` 报告 pack_version=5 与真实条目数

#### Scenario: 迁移搬运后 v5 行存活

- **WHEN** 旧槽（已同步 v5）随版本升级搬运进新槽
- **THEN** 搬运后清理 SHALL NOT 删除 pack_version=5 的行（无需清后重同步自愈）

#### Scenario: 恢复旧备份只清低版本行

- **WHEN** 恢复一份包含撤回版本行的旧备份
- **THEN** 低于接回版本的行被清理（版权合规），若备份同时含接回版本行则 SHALL 存活

#### Scenario: 撤回清单永不回充

- **WHEN** 任何清理计划执行
- **THEN** 被撤回版本 `src_key` 清单内的条目 SHALL NOT 重新出现在官方层；清单本身 SHALL NOT 被清除

#### Scenario: 合规急刹仍可用

- **WHEN** 手动将 retired 戳置位（合规紧急撤回）
- **THEN** 同步入口 SHALL 跳过（全局停同步）；该能力 SHALL NOT 被本 change 移除

#### Scenario: 验签与整层替换口径不变

- **WHEN** 接回后的同步执行
- **THEN** Ed25519 双验（latest＋manifest）、`format_client` 代际闸、整层事务替换、用户层覆盖（overlay）保全等既有口径 SHALL 全部不变——本 change SHALL NOT 触碰同步内容链路
