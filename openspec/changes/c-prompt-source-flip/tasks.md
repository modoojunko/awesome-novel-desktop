## 1. 影响判定与前置

- [x] 1.1 双端影响判定：本变更无用户可见界面改动（`PromptPackMissing`→503→四态卡语义/文案不变）、不触两端共享段、无原型需求——以此判定替代「原型先行」任务。验证＝proposal 的 Design Impact 段与本节一致；实施期 `git diff --stat` 无 `client/frontend/src` 变更
- [x] 1.2 环境前置：确认 sibling 提示词检出在位且与主库零漂移。验证＝`ls ../awesome-novel-prompts/prompts/*.prompt | wc -l`＝58，且（可选）`python3 ../awesome-novel-prompts/publish.py verify` 之外的对拍命令无差异报告

## 2. loader：目录解析＋剥注释收口（D1/D3）

- [x] 2.1 目录解析：`client/backend/prompts/__init__.py` 第②跳支持 `PROMPT_PACK_DEV_DIR`（优先）、未设回退包内目录；路径安全校验（白名单＋realpath）沿用；`PROMPT_PACK_MODE=force` 仍优先禁；**frozen 态禁用第②跳**；解析逻辑抽共享 helper。验证＝单测：env 指向临时目录可加载、未设回退、force 双禁、frozen 禁用、非法名仍拒绝
- [x] 2.2 剥注释收口到 `load()`：文件头连续 `## `/空行在 `load()` 返回前剥除；全覆盖现存裸调用点——`settings/ai_router.py` style 五处 `.format()`、`volumes/ai_plan.py::_rules_sections()`（volume_rules→expand/check system）、`settings/name_registry.py`（先审用途）。验证＝逐调用点钉子测试：产物不含注释行与 `## ★★` 哨兵（dev 带注释源与包源两态）
- [x] 2.3 包状态同源：`prompt_pack/sync.py::_dev_fallback_available()` 改用共享 helper（dev-dir 可用⇒`get_status().phase=="ready"`）。验证＝新增单测：dev-dir 态与无来源态各断言 phase
- [x] 2.4 既有 loader/pack 测试回归（`test_prompts_loader`/`test_prompt_pack*`）。验证＝全绿且未放宽既有断言

## 3. 开发栈与 e2e 接入（D2）＋文档

- [x] 3.1 `docker-compose.yml` 的 client-backend 增只读挂载 `${PROMPTS_DIR:-../awesome-novel-prompts/prompts}:/app/prompt_templates:ro`＋`PROMPT_PACK_DEV_DIR=/app/prompt_templates`；e2e 三份 compose 为 override、应自动继承（实跑确认）。验证＝`docker compose config` 渲染含挂载与 env；起栈后任一 AI 端点可用（未装包）
- [x] 3.2 原生直跑：`scripts/dev-up.sh --native` 与 handoff.md 原生配方同批注入 `PROMPT_PACK_DEV_DIR`（默认 sibling、`PROMPTS_DIR` 可覆盖）。验证＝`--native` 起栈一次 AI 端点可用
- [x] 3.3 非 sibling 布局：e2e 跑批脚本/runbook 显式传 `PROMPTS_DIR`（/tmp worktree 下默认相对路径解析不到、静默落空）。验证＝/tmp 布局下起栈并按预期验证（可用或按未装包 503 记录）
- [x] 3.4 缺检出语义验证：检出移走/改名后起栈，AI 端点维持 503 `prompts_missing` 四态卡语义（不新增错误形态）。验证＝容器内实测记录一次
- [x] 3.5 文档：CLAUDE.md（快速开始/架构图/目录树/常用命令）与相关 README 增「clone 提示词仓为 sibling」与 `PROMPTS_DIR` 覆盖说明。验证＝按文档从零起栈一遍可跑通（记录走查结论）

## 4. 闸门迁移（D4）

- [x] 4.1 迁 6 类正文闸门到提示词仓（pytest）：分层协议（原 `test_prompt_layering`，改扫提示词仓 `prompts/`）、注释↔占位符对拍（原 sync.py CURATED 校验并入 lint 命令）、去AI味 v4.4 断言、节奏规则、死引用、边界注入。验证＝提示词仓本地全绿；故意改坏一处模板（如删分层标记）必被拦截
- [x] 4.2 提示词仓 CI 加闸门 job（跑 4.1＋lint）。验证＝流水线实跑绿；构造一处坏改动可红
- [x] 4.3 主库测试改桩夹具：**逐文件先定归属**——只测编排行为的改 conftest 最小桩模板（`test_prose_pipeline`/`test_story_arc`/`test_cast_draw_ai`/`test_cast_review_ai`/`test_write_prompt_polish` 等）；含模板正文断言的与 4.1 同批迁走（`test_ai_prompt_and_boundary` 属此类，按段拆分判定，不在本任务重复处理）。验证＝主库 pytest 全绿且测试不再读 `client/backend/prompts/*.prompt`
- [x] 4.4 主库源码级门禁：新增测试断言主库树零 `.prompt`（先以允许清单＝现有 58 文件，第 5 组收紧为全禁）。验证＝门禁当前绿；临时造一个 `.prompt` 即红

## 5. 删模板与工具收尾（D5）

- [ ] 5.1 `git rm` 58 个 `.prompt`；门禁允许清单清零；清扫残留引用——范围＝源码/脚本/文档（tests、docs、README/CLAUDE）；历史 change 文档（`openspec/changes/**` 与 archive）不改，仅当活动 change 的指引面向未来操作时才更新。验证＝4.4 门禁绿＋主库 pytest 全绿＋`git grep` 无生产代码引用模板文件
- [ ] 5.2 sync.py 保留 renderer 角色：去「上游锚／`--check`／拉主库」方向；注释头由 CURATED 幂等重渲染（正文不动，避免元数据与注释双份漂移）；对拍并入 lint；manifest/README 继续生成（`source` 段改记本仓 commit）。验证＝连跑两次生成零 diff（幂等）；改 CURATED 可刷新注释头；lint 跑通
- [ ] 5.3 提示词仓 README/手册更新（唯一编辑源、发布流程、闸门、sibling 约定）。验证＝README 与实操一致（人工走查结论）

## 6. 回归与门禁

- [ ] 6.1 主库后端：`client/backend/.venv` 解释器跑 pytest 全量，输出通过数与零新增红结论
- [ ] 6.2 主库前端：`npx tsc --noEmit` 与 `npx vitest run` 全绿（无前端改动，防连带）；无 `client/frontend/src` 变更故 design:lint/design:check 免跑（判定见 1.1）
- [ ] 6.3 隔离栈：起本会话自有 docker 栈（独立数据目录）跑 AI 相关 e2e 子集，输出实际结论
- [ ] 6.4 打包面：跑「产物零 `.prompt`」断言与 `compile_native.py --scan`（或等价 CI 步骤）确认硬切仍成立，输出实际结论
- [ ] 6.5 双仓收口：提示词仓 CI 绿＋主库零模板门禁绿；两仓验证输出摘要记入本 change（archive 时引用）
