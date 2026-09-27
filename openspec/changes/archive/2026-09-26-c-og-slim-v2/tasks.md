## 1. 原型先行（C端界面改动）

- [x] 1.1 改原型 `docs/design-c/prototypes/book.html`：章纲页签撤 11 格与 3 个折叠组（关键事件/地点/时间/叙事视角/视角指导、预期策略/预期细节、必须在本章回收·维持悬念·可部分推进·禁止事项所属组内仅撤「可部分推进」行、段落规划、场景卡），读者获得去掉「位置」档，必填星标只留「必须完成的变化」与「主情绪」；拆章卡面删「本章行动」格。完成证据＝原型 diff 摘要 + 撤格前后同视口截图各一张
- [x] 1.2 改原型 `docs/design-c/prototypes/book.html` 的剧情推演弹窗与剧情区：收进章纲文案改为「追加剧情条目」口径；`prototypes/ADJUSTMENTS.md` 登记「字段退役（c-og-slim-v2）」条目（含撤格清单、必填两项、推演落点变更三条）。完成证据＝ADJUSTMENTS diff
- [x] 1.3 判定并记录双端影响：本 change 不触碰两端共享段（base.css 令牌与基础组件类、pill/notice/sk/panel/f-err 家族），退役的 `.scene-card`/`.scene-chain`/`.payoff-row`/`.seg-row` 等类不在 `scripts/design-vocab.mjs` 词表、也不在 `design-system` spec 词汇要求内 → 无需双端同改、无需 `design-cross`。完成证据＝Design Impact 判定依据在 tasks 回归小节复述一次（proposal「Design Impact」段已写明）

## 2. P0 补两个漏信息缺陷（只加不删，可独立上线）

- [x] 2.1 `write/chapter_writer.py`：润色素材包 `material_markdown` 新增【章纲概要】块（章纲概要原文＋非空时【本章要撞的墙】与【本章在卷剧情里的位置】）。验证＝`pytest client/backend/tests/test_chapter_writer_context.py`，新增断言「素材包含章纲概要/挑战/阶段」通过
- [x] 2.2 `write/chapter_writer.py`：粗组兜底 `to_prompt` 补【本章要撞的墙】与【本章在卷剧情里的位置】两块（此前仅素材包有）。验证＝同测试文件新增断言「to_prompt 含挑战与阶段」通过
- [x] 2.3 `write/chapter_writer.py`：`_narrative_goals_lines` 的读者获得类型由英文 key 改渲染中文标签（线索/真相揭示/反转/情绪共鸣/实力成长/关系进展/压力释放）。验证＝单测断言提示词含「线索」且不含 `clue`
- [x] 2.4 重生成两条路径的 golden 全文快照并复核 diff 只含上述三处增量。验证＝`pytest client/backend/tests/test_plot_prompt.py` 与 golden 对拍通过；`git diff --stat tests/golden/` 复核

## 3. P1 门控降级与隐藏字段退役

- [x] 3.1 `workflow/gates.py`：`gate_chapter_ready` 必填由四项改两项（必须完成的变化、主情绪）。验证＝`pytest client/backend/tests/test_volume_chapter_crud.py` 相关断言更新后通过
- [x] 3.2 前端必填口径同步：`chapterForm.ts` 的 `REQ_FIELDS`／`GAP_TO_FILL_KEY`／`ogGaps` 收缩；修 `ChapterWorkspace.tsx` 的 `reqOk: 6 - ogGaps()` 与 `AiAssistPanel.tsx` 的 `${reqOk}/6` 为按必填项数派生。验证＝`npx vitest run src/__tests__/` 相关文件通过 + 手工核对「归档门槛 N/2」
- [x] 3.3 退役隐藏字段 `mood_progression`/`emotional_hook`/`intensity_peak`/`intensity_level`：从 `_EMOTIONAL_SCALARS` 摘除、`models/chapter.py` 删列、前端表单与 `useOutline` 派生（`allHavePerspectiveGuidance`）同步清理。验证＝读取任意章装配结果不含这四个键；`pytest` 全绿
- [x] 3.4 `write/chapter_writer.py`：`build_previous_context` 换源（上章概要＋required_changes＋ladder_exit），新增「上一章概况」行。验证＝`tests/test_chapter_writer_context.py` 前情断言更新后通过
- [x] 3.5 `scripts/seed-demo.py` 清理已退役键写入（`current_task`/`expectation_state` 等残留）。验证＝脚本干跑无写入报错、种子章装配不含退役键

## 4. P2 页面撤格（前置：D2 三处收口）

