# c-prompt-source-flip — 设计

## Context

- 现状与动机见 proposal.md。要点：模板编辑在主库 `client/backend/prompts/`（58 个 `.prompt`），纳管/发布在 awesome-novel-prompts（sync.py 镜像＋publish.py＋release.yml）。
- loader 三跳解析（`client/backend/prompts/__init__.py`）：①已装包（内存解密＋读时校验）→ ②包内目录（开发/测试态）→ ③`PromptPackMissing` → 503 四态卡；`PROMPT_PACK_MODE=force` 禁第②跳（e2e 强制包模式）。所有消费方（`load_layers`、`load_fragment`、`_rules_sections`）都经 `load()` 走同一解析，改造点单处。
- 带纳管注释的镜像文件可直用为开发源：`load_layers` 与 `load_fragment` 均剥文件头连续 `## ` 行，`sync.publish_clean()` 在发布前剥；已 grep 核实生产代码无裸 `load()` 输出未剥离文本的调用点。
- 主库依赖面（已核实）：打包零依赖（build.spec 不打包模板，CI 有「产物零 *.prompt」断言）；开发/测试态硬依赖（本地后端、docker 开发栈、本地 e2e）；约 14 个测试文件触及模板，其中约 6 个为正文断言类（分层协议/占位符对拍/去AI味 v4.4/节奏规则/死引用/边界注入）。
- 既有先例：sibling 检出约定 `${S_SERVER_DIR:-../awesome-novel-server/server}`（compose）；主库 CI 不配跨仓 token（e2e-scheduled 未配 `S_SERVER_TOKEN` 时整轮跳过）。

## Goals / Non-Goals

**Goals:**

- 提示词单源：awesome-novel-prompts `prompts/` 为唯一编辑源；主库检出与 CI 产物零 `.prompt`。
- 开发/测试态来源可配、缺省不劣化：缺检出时维持既有 503/四态卡语义，不新增第二形态。
- 模板内容闸门随源走：分层/对拍/正文断言在提示词仓 CI 拦截；主库 CI 不再依赖模板内容。
- 发布链零改动：包格式、验签换钥、publish.py/release.yml、`prompt_pack` 同步器全部不动。

**Non-Goals:**

- 不引入 submodule 或复制品；不在主库存「离线兜底副本」（YAGNI，必要时另立项）。
- 不改用户可见行为（四态卡文案/状态语言/接口形态）。
- 不重做纳管注释体系：注释随源文件走；sync.py 只留「注释↔占位符对拍」与 manifest/README 生成。

## Decisions

### D1 开发态来源＝env 目录（`PROMPT_PACK_DEV_DIR`）＋回退包内目录

- 第②跳改为：优先读 `PROMPT_PACK_DEV_DIR` 指向的目录；未设时回退「包内目录」（`prompts/__init__.py` 同目录，兼容历史测试夹具与临时文件）。
- 备选否掉：①submodule（私有仓＋打包/CI 复杂度，且「主库零模板」目标打折）；②开发态装真包（需登录/换钥/CDN，离线不可用，开发体验重）；③gitignored 生成副本（多一步生成与陈旧风险）。
- 兼容：`PROMPT_PACK_MODE=force` 仍优先禁第②跳；解析序其余不变；兜底 `PromptPackMissing` 语义不变。

### D2 容器挂载点 `/app/prompt_templates`

- compose `client-backend` 增只读挂载 `${PROMPTS_DIR:-../awesome-novel-prompts/prompts}:/app/prompt_templates:ro`，并以 `PROMPT_PACK_DEV_DIR=/app/prompt_templates` 注入；本地 e2e 三份 compose（e2e／e2e-iso／e2e-dossier）同批。
- 不能挂 `/app/prompts`——那是 loader 包目录，会遮蔽代码。

### D3 带注释镜像文件直接作开发源

- 已核实加载路径全部剥 `## ` 头；补钉子测试：dev 源带注释块加载后，产物不含注释行与哨兵行（`## ★★`）。

### D4 内容闸门迁提示词仓 CI（搬 pytest，不建新体系）

- 6 个正文断言测试迁提示词仓（该仓已是 Python 工具仓，pytest 为最小增量）；「注释↔占位符对拍」并入其 lint 命令。
- 主库侧：触及模板的行为测试改桩夹具（conftest 提供含所需标记的最小模板）；新增源码级门禁——主库树出现 `.prompt` 即红。
- 备选否掉：主库 CI 配提示词仓 token 拉检出（无先例，且与「闸门随源」的长期解相悖）。

### D5 sync.py 降级为「校验＋索引生成器」

- 删除「上游锚／`--check`／从主库拉」方向；保留 CURATED 元数据与对拍（改在本仓直接跑）；manifest/README 继续生成（`source` 段改记本仓 commit）。
- publish.py 不动（继续 `publish_clean` 剥注释后切包）。

## Risks / Trade-offs

- [新机器/新会话没有 sibling 检出 → 开发态 AI 全 503] → CLAUDE.md 快速开始加「clone 提示词仓为 sibling」一步；缺检出时走既有四态卡引导；compose 变量 `PROMPTS_DIR` 可覆盖路径。
- [主库 CI 不再拦模板内容回归] → 有意取舍：闸门随源走；提示词仓 CI 是模板改动的必经点。
- [注释行漏剥进提示词] → 加载链已剥；补钉子测试（dev 源含注释，加载产物不含 `## ★★` 哨兵行）。
- [回退分支（包内目录）被误当主源] → 主库零模板后该分支自然为空，仅测试夹具使用。
- [e2e/演示栈忘挂载导致假红] → e2e compose 同批加挂载；配方与文档同步更新。

## Migration Plan

四步，各自可独立验收、独立回退（回退该步提交即可）：

1. **loader 支持 `PROMPT_PACK_DEV_DIR`**（含注释剥离钉子测试）——纯增量，兼容现状。
2. **开发栈/e2e 接入**：compose 挂载＋env＋CLAUDE.md/README 文档；本地与容器双路验证 AI 通路。
3. **闸门迁移**：6 个正文断言测试迁提示词仓 CI；主库测试改桩夹具；主库加「零 .prompt」源码级门禁（先允许清单存在，第 4 步收紧）。
4. **删模板**：`git rm` 58 个 `.prompt`；清扫残留引用；sync.py 降级；提示词仓 README/手册更新。

前 3 步完成后主库仍可独立工作；第 4 步是翻转点，回退即恢复文件。

## Open Questions

- 提示词仓 release.yml 是否加「内容闸门前置」（发布前跑 lint）——实施时定，不影响本设计。
- 无 sibling 检出机器的「离线开发副本」——明确不做；若实践中成痛点另立项。
