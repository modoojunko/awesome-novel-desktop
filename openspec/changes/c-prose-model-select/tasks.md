# tasks — c-prose-model-select

> 用户口径（2026-10-08）：「生成正文的弹窗页面，需要增加一个作者可以选大模型的下拉选项，选了哪个大模型就用哪个大模型去生成正文，方便作家规划的时候用一种模型，生成正文的时候可以更换。前提是模型配置有多个模型可选，可以跨模型供应商」。

## 1. 原型先行

- [x] 1.1 `docs/design-c/prototypes/book.html` `#modalAi` 补「生成模型」选择位（触发位「配置名 · 模型名」+ 就地展开的 `.mp-*` 弹层：按配置分组、组内模型行、绑定行标「本书模型」＋标签行说明「仅本次生成生效（提示词润色/刷新仍用本书模型）」）；原型局部样式新增 `.mp-trigger`/`.mp-group`/`.mp-flag` 三词，沿用既有 token 与字号档（11.5/12/12.5px）。**验证 ✓** `node scripts/design-lint.mjs`：严格扫描 31 文件（含 book.html 全量）零违规；存量统计段不变。
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记 c-prose-model-select 小节（5 条：选择位形态／三词入册／原型就地展开 vs 实现 portal+fixed 的形态差异／不进 parity 截图的依据／<2 可选不渲染）。**验证 ✓** 条目与原型、实现逐字对得上（触发位文案、组头、标记、说明行）。另判定：`.mp-*` 族未入 `docs/ux/design-language.html` 与 `scripts/design-vocab.mjs`（先例＝c-api-config-auto-models 业务层词汇），本次只增同族三词、不动令牌/语气档 → 无标准升格动作、无 design-cross。

## 2. 后端：按次模型对（解析 / 校验 / 记账）

- [x] 2.1 `ai_client.py`：`get_ai_client_for_novel(novel_id, *, api_config_id=None, model=None)` 支持按次覆盖对（配置存在且未软删 + 归属本书用户 + `vendor != "zhuque"` + Key 可解密 + `model ∈ parse_models(cfg.models)`；半对＝`ValueError`），未给定时路径逐字不变。**验证 ✓** `tests/test_write_model_override.py::TestOverrideResolution` 7 例全绿（覆盖取所选配置/模型与 base_url、未覆盖取本书模型、清单外、朱雀、已删除＋他人＋不存在、无可用 Key、半对）。
- [x] 2.2 `write/router.py`：`POST ""` 解析 body 的 `api_config_id`/`model`，**在 `StreamingResponse` 之前**解析覆盖客户端——非法对 400 JSON（可读错因），不产生流、不发调用、无副作用。**验证 ✓** `TestWriteEndpointOverride`：合法覆盖 200 + 真解析捕获 `qwen2.5:14b`；默认路径请求/行为不变；非法对 400（含「模型清单」文案、无 `data:`、无上游调用、无记账行、本书绑定不变）；半对 400。
- [x] 2.3 `write/router.py` 三处记账改记实际模型 id + 配置 id（成功/超时/失败）。**验证 ✓** 成功路径 TokenLog `model=qwen2.5:14b`、`api_config_id=c2`；默认路径 `model=deepseek-v4-flash`、`api_config_id=c1`；失败路径（上游抛错）`write_chapter_fail` 行同样记覆盖对——存量 `model="haiku"` 变量传递违规收敛（intro-genre-settings「计量层记实际模型 id」既有条款）。

## 3. 前端：选择位与链路透传

- [x] 3.1 `types/api-config.ts` 加 `ModelSelection`；`lib/ai.ts` `streamChapterWrite` 第 5 参 `modelSelection?`——两覆盖皆缺时不带 body（逐字不变）。**验证 ✓** vitest 全套（110 文件 / 1309 例）通过 + e2e 断言请求体三态（默认无模型对 / 只 prompt / prompt+模型对）。
- [x] 3.2 `workbench/ProsePane.tsx`（`ProseHandle.startWriting`/`startStream`）与 `NovelWorkspace.tsx`（`handleAiConfirm`）透传 `modelSelection`。**验证 ✓** `npx tsc --noEmit` 零错；`AiModal.test.tsx` 断言 `onConfirm(prompt, undefined)` 与携带对两种形态。
- [x] 3.3 `workbench/modals.tsx` 加 `ModelPicker`/`ModelField`（挂载于弹窗打开时；`ai_state !== ready` 或可选项 < 2 整行不渲染；弹层 portal+fixed、`role=listbox/option`、方向键/Enter/Esc 只收弹层、外点关闭；本书绑定行标「本书模型」）；`design/model-config.css` 加 `.mp-trigger`/`.mp-group`/`.mp-flag`（`.mp-item` 改 flex 容纳尾注）。**验证 ✓** `AiModal.test.tsx` 16 例（新增 6 例：默认本书模型不携带 / 换跨配置模型携带 / 换回撤销 / 单选不渲染 / 未就绪不渲染 / Esc 只收弹层不关弹窗）；截图人查：弹层按配置分组、跨供应商可辨、绑定行尾注就位。

