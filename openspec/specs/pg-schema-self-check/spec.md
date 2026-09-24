## Purpose

S端 生产库（CloudBase PG）表结构不随部署迁移、靠人工执行 DDL，存在"代码上线了、列没加"的漂移风险（theme-preferences 即因此返工）。本能力规定两道防线：部署流水线的上线前 schema 门禁（缺列即阻断发布、经 MCP 应用 DDL 后放行），以及 pg_http 启动时的运行时自检告警（兜底防绕过）。

## Requirements

### Requirement: 部署前 schema 门禁

S端 自动部署流水线 MUST 在部署后端服务之前，用与启动自检同源的必需表/列清单探测生产库；探测方式 MUST 与启动自检一致（既有 PG HTTP 通道，不引入 SQL 直连）。存在缺失表或缺失列时，流水线 MUST 中止本次部署（后端与前端均不发布）并在日志输出完整缺失清单；齐备时 MUST 放行部署。必需表/列清单 MUST 与 ORM 元数据保持机器对拍（模型新增而清单遗漏即测试失败，豁免须显式登记）。被门禁拦截后的恢复路径 MUST 为：用元数据生成的 DDL（生成脚本产出）经 CloudBase MCP 应用后重跑部署，MUST NOT 依赖手写等价 SQL。

#### Scenario: 生产缺列阻断发布

- **WHEN** 流水线运行时生产库缺少清单内的表或列
- **THEN** 部署在部署后端之前失败，后端与前端均未发布
- **THEN** 流水线日志可见全部缺失项（`表名.列名` / 表名），可直接作为 MCP 应用 DDL 的依据

#### Scenario: 生产 schema 齐备放行

- **WHEN** 生产库包含清单内全部必需表与列
- **THEN** 门禁通过，部署流程照常继续

#### Scenario: 清单与模型漂移被测试拦截

- **WHEN** 某 ORM 模型新增列，但 `pg_schema.REQUIRED` 未同步且未登记豁免
- **THEN** 对拍测试失败并列出未登记的 `表.列`，漂移在合入前暴露

#### Scenario: 恢复 DDL 由元数据生成

- **WHEN** 门禁拦截后运维需补齐缺失列
- **THEN** 运行生成脚本得到与模型元数据一致的 DDL 语句，经 MCP 应用后重跑部署即放行

### Requirement: pg_http 启动自检

服务以 pg_http 后端启动时，系统 MUST 在开始对外服务前，对维护清单中每张必需表的全部必需列各执行一次存在性探测（探测走既有 PG HTTP 通道，不引入 SQL 直连）。必需表/列清单 MUST 覆盖仓储层实际读写的全部表与列（含 payments 域仓储：tiers/skus/orders/trade_events/reconciliation_reports/invoices）。

#### Scenario: 全部表列齐备
- **WHEN** 生产库包含清单内所有必需表及必需列
- **THEN** 启动日志出现一条 info 级 `event=app.schema_check` 记录，`result=ok`，并携带探测的表数与列数

#### Scenario: payments 域表纳入清单
- **WHEN** payments 域任一表（如 orders）在生产库缺失
- **THEN** 自检缺失项中可见该表名，门禁按缺失拦截部署

### Requirement: 缺失告警

自检发现缺失必需表或缺失必需列时，系统 MUST 输出一条 warning 级结构化日志：`event=app.schema_check`、`result=fail`，并逐项列出缺失的表名/列名；日志 MUST NOT 包含任何行数据或凭据。缺失 MUST NOT 导致启动失败或进程退出。

#### Scenario: 必需列缺失（生产 theme 列漏加的复现形态）
- **WHEN** 某必需表存在但清单中的列不存在
- **THEN** 启动日志出现 warning 级 `event=app.schema_check result=fail`，缺失项中可见 `<表名>.<列名>`，服务照常启动
- **THEN** 其余未缺失表列的探测仍继续完成，不因单表缺失中断

#### Scenario: 必需表缺失
- **WHEN** 清单中的某张表整体不存在
- **THEN** 启动日志的缺失项中可见该表名，服务照常启动

#### Scenario: 文本列类型漂移（2026-08-31 device_registry.user_id bigint 事故形态）
- **WHEN** 清单内标注为 text 族某列在生产库存在，但类型为数值族（select 存在性探测 200）
- **THEN** 哨兵探测（`?select=<col>&<col>=eq.<哨兵>&limit=1`）返回 400 且错误码含 22P02
- **THEN** 该列计入缺失项，服务照常启动

### Requirement: 探测自身失败不阻断

自检期间探测请求因网络等原因失败时，系统 MUST 将该表按"探测失败"记入同一条告警日志并继续启动，MUST NOT 抛出异常中断启动流程。

#### Scenario: 探测请求网络失败
- **WHEN** 某表的探测请求超时或连接失败
- **THEN** 告警日志包含该表且标注探测失败，服务照常启动

### Requirement: 仅 pg_http 启用

非 pg_http 后端（sqlite）MUST NOT 执行本自检——该模式启动时已由 alembic 自动迁移保证 schema。

#### Scenario: sqlite 启动
- **WHEN** `DB_BACKEND` 为 sqlite
- **THEN** 启动日志不出现 `event=app.schema_check`，启动行为与现状完全一致

### Requirement: server_default 对拍

清单 MAY 按列声明语义承重的期望 server_default，且每一声明 MUST 同时存在于必需表/列清单（保证默认值对拍不因缺列而失效）。探测 MUST 经网关根 OpenAPI 元数据（既有 PG HTTP 通道）比对实际默认值；不一致 MUST 计入 `mismatch` 清单，与缺失同待遇：门禁拦截部署、启动自检告警。元数据不可得时 MUST 按"探测失败"降级，不阻断启动。

#### Scenario: 默认值漂移拦截（实证形态）
- **WHEN** 某声明了期望默认值的列在生产库存在但默认值缺失或不符（如 deletion_status 无 DEFAULT，新注册行落 NULL 使注销 CAS 永不匹配）
- **THEN** 门禁日志可见 `表.列#default(期望值)` 并 exit 1 中止部署
- **THEN** 启动自检日志 `mismatch=` 字段可见同一清单，服务照常启动

#### Scenario: 元数据不可得降级
- **WHEN** 网关根 OpenAPI 不可得（非 200 或非 JSON）
- **THEN** 该项按探测失败（probe_failed=openapi）记账，不抛异常、不阻断启动；门禁按探测失败 fail-closed
