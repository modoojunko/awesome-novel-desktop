## Why

官方基线 v5（8197 条蒸馏写法，手法/文风/文笔三概念、audit 全 clean、rights-manifest 全 `distilled_ideas_only`）已于 2026-11-22 经知识仓 CI 签名发布到生产 CDN，客户端链路（latest→manifest→entries）双签/哈希逐环验收全 PASS。但 C端消费侧被 11-11 版权撤回时代的机制挡死：`sync_baseline` 见 `app_meta.kb_baseline_retired=1` 即跳过（连 CDN 都不拉），且 boot 撤销钩子会清任何官方基线层行并重新盖 retired 戳——**真机实测 sync 七分钟零触发**。11-13 版权口径修订（蒸馏思想层不受公版限制）时挂的「C端同步待接回」是最后一件未办，v5 已上 CDN、接回即全体用户吃到官方知识层。

## What Changes

- **清理范围收窄（撤回能力保留）**：`apply_revocations` 全家（boot 钩子/迁移后/恢复备份后三调用点继承）从「清全部官方基线层」收窄为「只清 `pack_version` 低于接回版本（5）的行」——被撤回的 v1-v4 条目继续防回来，v5 行不再被误杀。行上 `pack_version` 戳现成（同步整层替换时记录）。
- **撤回戳退役自动打点**：`apply_revocations` 完成路径 SHALL NOT 再无条件盖 `kb_baseline_retired=1`/版本归零——只在真清了低于接回版本的行时才保留撤回语义；`is_retired()` 函数保留为**合规急刹**（手动打戳仍全局停同步）。
- **一次性接回过渡**：存量客户端 boot 时若 `kb_baseline_retired=1` 且接回标记未设 → 清 retired 戳＋设接回标记（幂等）；此后周期复查自然拉取 CDN v5 应用（现有整层替换＋验签链路不动）。
- **撤回硬闸保留**：`revoked_baseline.REVOKED_SRC_KEYS` 撤回清单（v1-v4 撤回的 21 项）继续守在清理计划侧，永不回充。
- **不动的东西**：迁移后清理与恢复备份清理的调用面不变（继承收窄后的行为）；`world_char_purge`（三本书世界/角色）与本 change 无关不动；`version_reconcile`（拆书版本收敛）与基线无关不动；知识库页无 UI 改动（官方精选层数据驱动自动重现）。

## Capabilities

### New Capabilities

（无——落在既有 `knowledge-baseline` capability 内）

### Modified Capabilities

- `knowledge-baseline`：
  - ADD「撤回机制退役与接回」：清理范围按 `pack_version` 收窄（v5+ 行永不自动清理）；retired 戳退役自动打点、保留为手动合规急刹；存量客户端一次性自动接回（幂等）；被撤回清单永不回充。

## Impact

- 后端：`client/backend/kb/revocation.py`（plan/_apply 收窄＋完成路径重构）、`client/backend/main.py`（boot 一次性接回过渡）、`client/backend/kb/baseline.py`（不动 sync 逻辑本身，过渡清戳后自然恢复）。
- 撤回能力不删：`apply_revocations(force=True)` 仍可整层清理（合规紧急时手动调用），`is_retired` 急刹保留。
- 无数据库 schema 变更（复用 `pack_version` 列与 app_meta 键）；无前端改动（官方精选层数据驱动）。
- 验收锚点：v5 已在生产 CDN（`latest.json` version=5、双签验真、8197 条）；本机 0.49.3 真机 `sync` 七分钟零触发的根因（retired 戳）即本 change 要拆的闸。

## Design Impact

- 受影响端：**C端 only**（S端无知识基线）。
- 受影响屏/弹层：知识库「官方精选」层——条目数据驱动自动重现，无新增界面状态、无文案改动（撤回时代无专门 UI，接回同样不加 UI）。
- 对象状态：数据层「retired 戳」语义从「永久停用」改为「合规急刹（手动）」＋「接回标记」新增（纯数据键，无界面态）。
- 共享段：零触碰。
- 原型先行：**免**——无任何用户可见界面/文案改动（数据层数据驱动重现），登记判定依据为本节。
- 文案：零新增用户可见串。
