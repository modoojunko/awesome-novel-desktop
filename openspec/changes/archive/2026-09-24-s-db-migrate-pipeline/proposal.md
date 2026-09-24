## Why

S端 schema 演进链目前两条腿都断：alembic 迁移在 `c3a51e09d7e2` 后分叉成两个 head（`c4d5e6f7a8b9` / `e8f2a4b6c8d0`），`alembic upgrade head` 必抛 MultipleHeads；启动期迁移又 fail-open（warning 后落 `create_all`），sqlite 路径的迁移链从未真正执行过。

更危险的是两条分支存在真实的顺序依赖：`a001_users_surrogate` 整表重建 users/codes/device_grants/device_registry（新表列清单显式写死），而 `a1b2c3d4e5f6`（注销四列）与 `c4d5e6f7a8b9`（codes.refund_requested）是加列。若加列分支先执行，重建会把它们静默吃掉——而 `alembic merge` 生成的合并点按 revision 字符串排序恰好会排出这个错误顺序。

生产 pg_http 侧则根本不走 alembic：DDL 靠 MCP 手写等价 SQL 应用，仓库里的迁移链对生产是死代码；部署前 schema 门禁虽已存在（`server/scripts/pg_gate.py`，fail-closed），但其必需清单 `pg_schema.REQUIRED` 是手写的，可能与 ORM 模型漂移——漂了就是「门禁放行、生产缺列、请求期 500」。

## What Changes

- **线性化迁移链**：`a1b2c3d4e5f6.down_revision` 由 `c3a51e09d7e2` 改挂 `e8f2a4b6c8d0`，确立「先重建、后加列」的唯一顺序（**BREAKING** 仅对显式 pin 过旧 revision 的调用方；仓库内无此调用方，且多 head 下任何环境都不可能成功 `upgrade head` 过）。
- 新增迁移可升级性测试：fresh sqlite `upgrade head` 后，schema 与 ORM 元数据逐表逐列一致（重建吃列、漏列即测试红）。
- CI 增 `alembic heads` 单头断言；`server-backend-ci` 路径过滤纳入 `server/alembic/**`（改迁移现在不触发该 CI）。
- **sqlite 启动迁移 fail-closed**：`upgrade head` 失败时拒绝启动（响亮日志 + 非零退出），不再 warning 后带伤 `create_all` 兜底；fresh 库由基线迁移建全表。
- **生产 DDL 单源**：`pg_schema.REQUIRED` 与 ORM 元数据对拍守卫（缺项即测试红）；新增脚本从元数据生成缺失项的 DDL（供 MCP 应用），替代手写等价 SQL。
- 时间口径清理：S端 `datetime.utcnow()` ×5 改钦定写法 `datetime.now(UTC).replace(tzinfo=None)`。

## Capabilities

### New Capabilities

- `s-schema-migration`: S端 迁移链治理——单头与线性顺序、sqlite 启动迁移到 head 且失败即拒绝启动、生产 DDL 由 ORM 元数据单源生成、必需清单与元数据对拍。

### Modified Capabilities

- `pg-schema-self-check`: 部署前门禁的必需清单 MUST 与 ORM 元数据保持机器对拍；被门禁拦截后的恢复 DDL MUST 由元数据生成而非手写等价 SQL。

## Impact

- 迁移链：`server/alembic/versions/a1b2c3d4e5f6_users_deletion.py`（改 down_revision）、新增测试。
- 启动：`server/app/main.py`（迁移失败分支改为拒绝启动）。
- 门禁与自检：`server/app/infrastructure/pg_schema.py`（清单对拍守卫）、`server/scripts/`（新增 DDL 生成脚本）。
- CI：`.github/workflows/server-backend-ci.yml`（路径过滤 + 单头断言）、`.github/workflows/s-server-deploy.yml`（恢复路径文档口径）。
- 时间口径：`server/app/application/payments/refund_flow.py`、`server/app/interfaces/web_api/payments.py`。
- 无用户可见界面改动：不触前端、不触共享段，Design Impact 不适用。
