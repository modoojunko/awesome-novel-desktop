# Proposal: s-server-repo-split

## Why

C端 开源路径已拍板（公开仓 Actions 标准 runner 免费、含 macOS——安装器双平台打包/parity/nightly 的分钟数大头搬家），其前提是把商业化大脑划出公开面：支付、鉴权、套餐、发码、提示词分发。用户已建空私有仓 `modoojunko/awesome-novel-server`（描述：「awesome-novel的服务端，支付、提示词、鉴权权限、套餐、营销都在这」）。本 change 执行 S端 拆仓：代码＋历史＋CI＋specs 整体迁移，ai-novel 收敛为 C端 真源。

实勘基础（2026-10-05）：`server/` 目录自洽度高，对仓外唯一硬引用是 `server/frontend/src/constants/brand.ts:8` 的 `../../../../brand/brand.json`；跨端耦合集中在三条管线（openspec、e2e/compose、CI workflows）。

## What Changes

1. **新仓 bootstrap**：awesome-novel-server 建 `server/` 内容（干净拷贝，剥离运行时脏文件）＋ openspec 骨架（独立 config.yaml，S端 子集基线）＋随迁 workflows＋brand 副本＋LICENSE/NOTICES＋CLAUDE.md。
2. **历史提取**：`git filter-repo` 按路径提取（`server/`＋随迁根级文件），保留 blame；顺带从历史剥离被跟踪的运行时脏文件（`server/license.db`、`logs/`、`data*/`、`test-results/`）。
3. **openspec 拆分**：按「requirement 实现在哪端，spec 归哪仓」迁移（约 21 个，执行时逐个实核定稿）；在途 change 归属处置（`s-prompt-pack-delivery` 拆两半；其余 c-* 留守）。
4. **ai-novel 切割**：删 `server/`；compose 全家桶 `build: ./server` 改 sibling checkout 约定；`design-cross.mjs` 与 nightly e2e 改双 checkout；`openspec/config.yaml` context 与根 `CLAUDE.md` 去掉 S端 表述。
5. **CI/secrets**：新仓配置部署凭据（TCB envId/PG key）；旧仓删 S端 workflows 与对应 secrets。
6. **验证**：新仓 CI 全绿＋tcb 部署冒烟；C端 e2e 连 sibling S端 全绿；两仓 `validate --specs` 基线重建。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——本 change 是仓拓扑手术，无 requirement 行为变更；spec 文件是整体搬迁、内容不变；部署拓扑与仓拓扑不入 spec。因此 `skip_specs: true`。）

## Design Impact

无 UI 改动——纯仓拓扑/CI/构建工程，不触原型、不触两端共享段样式。

## 非目标

- **C端 公开仓本体**：内容边界（prompts stub、S端 敏感 spec 过滤）、ai-novel 历史消毒（删除 server/ 不消历史——公开前仍需 filter）、许可证拍板，全部另立 change。
- **提示词包分发三刀**（S端 发钥端点＋CEK 表、C端 拉包安装、publish.py）：各自独立 change，实施位置按本 change 划定的仓归属（S端 仓/C端 仓/prompts 仓）。
- **openspec store 第三仓**：维持两仓各持，不做中央 spec 库。
- ai-novel 内任何产品行为变更。
