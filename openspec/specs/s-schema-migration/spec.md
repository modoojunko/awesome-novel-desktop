# s-schema-migration Specification

## Purpose
S端 的 schema 演进必须由一条可执行、可验证、单源的迁移链治理：链单头且顺序唯一（重建型先于加列型）、sqlite 启动迁移到 head 且失败即拒绝启动、生产 pg_http 的 DDL 由 ORM 元数据生成而非手写——使「代码上线、schema 漂移」在任何路径上都无法静默发生。

## Requirements

### Requirement: 迁移链单头且顺序唯一

alembic 迁移链 MUST 恒为单头（`alembic heads` 恰一个）。对同一张表既有整表重建、又有加列的分支，重建 MUST 排在加列之前，且该顺序 MUST 由 `down_revision` 显式线性化固定，MUST NOT 依赖合并点（merge revision）的隐式排序。

#### Scenario: 单头断言进 CI

- **WHEN** 任意 PR 改动 `server/alembic/**` 或 `server/app/**`
- **THEN** CI 断言 `alembic heads` 恰一个 head；出现第二个 head 即失败

#### Scenario: 重建不吃加列

- **WHEN** 在 fresh sqlite 库上执行 `alembic upgrade head`
- **THEN** 迁移完成后 users 表含注销四列（deletion_status/deletion_requested_at/deletion_deadline/deletion_waive_assets）、codes 表含 refund_requested——重建型迁移不吞并后加的列

### Requirement: 迁移可升级性测试

仓库 MUST 有一条测试：在 fresh sqlite 库上执行 `alembic upgrade head`，随后逐表逐列断言 schema 与 ORM 元数据（`Base.metadata`）一致；不一致 MUST 使测试失败。

#### Scenario: 漏列即红

- **WHEN** 某迁移漏加一列，或重建型迁移的新表列清单缺列
- **THEN** 可升级性测试失败并指出缺失的 `表.列`

### Requirement: sqlite 启动迁移 fail-closed

以 sqlite 后端启动时，系统 MUST 在对外服务前执行 `alembic upgrade head`。迁移失败时 MUST 拒绝启动（输出含失败 revision 的 error 级日志并非零退出），MUST NOT 以 `create_all` 兜底继续启动；`create_all` 仅允许用于迁移已成功后仍缺表的 fresh 库自愈路径。

#### Scenario: 迁移失败拒绝启动

- **WHEN** 启动期 `upgrade head` 抛异常
- **THEN** 进程以非零码退出，日志可见失败原因；服务不进入对外可用状态

#### Scenario: 迁移成功照常启动

- **WHEN** fresh sqlite 库启动且 `upgrade head` 成功
- **THEN** 表结构齐备，启动行为与现状一致（日志含迁移结果）

### Requirement: 生产 DDL 由元数据单源生成

pg_http 生产的缺失项恢复 DDL MUST 由 ORM 元数据生成（脚本产出，可复制到 MCP 应用），MUST NOT 依赖手写等价 SQL。`pg_schema.REQUIRED` 必需清单 MUST 与 ORM 元数据保持机器对拍：模型中存在而清单遗漏的表/列 MUST 使测试失败，除非在显式豁免清单中登记理由。

#### Scenario: 清单与模型对拍

- **WHEN** 某模型新增列而 `pg_schema.REQUIRED` 未同步
- **THEN** 对拍测试失败并列出未登记的 `表.列`

#### Scenario: 生成 DDL 供 MCP 应用

- **WHEN** 门禁报告某列缺失，运维需补 DDL
- **THEN** 运行生成脚本即得到与该列元数据一致的 `ALTER TABLE`/`CREATE TABLE` 语句，直接用于 MCP 应用
