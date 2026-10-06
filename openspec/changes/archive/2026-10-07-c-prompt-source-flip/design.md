# c-prompt-source-flip — 设计

## Context

- 现状与动机见 proposal.md。要点：模板编辑在主库 `client/backend/prompts/`（58 个 `.prompt`），纳管/发布在 awesome-novel-prompts（sync.py 镜像＋publish.py＋release.yml）。
- loader 三跳解析（`client/backend/prompts/__init__.py`）：①已装包（内存解密＋读时校验）→ ②包内目录（开发/测试态）→ ③`PromptPackMissing` → 503 四态卡；`PROMPT_PACK_MODE=force` 禁第②跳（e2e 强制包模式）。所有消费方（`load_layers`、`load_fragment`、`_rules_sections`）都经 `load()` 走同一解析，改造点单处。
- 带纳管注释的镜像文件可直用为开发源，但**剥注释必须先收口**：`load_layers`/`load_fragment` 有剥、`sync.publish_clean()` 发布前剥，而现存裸 `load()` 调用不走这些路径——`settings/ai_router.py:1890/1914/1934/1993/2018`（style 家族 `.format()`，全文进 user 消息）、`volumes/ai_plan.py:168` `_rules_sections()`（`volume_rules` 注入 expand/check 的 **system**），另有 `settings/name_registry.py:27` 待审。改造前提＝剥注释统一移入 `load()`。
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
- 目录解析抽**共享 helper**：`prompts/__init__.py` 与 `prompt_pack/sync.py::_dev_fallback_available()`（包状态 phase 判定）同源——现状两处各自扫目录，不同源会出现「四态卡判未就绪而 AI 可用」。
- **frozen 发布包禁用第②跳**（`getattr(sys, "frozen", False)`）：用户自设 env 也不读明文目录，维持主 spec「已装包＝发布态唯一来源」的字面不变量。
- 备选否掉：①submodule（私有仓＋打包/CI 复杂度，且「主库零模板」目标打折）；②开发态装真包（需登录/换钥/CDN，离线不可用，开发体验重）；③gitignored 生成副本（多一步生成与陈旧风险）。
- 兼容：`PROMPT_PACK_MODE=force` 仍优先禁第②跳；解析序其余不变；兜底 `PromptPackMissing` 语义不变。

### D2 容器挂载点 `/app/prompt_templates`

- compose `client-backend` 增只读挂载 `${PROMPTS_DIR:-../awesome-novel-prompts/prompts}:/app/prompt_templates:ro`，并以 `PROMPT_PACK_DEV_DIR=/app/prompt_templates` 注入；本地 e2e 三份 compose（e2e／e2e-iso／e2e-dossier）同批。
- 不能挂 `/app/prompts`——那是 loader 包目录，会遮蔽代码。
- 原生直跑（`scripts/dev-up.sh --native`，handoff.md 原生配方）同批注入 `PROMPT_PACK_DEV_DIR`（默认 sibling、`PROMPTS_DIR` 可覆盖）——原生模式不经 compose，漏注入即 AI 全 503。

### D3 剥注释收口到 `load()`（翻转前置改造）

- 现状并非「全部路径都剥」：裸 `load()` 调用 6+ 处不剥（style 五处→user 消息、`_rules_sections`→system、`name_registry` 待审）。改造＝**把文件头连续 `## `/空行剥除移入 `load()` 返回前**（与 README「加载时自动剥除」口径、`load_fragment` 现有实现同构）；`load_layers` 的既有剥除保留（重复无害）。
- 钉子测试逐调用点断言：style 五处 `.format()` 产物、`_rules_sections()` 两段注入、`load_layers`/`load_fragment` 产物均不含注释行与 `## ★★` 哨兵（dev 带注释源与包源两态同断言）。

### D4 内容闸门迁提示词仓 CI（搬 pytest，不建新体系）

- 6 个正文断言测试迁提示词仓（该仓已是 Python 工具仓，pytest 为最小增量）；「注释↔占位符对拍」并入其 lint 命令。
- 主库侧：触及模板的行为测试改桩夹具（conftest 提供含所需标记的最小模板）；新增源码级门禁——主库树出现 `.prompt` 即红。
- 备选否掉：主库 CI 配提示词仓 token 拉检出（无先例，且与「闸门随源」的长期解相悖）。

### D5 sync.py 保留 renderer 角色＋对拍（不降成只读校验）

- 删除「上游锚／`--check`／从主库拉」方向；**注释头仍由 CURATED 幂等重渲染**（读 CURATED → 重写源文件注释头、正文不动）——否则 CURATED 与文件内注释成为两份可各自漂移的元数据；对拍（占位符清单 vs 实提取）并入其 lint 命令；manifest/README 继续生成（`source` 段改记本仓 commit）。
- 编辑口径：改正文＝直接编辑文件；改元数据＝改 CURATED 后跑生成刷新注释头。
- publish.py 不动（继续 `publish_clean` 剥注释后切包）。

## Risks / Trade-offs

- [新机器/新会话没有 sibling 检出 → 开发态 AI 全 503] → CLAUDE.md 快速开始加「clone 提示词仓为 sibling」一步；缺检出时走既有四态卡引导；compose 变量 `PROMPTS_DIR` 可覆盖路径。
- [主库 CI 不再拦模板内容回归] → 有意取舍：闸门随源走；提示词仓 CI 是模板改动的必经点。
- [注释块漏剥进模型输入（裸 `load()` 调用点）] → 剥注释收口 `load()`＋逐调用点钉子测试（D3）。
- [回退分支（包内目录）被误当主源] → 主库零模板后该分支自然为空，仅测试夹具使用。
- [e2e/演示栈在非 sibling 布局（/tmp worktree）下默认挂载路径解析不到 → 静默 503] → e2e 跑批脚本/runbook 显式传 `PROMPTS_DIR`；验证清单含「/tmp 布局起栈」用例。

## Migration Plan

四步，各自可独立验收、独立回退（回退该步提交即可）：

1. **loader 改造**：`load()` 收口剥注释＋第②跳支持 `PROMPT_PACK_DEV_DIR`（含共享 helper、frozen 禁用）——纯增量，兼容现状；钉子测试逐调用点覆盖。
2. **开发栈/e2e 接入**：compose 挂载＋env＋CLAUDE.md/README 文档；本地与容器双路验证 AI 通路。
3. **闸门迁移**：6 个正文断言测试迁提示词仓 CI；主库测试改桩夹具；主库加「零 .prompt」源码级门禁（先允许清单存在，第 4 步收紧）。
4. **删模板**：`git rm` 58 个 `.prompt`；清扫残留引用；sync.py 降级；提示词仓 README/手册更新。

前 3 步完成后主库仍可独立工作；第 4 步是翻转点，回退即恢复文件。

## Open Questions

- 提示词仓 release.yml 是否加「内容闸门前置」（发布前跑 lint）——实施时定，不影响本设计。
- 无 sibling 检出机器的「离线开发副本」——明确不做；若实践中成痛点另立项。
