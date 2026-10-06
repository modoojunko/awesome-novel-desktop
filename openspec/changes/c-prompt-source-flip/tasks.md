## 1. 影响判定与前置

- [ ] 1.1 双端影响判定：本变更无用户可见界面改动（`PromptPackMissing`→503→四态卡语义/文案不变）、不触两端共享段、无原型需求——以此判定替代「原型先行」任务。验证＝proposal 的 Design Impact 段与本节一致；实施期 `git diff --stat` 无 `client/frontend/src` 变更
- [ ] 1.2 环境前置：确认 sibling 提示词检出在位且与主库零漂移。验证＝`ls ../awesome-novel-prompts/prompts/*.prompt | wc -l`＝58，且（可选）`python3 ../awesome-novel-prompts/publish.py verify` 之外的对拍命令无差异报告

## 2. loader：开发态来源（D1/D3）

- [ ] 2.1 `client/backend/prompts/__init__.py` 第②跳改「开发态模板目录」：优先 `PROMPT_PACK_DEV_DIR`、未设回退包内目录；路径安全校验（白名单＋realpath）沿用；`PROMPT_PACK_MODE=force` 仍优先禁第②跳。验证＝单测：env 指向临时目录可加载、未设回退、force 双禁、非法名仍拒绝
- [ ] 2.2 注释剥离钉子：dev 源带 `## ★★ 纳管注释` 哨兵块时，`load_layers`/`load_fragment` 产物不含任何注释行与哨兵行。验证＝新增单测断言产物零 `##` 头行
- [ ] 2.3 既有 loader/pack 测试回归（`test_prompts_loader`/`test_prompt_pack*`）。验证＝全绿且未放宽既有断言

## 3. 开发栈与 e2e 接入（D2）＋文档

- [ ] 3.1 `docker-compose.yml` 的 client-backend 增只读挂载 `${PROMPTS_DIR:-../awesome-novel-prompts/prompts}:/app/prompt_templates:ro`＋`PROMPT_PACK_DEV_DIR=/app/prompt_templates`；e2e 三份 compose（e2e／e2e-iso／e2e-dossier）同批。验证＝`docker compose config` 渲染含挂载与 env；起栈后任一 AI 端点可用（未装包）
- [ ] 3.2 缺检出语义验证：检出移走/改名后起栈，AI 端点维持 503 `prompts_missing` 四态卡语义（不新增错误形态）。验证＝容器内实测记录一次
- [ ] 3.3 文档：CLAUDE.md（快速开始/架构图/目录树/常用命令）与相关 README 增「clone 提示词仓为 sibling」与 `PROMPTS_DIR` 覆盖说明。验证＝按文档从零起栈一遍可跑通（记录走查结论）

## 4. 闸门迁移（D4）

- [ ] 4.1 迁 6 类正文闸门到提示词仓（pytest）：分层协议（原 `test_prompt_layering`，改扫提示词仓 `prompts/`）、注释↔占位符对拍（原 sync.py CURATED 校验并入 lint 命令）、去AI味 v4.4 断言、节奏规则、死引用、边界注入。验证＝提示词仓本地全绿；故意改坏一处模板（如删分层标记）必被拦截
- [ ] 4.2 提示词仓 CI 加闸门 job（跑 4.1＋lint）。验证＝流水线实跑绿；构造一处坏改动可红
- [ ] 4.3 主库测试改桩夹具：触及模板的行为测试（`test_ai_prompt_and_boundary`/`test_prose_pipeline`/`test_story_arc`/`test_cast_draw_ai`/`test_cast_review_ai`/`test_write_prompt_polish` 等）改 conftest 最小桩模板。验证＝主库 pytest 全绿且测试不再读 `client/backend/prompts/*.prompt`
- [ ] 4.4 主库源码级门禁：新增测试断言主库树零 `.prompt`（先以允许清单＝现有 58 文件，第 5 组收紧为全禁）。验证＝门禁当前绿；临时造一个 `.prompt` 即红

## 5. 删模板与工具收尾（D5）

- [ ] 5.1 `git rm` 58 个 `.prompt`；门禁允许清单清零；清扫残留引用（测试/脚本/文档）。验证＝4.4 门禁绿＋主库 pytest 全绿＋`git grep` 无生产代码引用模板文件
- [ ] 5.2 sync.py 降级为「校验＋索引生成器」：去「上游锚／`--check`／拉主库」方向，留对拍与 manifest/README 生成（`source` 段改记本仓 commit）。验证＝提示词仓 lint 与生成命令跑通，产物 diff 仅「来源」段变化
- [ ] 5.3 提示词仓 README/手册更新（唯一编辑源、发布流程、闸门、sibling 约定）。验证＝README 与实操一致（人工走查结论）

## 6. 回归与门禁

- [ ] 6.1 主库后端：`client/backend/.venv` 解释器跑 pytest 全量，输出通过数与零新增红结论
- [ ] 6.2 主库前端：`npx tsc --noEmit` 与 `npx vitest run` 全绿（无前端改动，防连带）；无 `client/frontend/src` 变更故 design:lint/design:check 免跑（判定见 1.1）
- [ ] 6.3 隔离栈：起本会话自有 docker 栈（独立数据目录）跑 AI 相关 e2e 子集，输出实际结论
- [ ] 6.4 打包面：跑「产物零 `.prompt`」断言与 `compile_native.py --scan`（或等价 CI 步骤）确认硬切仍成立，输出实际结论
- [ ] 6.5 双仓收口：提示词仓 CI 绿＋主库零模板门禁绿；两仓验证输出摘要记入本 change（archive 时引用）
