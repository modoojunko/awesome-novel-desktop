## Context

见 proposal.md 的 Why。落地相关的现状约束（实勘）：

- 链现状：`bb1fcc46b21f`（基线建全 6 表）→ `c3a51e09d7e2`（users.theme）→ 分叉：
  - 加列支：`a1b2c3d4e5f6`（users 注销四列）→ `c4d5e6f7a8b9`（codes.refund_requested）
  - 重建支：`a001_users_surrogate`（整表重建 users/codes/device_grants/device_registry，列清单显式写死）→ `a002_payments_tables` → `d7e9f1a3b5c7`（device_grants.challenge）→ `e8f2a4b6c8d0`（users.token_version）
- `a1b2c3d4e5f6`/`c3a51e09d7e2` 用 `sa.inspect(op.get_bind())` 做幂等，离线 `--sql` 模式不可用。
- 启动：`server/app/main.py` 目前 `upgrade head` 失败仅 warning 后 `create_all`。
- 生产：部署前门禁已存在且 fail-closed（`server/scripts/pg_gate.py`），清单 `pg_schema.REQUIRED`（`server/app/infrastructure/pg_schema.py:25`）手写；DDL 由 MCP 手写等价 SQL 应用。
- CI：`server-backend-ci` 路径过滤不含 `server/alembic/**`；全仓 workflow 无 alembic 断言。

## Goals / Non-Goals

**Goals:**

- 链单头、顺序由 `down_revision` 显式固定，且「重建不吃加列」有测试钉住。
- sqlite 启动迁移失败不再静默带伤启动。
- 生产缺失项的恢复 DDL 有可执行单源（元数据生成），清单与模型的漂移在合入前被测试拦截。

**Non-Goals:**

- 不改生产部署拓扑（DDL 仍经 MCP 应用，只是来源改为生成）。
- 不把 alembic 接到 pg_http 运行时（PostgREST 通道不接受 DDL，维持带外应用 + 门禁）。
- 不做存量 sqlite 旧库的数据回填（沿用既有 runbook 口径）。

## Decisions

**D1：线性化（改 `down_revision`）而非 `alembic merge`。**
合并点会让 alembic 按 revision 字符串排序两条分支（`c4d5e6f7a8b9` < `e8f2a4b6c8d0`），即加列支先跑、重建支后跑——重建的显式列清单会静默吃掉注销四列与 refund_requested。线性化把 `a1b2c3d4e5f6.down_revision` 由 `c3a51e09d7e2` 改为 `e8f2a4b6c8d0`，顺序唯一且语义正确（先重建、后加列）。
安全性依据：多 head 下任何环境都无法成功 `upgrade head`，不存在已戳记这两个 revision 的 `alembic_version`；实施前全仓检索有无 pin 具体 revision 的脚本/文档（有则同批更新）。
备选（已弃）：merge revision + 在重建迁移里补列——修一次但保留隐式排序，未来分支再分叉仍会踩。

**D2：fail-closed 的边界。**
`upgrade head` 失败 → error 日志（含失败原因）+ 非零退出，不进入对外服务。`create_all` 仅保留在迁移成功之后（对 fresh 库是 no-op 兜底），不再作为迁移失败的兜底。dev/CI 被坏迁移阻塞是有意为之——早暴露优于运行时 `no such column`。

**D3：DDL 单源用「手写清单 + 机器对拍 + 生成脚本」而非「清单全自动派生」。**
`REQUIRED` 除表列外还承载 server_default 期望值与类型族标注，且覆盖范围是仓储实际读写面（可小于模型全集），全自动派生会丢语义。改为：测试遍历 `Base.metadata` 与 `REQUIRED` 双向对拍（模型有而清单无 → 红，除非在显式豁免清单登记）；生成脚本用同一元数据类型编译缺失项的 `ALTER TABLE ... ADD COLUMN` / `CREATE TABLE`，供 MCP 直接应用。

**D4：时间口径清理随本 change 同批。**
`utcnow()` ×5 是机械替换且与 C1 同端（S端），单独开 change 不划算；CLAUDE.md 已定口径（naive UTC），不新增规格。

## Risks / Trade-offs

- [改 down_revision 影响未知 pin 方] → 实施前全仓检索 `c4d5e6f7a8b9`/`a1b2c3d4e5f6`/`upgrade <rev>` 的引用；文档与 runbook 同批改。
- [fail-closed 抬高本地启动门槛] → 迁移失败日志给出一句可执行的修复指引；可升级性测试把坏迁移拦在 CI。
- [生成 DDL 与既有手写 DDL 存在细节差异（PG 类型映射）] → 首次用生成脚本对拍一次生产既有 DDL 的实际效果（本地 sqlite 编译 + 人工核对类型变体）。
- [对拍守卫初期爆红（历史清单可能已漏项）] → 先跑对拍出清单，漏项在本次一并补齐或登记豁免。

## Migration Plan

1. 分支内完成链线性化 + 测试 + CI，先跑 `server/tests` 全量确认无回归。
2. 启动 fail-closed 随同批次上线；生产为 pg_http 后端，不触发该分支（S端生产无 alembic 路径）。
3. 生成脚本与门禁口径更新后，下次需要补 DDL 时改用它产出语句经 MCP 应用。
4. 回滚：revert 本 change 的提交即可（无数据迁移、无 schema 变更）。