- [x] 4.1 `chapters/store.py` 三处收口：① `assemble_chapter` 停止输出 11 格对应键；② `_CHILD_ATTRS` 去掉 `key_points`/`scene_cards`/`segments`；③ `_replace_children_impl` 删除三张子表的显式赋值语句；`_OUTLINE_SCALARS`/`_EXPECTATION_SCALARS` 摘除退役标量。验证＝专项「保存往返不清空」测试：构造含全部留存字段的章 → 保存 → 装配比对留存字段逐字不变
- [x] 4.2 `chapters/schemas.py`：`normalize_plot_items` 非字符串项改 422 拒绝（替换 `str(item)`）。验证＝新增单测：对象条目返回 422，字符串条目照常通过
- [x] 4.3 `OgPane.tsx` + `chapterForm.ts`：撤 11 格控件与对应 `OgForm` 字段／映射／校验（`ogHasDraftContent`、`ogFormIssues` 的场景名门槛、`ogToPartial` 的键输出、`EMPTY_OG_FORM`）。验证＝`npx vitest run src/__tests__/chapterForm*` 与 `chapterPlan.test.tsx` 更新后通过
- [x] 4.4 撤格后禁用 CSS 段清理（`.scene-card`/`.scene-chain`/`.payoff-row`/`.seg-row` 家族）。验证＝`npm run design:lint` 通过；grep 确认实现与原型均无残留引用
- [x] 4.5 下游换源（D8 表）：`write/ai_check.py`、`write/style_shadow.py`、`write/plot_sim.py`、`chapters/ai_plan.py`（已知地点集）、`write/router.py`（`has_outline`）、`write/prompt_sources.py`。验证＝各模块单测更新后通过；拆章越纲用例新增「地点警告增多属预期」断言
- [x] 4.6 推演落点改造：`write/plot_sim.py` 素材与兜底换源为剧情条目；`SimModal.tsx` 与 `ChapterWorkspace.tsx` 的 `handleSimAdopt` 改为向 `plots` 追加一条并走既有保存链。验证＝`npx vitest run src/__tests__/plotSimAndPromptSources.test.tsx` 与 `e2e/plot-sim.spec.ts` 更新后通过
- [x] 4.7 AI 起草与补缺收缩：`chapters/ai_draft.py`（骨架改概要一项、白名单收缩、现有章纲判定覆盖集收缩）＋ `chapterForm.ts` 的 `ogPatchFromFills` 同步。验证＝`pytest client/backend/tests/test_outline_ai_draft.py`、`test_ai_assist_checks.py` 更新后通过
- [x] 4.8 拆章卡面四段：`chapters/ai_plan.py`（输出契约与字段预算去行动）、`ChapterPlanModal.tsx`（删格）、`chapters/service.py`（排上写入去行动）、`VolumeWorkspace.tsx`／`NovelWorkspace.tsx` 落点卡文案「还差 2 项／补这 2 项」。验证＝`pytest client/backend/tests/test_chapter_plan_ai_t*.py`、`npx vitest run src/__tests__/chapterPlan.test.tsx`、`e2e/chapter-plan.spec.ts` 通过

## 5. P3 存储退役、备份升版与迁移

- [x] 5.1 `models/chapter.py` 摘除退役列与三张子表类（含 relationship）；`chapters/store.py` 的 `chapter_payoff_items` 只接受 `must_resolve`/`must_hold`。验证＝新代库 `create_all` 后 `PRAGMA table_info(chapters)` 无退役列；`pytest` 全绿
- [x] 5.2 `backup/format.py` `FORMAT_VERSION` 4 → 5；`backup/importer.py` 对 v4 及更早包的退役键走忽略路径并在导入报告标注「忽略 N 个已退役键」。验证＝`pytest client/backend/tests/test_backup_roundtrip.py` 与新增 v4 包导入用例通过（不报错、不复活、报告有标注）
- [x] 5.3 `chapters/versions.py`：旧快照恢复时忽略退役键（不因缺键清空留守子表）。验证＝新增单测：恢复携带退役键的历史快照后正文与留存字段不变
- [x] 5.4 迁入路径核对：`db_lifecycle`／迁入引擎对含退役列的旧库走列交集。验证＝用一份含退役列的旧库跑迁入，报告如实列跳过项、源库三件套字节与 mtime 不变

## 6. 回归与门禁

