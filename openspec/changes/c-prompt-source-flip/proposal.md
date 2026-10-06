# c-prompt-source-flip — 提示词源翻转（提示词仓为准）

## Why

提示词资产现在两头都有：编辑在主库 `client/backend/prompts/`，纳管与发布在私有仓 awesome-novel-prompts（sync.py 镜像＋publish.py 发布链）。双源的成本已经实付过一次：2026-10-06 镜像仓静默落后 6 笔、版本锚滞后一个上游提交，靠人工对齐才发现。而主库这份明文模板只服务开发/测试态——安装包早已硬切零 `.prompt`（CI 断言钉住），生产唯一来源是 CDN 加密包。把源翻转到提示词仓，主库收敛为纯 C 端代码；模板的编辑、纳管注释、内容闸门与发布同仓一处完成，锚/镜像概念整体退役。

## What Changes

- **BREAKING（开发工作流）**：移除主库 `client/backend/prompts/` 的 58 个 `.prompt` 模板——提示词编辑唯一入口改为 awesome-novel-prompts 仓（`prompts/` 即源，带纳管注释）。`prompts/__init__.py`（loader）与 `prompt_pack/*`（同步器）保留；生产解析序（已装包→ 503）不变。
- **loader 解析序第②跳改「开发态模板目录」**：新增 env `PROMPT_PACK_DEV_DIR` 显式指定（本地＝sibling 提示词检出）；未设时回退包内目录（兼容历史测试夹具）。带纳管注释的源文件可直接作开发源——`load_layers`/`load_fragment` 本就剥 `## ` 注释行，且已核实生产代码无裸 `load()` 调用点。
- **开发态接入 sibling 检出**：本地与 docker 开发栈按既有 sibling 约定挂提示词检出（`${PROMPTS_DIR:-../awesome-novel-prompts/prompts}`，compose 只读挂载＋env 注入），本地 e2e 同批；缺检出时 AI 功能维持既有 `PromptPackMissing` 503 语义（行为不劣化）。
- **模板内容闸门迁移**：分层协议闸门（test_prompt_layering）、占位符对拍（原 sync.py CURATED 校验）、正文断言类（去AI味 v4.4 断言/节奏规则/死引用/边界注入等约 6 个测试文件）迁入提示词仓 CI；client 侧保留 loader 与同步器的桩测试。
- **sync.py 退役「拉主库」方向**：`--check` 与上游锚概念取消，降级为提示词仓自身的 lint（注释↔占位符对拍）；publish.py 发布链不变（继续吃本仓 `prompts/`）。
- **文档同批**：CLAUDE.md 与相关 README 的提示词编辑/开发流程改写为「提示词仓改 → 提交推送 → 发布走 Actions」。

## Capabilities

### New Capabilities

- 无（本变更不新增 capability——改的是既有 loader 契约与开发态来源约定）

### Modified Capabilities

- `prompt-pack-delivery`：
  1. MODIFIED「模板加载解析序（C端 loader）」——第②跳由「包内目录直读」改为「开发态模板目录（`PROMPT_PACK_DEV_DIR` 指定，缺省回退）」。
  2. ADDED「提示词模板源与内容闸门归属」——主库零 `.prompt`；开发/测试态模板来源＝sibling 提示词检出（env/挂载）；模板内容闸门（分层/占位符对拍/正文断言）SHALL 住提示词仓 CI。

## Design Impact

- 无用户可见界面改动：`PromptPackMissing` → 503 → 四态卡语义、文案、状态语言均不变；不触任何两端共享段；无原型需求。

## Impact

- 代码：`client/backend/prompts/*.prompt`（58 文件删除）、`client/backend/prompts/__init__.py`（解析序）、`docker-compose.yml`（挂载＋env）、测试面约 14 个文件（6 个正文闸门迁走，其余改桩夹具）、本地 e2e 与开发栈来源。
- 跨仓：awesome-novel-prompts（CI 增收内容闸门 job；sync.py 降级为 lint；README 同步）；awesome-novel-server 不动。
- 不变项（明确不改）：安装包零 `.prompt` 硬切断言、CDN 包格式与档位映射、验签/换钥契约、`prompt_pack` 同步器七道校验、发布链（publish.py/release.yml）。
