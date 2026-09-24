## Context

见 proposal.md 的 Why。落地相关现状（实勘）：

- 打戳：`client/backend/main.py:128-143` 写 `app_meta`（`schema_id` + 版本快照），`except SQLAlchemyError: pass` 无日志。状态机（`db_lifecycle.py:324-339`）对「有表但 `schema_id` 缺失/不符」判 `mismatch` 改名——件本身按规格仍作为候选可一键带回，缺的是「为什么会这样」的线索。
- 清理：`db_lifecycle.deletable_candidates`（:478-492）只按 `migration.history` 的 `source_stamp` 过滤；`_record_completion`（`migration/router.py:217-218`）仅在 `status=="ok"` 写 history，而 engine 的 `status` 在「整表跳过 / FK 违规 / 带回 0 本」时仍是 `ok`；history 条目不含 `tables_skipped`/`fk_violations`。前端 `LegacyMigrateModal.tsx:192-196` 的三条件门只看本次 report。
- 备份：`_dump_hooks`（`backup/export.py:284-294`）payload 与 `_hook_row_fields`（`importer.py:372+`）白名单都不含 `planned_volume_no`；`test_backup_roundtrip.py:493-497` 用键集完全相等冻结旧契约。
- 验收门：`client/frontend/e2e/db-version-upgrade.spec.ts:21` 未设 `UP11_DATA_DIR` 即整组 skip；`client/backend/scripts/upgrade_drill.py` 无 workflow 调用。
- 死表：`models/volume.py:75-80,98-101` 的 `VolumeCastMember` 零读写，relationship `lazy="selectin"` 每次空查。
- 时间口径：`db_lifecycle.py:282`、`migration/engine.py:199`、`backup/export.py:46,67,323` 裸 `datetime.now()`（`CLAUDE.md:11` 红线）。

## Goals / Non-Goals

**Goals:**

- 三个数据安全缺口（打戳静默、清理门、白名单）在合入前被测试钉住。
- db-per-version 的验收门从纸面变成 CI 实际执行。
- 死表与时间口径两个纪律债同批清掉。

**Non-Goals:**

- 不新增 UI（打戳失败不加前端提示；mismatch 件的可带回性已由规格保证）。
- 不改清理清单的展示形态（仍由前端展示，判定移到后端）。
- 不删既有库文件里的 `volume_cast_members` 表（C端无 DDL 路径；只删模型与读写路径，旧表成为无主表，数据保留）。
- 不做候选扫描的性能优化（整库拷贝项单独立项，见复审报告）。

## Decisions

**D1：打戳失败只加 error 日志，不加 UI。**
数据不丢（mismatch 件仍进候选、空书架流程会提供带回），缺的是排障线索；加 UI 需前端改动且触发面窄，收益不抵成本。备选（已弃）：打戳失败时把库判 `fresh_boot` 复用——会在指纹未知时误用形状不符的库，风险高于收益。

**D2：清理门下沉后端，老 history 条目按「不完整」保守处理。**
`deletable_candidates` 只认 `migration.last.source_stamp`（对齐规格），并校验 history 条目的 `tables_skipped`/`fk_violations` 为空；老条目缺新字段 → 视为不完整、不进待删清单（fail-safe：少删优于误删）。history 条目补记 `book_count_source`。

**D3：白名单补键 + 把冻结断言改成「必含」。**
roundtrip 测试的「键集完全相等」会保护缺陷（补字段即判回归），改为断言必含键集合 + 新键存在性；加键兼容不升 `format_version`（沿用 v1 契约的加键规则）。

**D4：验收门进 nightly，用既有 `UP11_DATA_DIR` 机制。**
nightly 的 e2e 步骤设 `UP11_DATA_DIR` 指向 docker 栈宿主侧挂载点，使 UP-11 活体链路真跑；`upgrade_drill version-chain` 接入 nightly 或打包流水线（取 nightly，避免拖慢发版）。备选（已弃）：进 PR 门禁——链路依赖 docker 栈与多版本库构造，代价过高。

**D5：`VolumeCastMember` 只删模型层。**
模型、relationship 与读侧空查一并删除；导出 YAML 里 `cast_members` 键名保留（外部消费方），在 change 目录登记保留理由。

**D6：时间口径机械替换。**
5 处统一 `datetime.now(UTC).replace(tzinfo=None)`；`migration/engine.py` 内已有 `_now_iso()`（aware UTC）保持不动，避免同文件第三种口径。

## Risks / Trade-offs

- [老 history 条目保守处理使可删清单暂时变小] → 属期望行为（少删不误删）；向导无需改文案，清单可能为空即空。
- [UP-11 进 nightly 拉长夜间时长] → 接受；失败即红可定位到具体版本链步骤。
- [删 `VolumeCastMember` 模型后，若仍有外部脚本读写该表] → 全仓检索确认零消费方（codegraph callers 已验证）；旧库表保留，最坏情况是无主数据而非丢数据。
- [打戳失败仅日志，用户仍可能先看到空书架] → 空书架流程本就会提供带回入口（规格保证），日志面向排障；若后续出现真实工单再评估 UI 提示。

## Migration Plan

1. 分支内实施；无 schema 变更、无数据迁移（死表仅删模型层）。
2. 上线随下一版 C端 发布；回滚 = revert 提交。
3. nightly 验收门接入后观察一轮，确认 UP-11 与 version-chain 稳定绿。
