# docs/arc — 架构文档

三层次架构文档，自顶向下：

| 层 | 文档 | 回答的问题 |
|----|------|-----------|
| 1 | [01-system-architecture.md](01-system-architecture.md) | C端 × S端 作为整体：部署拓扑、双端契约（权益/鉴权/支付/更新）、发布链、失败降级、架构红线 |
| 2 | [02-c-client-architecture.md](02-c-client-architecture.md) | C端 内部：pywebview + React 19 前端 + FastAPI 后端 + SQLite/文件双存储、AI 客户端、SSE 写作链、打包发版 |
| 3 | [03-s-server-architecture.md](03-s-server-architecture.md) | S端 内部：FastAPI 4A 分层（interfaces/application/domain/infrastructure）、订单状态机、pg_http 双仓储、Vue 3 门户、支付对账链、CloudBase 部署 |
| 4 | [04-data-architecture.md](04-data-architecture.md) | 数据：C端 单库事实源（全量入库/KV 路由/指纹留档/资产包契约）、S端 单库账本（11 表/台账/下单快照）、跨端数据流、治理红线 |

## 阅读约定

- **本地看图**：打开 [preview.html](preview.html)（单文件、内联 mermaid，双击即用，四篇带导航）；GitHub 网页端也能原生渲染各 md 的 mermaid 图。VS Code 预览需装 Mermaid 插件。
- **事实来源是代码**：本文是 2026-09-11 快照。模块清单、端点、状态机转移均取自当天 main；代码先行，文档滞后时以代码为准并回改本文。
- **契约类内容**（权益基线、feature key、时区口径）的单一事实源不在这里：权益契约 = `docs/contracts/entitlement-defaults.json`，工作流与设计规范 = 根 `CLAUDE.md` 与 `docs/design-c/prototypes/`。
- 图为 mermaid，GitHub 直接渲染。

## 快速对照

| 关心什么 | 去哪 |
|----------|------|
| 两端怎么配合、谁管数据 | 01 §1/§5 |
| C端↔S端 具体接口与授权时序 | 01 §4.2，03 §2.1 |
| 打 tag 后发生什么 | 01 §3.3，02 §4，03 §5.1 |
| 生产 PG 为什么走 HTTP | 03 §2.4 |
| 订单/退款到底几种状态 | 03 §2.3 |
| C端 设定存哪、正文存哪 | 02 §3.3，04 §1 |
| 数据怎么备份/搬家/跨版本升级 | 04 §1.5/§1.6 |
| 钱的账本和对账怎么设计 | 04 §2.2/§2.3 |
