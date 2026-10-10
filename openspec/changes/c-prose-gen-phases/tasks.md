## 1. 原型先行（C端）

- [x] 1.1 更新 `docs/design-c/prototypes/book.html`：生成态补「等待呈现（变体 A：版心首行·文案＋光标＋尾注，无框）」＋呼吸灯改为「环编辑体、首个正文片段到达起」（`stream-breath` 上移编辑区包裹）；演示链改为「等待三阶段推进（无环）→ 首字到达（行内退场＋环亮起）→ 流式写入」；改动后浏览器打开该原型、点演示链可见两条时序（视觉真值另见真界面原型草稿 `docs/design-c/drafts/ai-novel-c端-生成等待呈现-无框三变体-真界面原型.html`）
  - 证据：直驱演示链实测（file://）等待期 `lineShown=true/ring=false` → 首字后 `lineShown=false/ring=true`＋正文开写，控制台零报错；截图 `/tmp/an-proto-shots4/bookhtml-awaiting.png`、`bookhtml-typing.png`
- [x] 1.2 在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记本条目：阶段卡片落地（产品侧新增的生成态呈现）、原因（首字等待期无可视进度，用户拍板「按真实阶段摊开」）、实现位置（ProsePane/ProsePane 覆盖层）与形态依据（§5 分步行既有形态，无新视觉语言）
  - 证据：ADJUSTMENTS.md 新增「c-prose-gen-phases」节（形态/口径/parity 影响/验证/文案自查/视觉真值 六项）

## 2. 双端影响判定

- [x] 2.1 判定并记录：本改动**不触碰两端共享段**——只读复用 base.css 既有分步行词汇（`.pm-steps/.pm-step/.pm-ic`）与既有令牌，不新增/修改令牌档位、组件词汇、语气档位；新增 CSS 均为 C端 业务层（book.css 工作台段）。据此 `design-cross` 免跑，回归小节引用本判定（与 proposal「Design Impact」一致）
  - 证据：仅只读复用 base.css 既有词汇与令牌；新增 CSS 全在 C端 业务层（book.css 工作台段）→ design-cross 免跑

## 3. 后端：阶段事件与错误收尾

- [x] 3.1 `write/router.py`：`_stream_chapter` 增发阶段事件 `{"type":"phase","phase":"assemble|prompt|model"}`（组装前发 assemble、定稿提示词前发 prompt、调模型前发 model）；验证：单测断言 SSE 行序为 phase(assemble)→phase(prompt)→phase(model)→chunk*→done
  - 证据：`tests/test_prose_pipeline.py::TestGenerationPhases::test_phase_events_precede_chunks_and_done`——phase 序恰为 assemble→prompt→model，首事件＝assemble、model 在首 chunk 前，末事件＝done（有模板源跑）
- [x] 3.2 `write/router.py`：把准备段（`build_chapter_context`／提示词定稿（覆盖>存量回落>组装）／`save_prompt`／阶段推进＋commit／`build_system_prompt`／本书模型客户端构造）移入流内并包 `try/except` → 失败 `yield error` 事件并 return；**可读 4xx 校验（会员/档位/模型就绪/排队/按次模型对）保持在开流前不变**；验证：单测令准备段抛错（如模板缺失桩）→ 响应仍 200 但含 `error` 事件（SHALL NOT 空流静默结束）
  - 证据：`test_prepare_failure_yields_error_event_not_empty_stream`（200＋error 事件、无 chunk/done、未发起模型调用）＋`test_prompt_pack_missing_reports_setup_message`（「写作能力还没就绪」文案＋`event=prompts_missing` 留痕）
- [x] 3.3 检索并同步既有 `/write` 相关后端断言（准备段错误原为开流前 500；现为流内 `error` 事件）；验证：`pytest` 相关文件全绿，改动处逐条说明
  - 证据：`pytest -k write`＝有模板源 **168 passed**；CI 形态（无源）**129 passed / 39 skip / 0 failed**（原 6 例缺源失败→按缺包留痕转 skip，与既有「缺源＝跳过」口径一致）；`ruff==0.16.3 check` All checks passed

## 4. 前端：阶段状态与卡片

- [x] 4.1 `lib/ai.ts`：`StreamCallbacks` 增可选 `onPhase(phase)`；解析 `data.type==="phase"`；`doStreamFetch` 记录本流是否见过终态事件，流结束未见 → 单次 `onError("生成中断：未收到完成信号…")`（防与真实 error 事件双报）；验证：单测覆盖 phase 透传、无终态事件兜底恰报一次、正常流不误报
  - 证据：`aiStreamError.test.ts` 新增 3 例——phase 透传（恰 assemble/model）、流无终态事件补报**恰一次**（文案含「未收到完成信号」）、error 事件后不补报