## 4. E2E

- [x] 4.1 `e2e/prompt-pipeline.spec.ts` 新增「生成模型选择位：默认本书模型不带按次模型对、换模型后进请求体」（模型域打桩＝两配置×三模型 + 本书就绪；`/write` 桩读 `postDataJSON`）。**验证 ✓** 通过（4.1s）。**跑法（本会话轻量隔离栈，非 docker）**：`DATA_ROOT=/tmp/... SERVER_API_BASE=<假S> ENTITLEMENT_LEGACY_TRIAL=1` 裸起 uvicorn + 假 S端（register/login 发 token）+ 独立 vite（`/api` 代理指自己 uvicorn，`strictPort`）+ 临时 playwright config（**去掉 globalTeardown**——默认 sweep 会打共享栈容器）；`E2E_BASE_URL/E2E_S_API/E2E_CLIENT_DATA` 指向自己。**坑（10-08 实锤）**：缺 `ENTITLEMENT_LEGACY_TRIAL=1` 时 trial 无到期被降免费（`trial_no_expiry`）→ AI 入口弹「升级 PRO」、`/prompts` 403，表现为整轮假红（docker 栈在 `docker-compose.yml:92` 注入该变量）——轻量栈必须自带。
- [x] 4.2 同文件其余用例回归。**验证 ✓** 4 例通过；1 例存量红「编辑工具箱：开章不入历史」（`prose-redo` 断言）——**A/B 定罪**：pristine `origin/main` 应用在同栈同跑，同例同红 → 与本次改动无关。

## 5. 回归

- [x] 5.1 后端：`.venv/bin/python -m pytest tests/ -q` ＝ **2089 passed, 1 skipped**；`ruff check --extend-select F811,F821,F841 .` ＝ **All checks passed!**（本次修掉一条 UP032）。
- [x] 5.2 前端：`npx tsc --noEmit` **零错**；`npx vitest run` ＝ **110 文件 / 1309 例全绿**（含新增 6 例）。
- [x] 5.3 设计门禁：`npm run design:lint` 全绿（严格 31 文件零违规）。parity（DESIGN_PARITY=1，本会话隔离栈）：
  - 模型配置屏 **2/2 通过**（本次动的 `.mp-item`/新增三词未扰动既有屏）；预览屏 1/1 通过；书架屏 6/7（`quota` 2.693% 存量红＝判例在册）。
  - 书工作台屏 4 例红：`free·workbench` 12.335% / `modal-delete` 12.658% / `modal-prefs` 12.497% / `modal-upgrade`（原型 `#btnUpgrade3` 点击超时）——**A/B 对 pristine `origin/main` 应用同栈同跑：失败集合与差异率逐字相同（12.335/12.658/12.497 + 同超时）** → 全部存量红（原型 demo-bar 未隐藏族），本次零新增漂移。
- [x] 5.4 双端影响判定（proposal Design Impact）：单端（C端）、不触 `base.css` 令牌与 `pill/notice/sk/panel/f-err` 共享段 → **不跑** `node scripts/design-cross.mjs`（依据：本次只用 C端 model-config 作用域 `.mp-*` 词汇；S端 无对应面）。
- [x] 5.5 `openspec validate c-prose-model-select --strict` ＝ **Change 'c-prose-model-select' is valid**；`openspec validate --specs` ＝ **60 passed, 0 failed**。

## 6. 环境收尾

- [x] 6.1 本会话隔离栈已拆：uvicorn(8100)/假 S(19100)/vite(5199,5198) 逐口 kill（逐口复验为空）；临时 playwright/vite config 与 `test-results/` 已删；A/B 用 pristine worktree（`/tmp/an-baseline`）已 `worktree remove`；`/tmp/wmo-e2e` 已删。主检出与共享 docker 栈零触碰（`git status` 无本会话残留）。
