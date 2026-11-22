## Context

v5 已上生产 CDN（双签验收全 PASS、8197 条），但 C端消费被撤回时代机制挡死——真机实锤：0.49.3 上 `sync_baseline` 七分钟零触发，根因＝`app_meta.kb_baseline_retired=1`。撤回机器三件套（勘察结论）：

1. **boot 钩子**（main.py:268-276）：每次启动 `revoke_official_baseline()` → `apply_revocations`。
2. **`_apply` 幂等标记**（revocation.py）：marker＋`baseline_left==0` 才跳过——**基线层有行（v5 同步后）就不跳**，会全删＋重盖 retired 戳。
3. **`sync_baseline`/`_sync_impl`/probe 三处 `is_retired` 闸**（baseline.py:367/405/427）。

有利条件：`KbBaselineEntry.pack_version` 现成（整层替换时记账）；`is_retired` 消费面仅 baseline 三处；撤回机器从未进 spec（无历史包袱）；「重收 reconcile」（version_reconcile）是拆书侧与本 change 无关；v5 `format_client='0.45.0'` 与 `_KNOWN_FORMAT_CLIENTS` 相容；v5 已在 CDN 双签验收（本 change 不触碰内容链路）。

## Goals / Non-Goals

**Goals:**

- v5 行在 boot/迁移后/恢复后三条自动路径下永不删除。
- 存量客户端一次启动即自动接回，周期复查拉 v5 应用。
- 撤回能力（force 整层清理＋retired 急刹＋撤回清单）作为合规工具完整保留。

**Non-Goals:**

- 不触碰同步内容链路（验签/整层替换/overlay 保全——#1122 与 c-kb-baseline 既有口径）。
- 不动 `world_char_purge`（三本书世界/角色——独立合规闸，仍有效）。
- 不做任何前端/文案改动。
- 不自动清除用户书里的 v5 派生副本回收站语义（book_copies 撤回口径随版本收窄继承）。

## Decisions

**D1 接回版本常量＝清理的分界线**：`RECONNECT_PACK_VERSION = 5`（revocation.py 模块级）。`plan_revocations` 的 `baseline_ids` 选择从「全部 KbBaselineEntry」收窄为「`pack_version < RECONNECT_PACK_VERSION`」；书级副本/晋升条目的判定（REVOKED_SRC_KEYS/evidence 口径）不动——v5 行派生的副本 src_key 不在撤回清单，天然不进计划。备选「按包白名单（只删撤回清单命中的行）」——过于依赖清单完整性，弃；「不收窄、靠清后重同步自愈」——boot 每次启动都删＋重拉，浪费且接回窗口期读面空窗，弃。

**D2 `_apply` 完成路径重构**：现状尾部无条件 `VERSION_KEY=0`＋`LAST_SYNC=revoked`＋`RETIRED=1`。重构为：本次真清了低于接回版本的行（计数>0）→ 保留撤回语义（戳＋版本归零＋审计 marker 照旧）；没清任何行（纯 v5 库）→ 只更新 marker 为接回态、不动 retired/版本。**marker 语义升级**：`kb_baseline_revocation_marker` 从「撤回完成」扩为「最后清理审计」（记录 at/清理行数/版本界），幂等跳过条件从「marker＋全零」改为「marker 版本界 ≥ 当前接回版本界」——避免 v5 行数>0 触发无谓重扫。

**D3 一次性接回过渡**：main.py lifespan 在 boot 钩子**之前**插一步：若 `kb_baseline_retired==1` 且 `kb_baseline_reconnect_done` 未设 → 删 retired 键＋落 `kb_baseline_reconnect_done=1`（幂等；直接 SQL 写 app_meta，与 carry 完成记录同款直连口径）。放在 boot 钩子前保证「先解锁再收窄清理」顺序成立。

**D4 三个调用面零改动**：boot 钩子、迁移后（migration/router.py:757）、恢复后（backup/importer.py:198-208）的调用代码不动——收窄发生在 `plan_revocations`/`_apply` 内部，三处自动继承。备选「逐调用点加版本判断」——三处重复且易漏，弃。

**D5 急刹保留**：`is_retired()` 三处消费不动；合规紧急时手动 `app_meta.kb_baseline_retired=1` 即全局停同步（文档进 design/tasks 验收项）。撤回清单 `revoked_baseline.REVOKED_SRC_KEYS` 原样保留在清理计划侧。

## Risks / Trade-offs

- [D1 硬编码 5：未来再撤 v5 时要改常量] → 接受——撤回本就是人工合规动作（手动改常量＋打 retired 戳＋force 清理），机制保留、自动面退役；常量旁注释串起「撤回四步」操作口径。
- [D2 marker 语义升级的存量兼容] → 存量 marker（撤回完成态）读取时视为「版本界=4」（低于 5）→ 首次 boot 必然重入 _apply：真清 0 行（存量库行数为 0）→ 落新语义 marker＋清 retired——恰好就是接回过渡本身，无需额外一步。D3 的显式过渡与此互为保险。
- [v5 行 pack_version 是否真为 5] → 真机已验：CDN manifest version=5，同步整层替换按 manifest version 记账（既有口径）。
- [恢复旧备份只带回 <5 行] → 清理后重同步自愈（sync 仍在周期复查里），可接受。
- [撤回能力未来再启用需要改代码] → 接受——比「自动撤回误杀合法内容」的代价小；急刹（停同步）走 retired 戳零代码。

## Migration Plan

PR → CI（后端 pytest：新增接回场景组）→ 发版随灰度。真机验收：本机 0.49.3 装含本 change 的版本 → boot 日志出现接回过渡 → 周期复查拉 v5 → `/api/kb/baseline/status` version=5＋entries=8197 → 知识库页「官方精选」层内容重现。回滚：revert 即恢复撤回态（v5 行被 boot 钩子清掉，重新 retired——数据可重拉，无损失）。

## Open Questions

（无）