- [x] 4.2 `ProsePane.tsx`：`genStage` 状态位（`startStream` 置 `assemble`；`onPhase` 推进；首个 `onChunk`／`finishStream` 清空）＋正文区覆盖层卡片（标题＋三步分步行＋尾注，`data-testid="gen-steps"`）；验证：`proseStream.test.ts` 断言生成中卡片可见、首字到达即消失、停止/失败同样消失
  - 证据：`NovelWorkspace.test.tsx` 新增用例——等待期 gen-line 可见/`.awaiting` 且 `.generating` 缺席，onPhase 推进到组装/模型两态，首字 onChunk 后 gen-line 消失且 `.prose-body.generating` 到场
- [x] 4.3 `design/book.css`：卡片覆盖层定位（与 680 版心同位、`pointer-events:none`、不参与编辑链布局）＋生成态占位退场（`.editor.generating` 下 Placeholder `::before` `content:none`）；验证：截图/`design:lint` 通过，空章生成中无「从这一章开始写……」与卡片重叠
  - 证据：全量 vitest 122 文件 1489 用例全绿；截图 `/tmp/an-gp-shots/1-首字前-等待呈现.png`（无框行内、无环）与 `2-首字后-环亮起.png`（环扣工具行＋正文区整列）——定位修正：`.editor-wrap{position:relative}`（首拍曾漂到页面上方，已修）

## 5. 测试与 e2e

- [x] 5.1 `client/backend/tests/**`：补阶段序列与准备段失败转 `error` 用例（组 3.1/3.2 的验证落点），并确认原有用例全绿
  - 证据：见 3.1/3.2（三例全在 `tests/test_prose_pipeline.py::TestGenerationPhases`）
- [x] 5.2 `client/frontend/src/__tests__/proseStream.test.ts`／`aiStreamError.test.ts`：补组 4.1/4.2 的用例（phase 渲染推进、首字退场、兜底单报）
  - 证据：见 4.1/4.2；(proseStream 复现链未改——本次未动流式写入管线)
- [x] 5.3 `client/frontend/e2e/prompt-pipeline.spec.ts`：生成链路由 mock 增 `phase` 事件，断言阶段卡片出现（当前步为「组装提示词」态）与首字到达后退场；既有「重新生成＝替换写」「中断与找回」两用例适配后全绿
  - 证据：隔离栈（an-gp，独立容器名/端口/数据目录）跑 `prompt-pipeline.spec.ts`＝**7 passed**；含等待呈现断言（gen-line 可见＋`.awaiting`＋`.generating` 缺席→首字后退场）与「截断＝自动失败收尾」改写（切流后 toast「未收到完成信号」＋徽章退场＋半截落库＋版本历史找回）

## 6. 门禁回归（实际输出回填本组）

- [x] 6.1 `client/frontend`: `npm run design:lint` → 记录实际输出结论
  - 证据：通过（存量统计照旧：29 个文件严格扫描；无新违例）
- [x] 6.2 `client/frontend`: `npm run design:check`（C端 parity，book 屏不在矩阵内；如截图受本改动影响需在 ADJUSTMENTS.md 已登记项内）→ 记录各场景像素差与结论
  - 证据：**7 passed / 1 failed**——唯一失败＝书架屏 quota **2.693%**（阈值 0.2%）＝既有存量红（书架屏光栅漂移，与本次无关：本 change 未触书架屏；其余场景全过）
- [x] 6.3 双端 `tsc --noEmit`（C端）／按 2.1 判定免 `design-cross` → 记录结论
  - 证据：`tsc --noEmit` 干净；按 2.1 判定免 `design-cross`（未触两端共享段）
- [x] 6.4 相关测试实跑：后端 `pytest`（write 相关）＋前端 `vitest`（proseStream/aiStreamError/NovelWorkspace）＋e2e（prompt-pipeline）→ 记录绿/红与红因归因
  - 证据：后端 `pytest -k write` 168 passed（CI 形态 129 passed/39 skip）；前端 `vitest run` 122 文件 **1489 passed**；e2e `prompt-pipeline.spec.ts` **7 passed**；`ruff check` passed
- [x] 6.5 手动链视觉留证：隔离栈（本仓＋mock AI 流）跑「有正文章重生成」与「空章首生成」，截三态（准备/组装/模型等待）＋首字后退场对照图，附路径
  - 证据：`/tmp/an-gp-shots/1-首字前-等待呈现.png`、`1b-等待呈现-局部.png`（局部：行内文案＋光标＋尾注）、`2-首字后-环亮起.png`；页面内可保持打开的流复刻两态（临时 spec 跑完即删）

## 7. change 收口

- [x] 7.1 `openspec validate c-prose-gen-phases` 通过；proposal/design/tasks 与本回填的实测结论一致（含 proposal 已声明的规范补丁：徽章承载位旧句修正）
  - 证据：`openspec validate` 通过（4/4 artifacts；spec delta 两处 Requirement：ADDED 生成阶段呈现（无框行内＋呼吸灯后置）／MODIFIED 现场保护（环＝编辑体＋无终态事件兜底））；实现与 design.md D5a/D5b/D6 口径一致（`.prose-body` 包裹层＋`onPhase`＋终态兜底）
- [ ] 7.2 提交与 PR：分支 `c-prose-gen-phases`（worktree `ai-novel-wt-genphases`）按仓规范提交；PR 描述含判据（组 6 输出）与截图
