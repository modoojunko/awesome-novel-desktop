## 1. 原型先行（style-settings.html ＋ ADJUSTMENTS.md）

- [x] 1.1 `docs/design-c/prototypes/style-settings.html`：蒸馏空态改双入口（「粘贴文本蒸馏」主按钮直开弹窗＋「从文件/章节选样本」次入口，沿用 `btn-open-distill` 行为）；样本选择页顶部加「直接粘贴文本」入口；新增粘贴弹窗层（Modal wbStyle 同款 mcard：大 textarea＋实时去空白字数＋区间状态提示＋「取消/开始蒸馏」footer，区间外禁用提交；超限提示优先于精确计数）。验证：浏览器打开原型切评审态，三处改动可见且字数提示随输入变化
- [x] 1.2 同原型：作者画像确认卡补「六行基线预览」段（每行「行名＋约 X（±容差%）」；含锁定行「保留上一版」标记的展示口径）；右栏蒸馏行 desc 补第三路「或直接粘贴文本」。验证：原型确认卡可见六行预览与锁定行标记
- [x] 1.3 `ADJUSTMENTS.md` 登记本 change 小节：双入口／弹窗层／预览段（含锁定行标记）／右栏 desc，逐条写原因；如实陈述门禁口径——style-settings 屏无像素 parity 基线场景（parity CASE 仅 list 屏），但原型在 design-lint 严格名单内。验证：登记条目与原型 diff 一一对应

## 2. 后端：step1 粘贴路与预览行单源

- [x] 2.1 `client/backend/settings/ai_router.py` step1 受理 `body.text`：判定式 `str(body.get("text") or "").strip()` 非空才重启，**分支置于续跑短路判断之前**；`text` 非字符串返回 400；清 draft 仅内存态（沿用 save-at-end，校验/LLM 失败时旧 draft 零写入）；粘贴路 `samples_used=["粘贴文本"]`、`chapter_count=0`；3,000–10,000 去空白校验沿用既有中文文案。验证：`tests/test_style_settings_v2.py` 新增用例——粘贴受理（fake AI 记录的 prompt 含粘贴子串）、2,100 字 400 含「再补」、12,000 字 400 含「挑最有代表性」、非字符串 text 400、预置旧 draft＋粘贴重启（旧产物作废、draft 被清）、无 text 续跑短路保持，全部通过
  - 完成证据：docker 容器（镜像 ai-novel-client-backend 挂 worktree /app）`pytest tests/test_style_settings_v2.py -q` → 31 passed
- [x] 2.2 落卡行单源：step3 共享落盘块以 `build_baseline` 构建**新值行**存 `draft.step3.rows`，构建注入 `confidence = confidence_for(draft.sample_chars, draft.chapter_count)`（force 重跑同样重建）；`commit_draft` 优先复用 rows、**仍执行锁定行覆盖环**（按落卡时点正式区锁定态取上一版值＋记 mixture），无 rows 的旧 draft 回落现算；顺手修 `quant_doc` 浅拷贝地雷（`dict(_EMPTY)` → `deepcopy`，history 快照跨项目串档已实证）。验证：pytest——draft.step3.rows 与 commit 后正式区六行逐字段相等且容差档位正确（10,000 字→±20% 而非缺省 ±30%）；锁定行落卡保留旧值＋mixture 记录；无 rows 回落用例；quant_doc deepcopy 回归断言
  - 完成证据：同容器含新增 7 用例全绿；deepcopy 断言防 history 串档
- [x] 2.3 后端全量回归：`cd client/backend && python -m pytest`（在 docker 栈或 venv 按现行跑法）。验证：全绿，存量 style 三件（settings_v2/banned_words/shadow_api）无回归
  - 完成证据：挂 client/ 整目录按 CI 同款依赖 `pytest tests/ -q --timeout=30` → 1191 passed, 2 failed（brand/entitlement 基线红）；origin/main 基线同法对照同 2 败——环境性非回归

## 3. 前端：弹窗组件与接线

- [x] 3.1 `client/frontend/src/lib/styleApi.ts`：加 `countSampleChars`（码点迭代 `[...text.replace(/\s/g,"")].length`，docblock 写明与后端的已知残差清单）；`StyleQuantDraft.step3` 补 `rows` 类型（`Record<rowKey, {value: string; tolerance: number}>`）；新建 `settings/StylePasteModal.tsx`（`Modal wbStyle width=560`＋`afterTitle` PRO 标＋大 textarea＋实时字数/区间提示＋取消/开始蒸馏 footer；超限 fast-path：原始长度超上限直接提示并跳过精确计数；文案按 design-language §13：按钮动词、补救提示带出口）。验证：vitest 组件测试（字数提示、区间外禁提交、超限 fast-path）＋`tsc --noEmit` 零错
  - 完成证据：`npx vitest run src/__tests__/StylePasteModal.test.tsx` 6 passed；`npx tsc --noEmit` 0 errors