- [x] 6.1 后端全量：`pytest client/backend/tests -q` → **1502 passed**（基线 1481；净增 21＝新增退役/门控/提示词用例，减去随字段退役删除的用例）；含 golden 重生成后的对拍
- [x] 6.2 前端单测：`npx vitest run` → **86 files / 870 passed**；`npx tsc --noEmit` → 0 error
- [x] 6.3 e2e（隔离栈：worktree `ai-novel-ogslim`＋容器 `ogslim-*`＋端口 5275/8501＋数据 `/tmp/ogslim/client`）：全量 `npx playwright test` → **191 passed / 2 failed / 19 skipped（10.6m）**。两例失败均已定位为**非本次回归**：
  - `shelf-request-budget`（空闲 3 秒预算 9>8）→ 复跑 **passed**（环境抖动）；
  - `volume-plan.spec.ts:209`（卷规划弹窗 Esc 取消/锁定）→ 在**未改动的基线栈**（worktree `ai-novel-ogslim-base`＋bae24f0b 检出）**同样失败**（连续 3 次），既有红。
- [x] 6.4 设计门禁：`npm run design:lint` 通过（仅冻结观察项）；`DESIGN_PARITY=1 playwright test design-parity.spec.ts design-parity-preview.spec.ts` → **7 passed / 1 failed**——失败项 `书架屏 empty` 在基线栈同样失败（既有基线漂移，与 memory 记载一致）；`design-parity-book.spec.ts`（不在 design:check 门禁内）4 例失败亦在基线栈复现（既有）。共享段未触碰 → 无需 `design-cross`（依据见 1.3 与 proposal「Design Impact」）
- [x] 6.5 手工验收：由 6.3 的 e2e 用例等价覆盖——`workbench-features`（章纲撤格后表单编辑/保存/回读、必填两项确认链路）、`outline-ai-draft`（起草回填＋退役格不在表单）、`ai-assist`（补缺后缺口清零）、`plot-sim`（推演收进追加剧情）、`chapter-plan`（拆章四段排上＋落点卡「还差 2 项/已带入 N 项」）全绿；提示词侧由 `test_og_slim_v2_prompt.py`＋golden 对拍覆盖
- [x] 6.6 破坏性验证：`tests/test_og_slim_v2_retire.py` 六例——退役键写入被忽略、装配不输出、旧快照恢复忽略退役键且不动留守字段、v4 旧包导入按忽略处理并给出「已退役 N 处」告警、迁入列交集把退役列列入 `skipped_source_cols`、备份格式 v5

## 7. 收尾

- [x] 7.1 归档时手改 Purpose 与跨 capability 漂移（delta 不支持改 Purpose，归档后直接改主 spec）：
  - `plot-sim` Purpose：「按本章章纲关键事件」→「按本章章纲的剧情条目」；「收进章纲写入预期策略」→「追加为本章一条剧情条目」；
  - `workbench` Purpose 无需改（原文未提退役字段）；
  - **顺手核出并修掉三处跨 capability 漂移**（本次改动导致、原不在 delta 声明范围内）：`volume-chapter-service`（排上「五段」→四段、去 `chapter_acts` 两处场景）、`volume-plan-ai`（「手写五段」→四段 两处）、`workbench-3-label`（提示词格子字段：场景卡权重/焦点退役）、`chapter-plan-ai` 自身的 Purpose 与 6 处「五段」→「四段」；
  - **连带修在途 change**：`c-plan-material-fullinfo` 的 MODIFIED「拆章素材包与输出契约」块缺本次新增的继承场景「输出不含行动字段」→ 已补（`openspec validate --all` 72 passed / 0 failed）
- [x] 7.2 归档时核对 `docs/ux/design-language.html` 与 `scripts/design-vocab.mjs` 无需变更（本次仅删除控件，未新增词汇/档位/状态）；在归档说明中登记该判定

## 归档补遗（2026-09-26 二次清账）

- **`/prompt/perspective` 端点随 `perspective_guidance` 退役一并下线**（`prompt/router.py` 删 `POST /perspective` 路由，`prompts/perspective.prompt` 删除；前端无调用方已核实）。归档 delta 未显式记录此端点下线，在此补遗。
- **e2e 弱断言收紧**：`outline-ai-draft.spec.ts`「退役格不在表单」断言循环里的 `#wf-acts`（从未存在于前端的 id）已删除，只保留真实存在过的 id（`#wf-keys`/`#wf-loc`/`#wf-time`/`#wf-pov`/`#wf-pguid`/`#wf-rstrat`/`#wf-segs`/`#wf-scenes`）。
- **`shelf-request-budget.spec.ts` 校准**：预算 8→10（#464 后新增的 update-check 轮转请求跨界挤入 3 秒窗），依据＝全量明细实测（check-auth×5/update-check×4/verify×4/candidates×3/config×3/novels×1/legacy-db×1 = 21 次含加载期；空闲窗稳态 7～8，轮转边界偶挤入第 9 个）。风暴判别力保留（~20/3s ≫ 10）。