- [x] 3.2 `StyleSettingForm.tsx` 接线：空态主按钮「粘贴文本蒸馏」直开弹窗＋次按钮**沿用 `btn-open-distill` id 与行为**（存量 e2e/settings-forms 按此断言）；样本选择页顶部「直接粘贴文本」入口；`runSteps` 改造为显式 `startStep`＋`text`（修 state 闭包旧值竞态，粘贴强制从 step1 起跑）；**粘贴文本存组件态，重试的 step1 body 持续携带直至成功或取消**；`SettingsView.tsx` 右栏蒸馏行 desc 补「或直接粘贴文本」（与原型同批）。验证：e2e 新用例「预置旧 draft＋粘贴」锁重启语义＋「step1 失败→重试仍带 text」用例
  - 完成证据：实现侧补钉——粘贴链重试按钮显式 `startStep: 0`（state 残留旧蒸馏步数会让重试直跳 step3 吃 400），由用例 ⑥ 首次运行抓出并修复
- [x] 3.3 确认卡渲染六行预览（`data-od-id="portrait-baseline-preview"`）：条件渲染（`rows` 缺失整段隐藏，沿 quant-baseline `if (!row) return null` 同款容错）；锁定行按 `quant.baseline` 锁定态显示「保留上一版：旧值」标记（只读两个服务端字段做展示规则，不复制业务算法）；`__tests__/StyleSettingForm.fewShots.test.tsx` 的 style-quant mock 适配（无 rows 时断言预览段隐藏）。验证：e2e 断言预览渲染格式（「约 X（±Y%）」）与落卡后 `quant-baseline` 同构——预览＝落卡的真源一致性由 2.2 的 pytest 承担，e2e 不超桩能力口径；vitest 全绿
  - 完成证据：fewShots＋PasteModal 两文件 15 passed（含新增锁定行预览正例/无 rows 隐藏断言）
- [x] 3.4 `e2e/style-quant.spec.ts` 新增粘贴全链（沿既有有状态 KV 桩）＋短文禁提交用例；重启语义锁法：step1 桩**仅在 body.text 非空时**重置 draftState 并打 `pasted` 标，step3 桩校验 `pasted` 否则回 400（前端若回归为闭包旧值起步直调 step3，用例即红），commit 后断言 `quant.sample_chars`＝粘贴字数。验证：本机 docker 栈 playwright 该 spec 全绿（含既有 4 条回归）
  - 完成证据：`npx playwright test e2e/style-quant.spec.ts` → 6 passed（含用例 ⑤⑥）；e2e-cleanup 残留清零
- [x] 3.5 画像确认挂起态补 ghost「取消，稍后再说」（`setDistillView("closed")`、draft 保留，重进面板可恢复确认卡）。验证：e2e 断言取消后可走粘贴入口、重开蒸馏仍回到确认卡

## 4. 回归与门禁（实际结论回填）

- [x] 4.1 `client/frontend`：`tsc --noEmit`＋`npm run design:lint`。验证：两者零错误（lint 对新增类名/id 的拦截检查含原型严格名单），输出结论追加在本 checkbox 下
  - 完成证据：`npx tsc --noEmit` 0 errors；`npm run design:lint` 报 2 处违规均在未触碰文件（preview.html 注释「#414」/AcctMenu.tsx 注释「#346」被 hex 正则误判，`git diff origin/main` 对两文件 0 差异）——origin/main 存量基线红，非本次引入；本次新增/修改文件未上榜
- [x] 4.2 `npm run design:check` 作为全链回归照跑，但如实记录：style-settings 屏不在任何 parity CASE（parity 仅 list 屏三场景），本 change 的门禁影响面＝design:lint 原型严格扫描。验证：lint 结论＋「parity 不适用」事实一并追加在本 checkbox 下
  - 完成证据：`DESIGN_PARITY=1 npx playwright test e2e/design-parity.spec.ts e2e/design-parity-preview.spec.ts` → 4 passed（list 屏三场景＋preview 屏，像素差 <0.2% 达标）；style-settings 屏不在 parity CASE，lint 段结论见 4.1
- [x] 4.3 本机 docker 栈全量 e2e（改交互必跑全量的既定规矩；注意宿主 19000 端口占用/登录限频等已知坑按 runbook 规避）。验证：全绿；如有存量红逐条登记并对照 main 基线证实非新回归
  - 完成证据：`npx playwright test`（全量，本 worktree docker 栈 5174/19000）→ 157 passed, 14 skipped（存量 skip 登记项）, 0 failed，6.6min；e2e-cleanup 残留清零
- [x] 4.4 共享段判定复核：本 change 无令牌档位/组件词汇/状态语言改动（依据 proposal Design Impact），`design-cross.mjs` 不需跑。验证：结论追加在本 checkbox 下
  - 完成证据：判定成立——本 change 未动 base.css 令牌/基础组件类，仅 book.css 追加 paste-* 全局类（新业务类，非共享段），S端 零改动
