## 1. 后端退役

- [x] 1.1 删 `POST /write/{chapter_ref}/prompt/polish` 端点（`write/router.py`，含 `load_layers` import）；`_advance_phase` docstring 去「重润色」示例。验证：`grep -rn "prompt/polish" client/backend` 只剩契约测试缺席钉；pytest 全量 **2045 passed, 1 skipped**
- [x] 1.2 删 `validate_polished_prompt`＋`_PLACEHOLDER_RE`（`write/chapter_writer.py`）；**保留** `_POLISH_ANCHORS`（仍服务存量行判型 `legacy_prompt_kind`/`should_refresh_stored_prompt`，注释改口径）与 `strip_code_fences`（plot_sim/ai_check/ai_draft 共用）。验证：`grep validate_polished_prompt` 后端零残留
- [x] 1.3 `git rm prompts/prompt_crafting.prompt`（本仓 `.prompt` 计数 58→57）。验证：git status 记录删除
- [x] 1.4 测试清理：删 `tests/test_write_prompt_polish.py`；`test_write_regressions.py`（major 2 润色用例＋major 3 条件锚整块＋`MINIMAL_VALID`/`_FakeChatClient` 死件）；`test_chapter_writer_context.py::test_validate_polished_prompt_tail_anchor`；`test_plot_prompt.py`（`TestPolishConditionalAnchor`＋import）；`test_story_state_consumption.py::test_polish_anchor_requires_story_state_title`；三处 docstring 记退役。验证：受影响五文件 **50 passed**
- [x] 1.5 契约测试：子路径清单去 `/prompt/polish`＋新增 `test_prompt_polish_route_retired` 缺席反向钉（照 `test_continue_route_retired` 形制）。验证：`test_write_routes_contract` 绿

## 2. 前端退役

- [x] 2.1 `AiModal`：撤「AI 润色」按钮＋`handlePolish`＋`polishing`/`polishError`＋「重试润色」块＋两段式引导文案；徽标改「本次组装/本章已存稿」（testid 不变）；组件头注释改单段式。验证：`grep 润色` 弹窗内零用户文案残留
- [x] 2.2 `lib/ai.ts` 删 `polishWritePrompt`（唯一消费方是 AiModal）。验证：`grep polishWritePrompt src` 零残留
- [x] 2.3 软提示改出口：`ChapterWorkspace`「可以重新润色/去重新润色」→「可以刷新提示词/去刷新提示词」；`NovelWorkspace`/`Rail`/`AiAssistPanel`/`ChapterWorkspace` 的 `promptSavedSignal` 注释去「润色」。验证：`chapterWorkspace.plotFlow` **13 passed**
- [x] 2.4 单测：`AiModal.twoStage.test.tsx` → `AiModal.test.tsx` 改名重写（删润色/重试用例；新增「本次组装且无润色入口」退役钉；徽标文案断言更新）。验证：`AiModal` **10 passed**
- [x] 2.5 e2e：`prompt-pipeline.spec.ts` 首用例改「组装→编辑→生成」＋退役面断言（无 `ai-polish`、无「AI 润色」文案、无「两段式」）＋编辑稿透传钉；`workbench-features.spec.ts` 存量稿徽标断言收紧为文案。验证：**本机未跑**（隔离栈未起；共享 demo 栈按约定不复用）——随 e2e 排程/常规环境复跑

## 3. 规格与登记

- [x] 3.1 spec deltas：`prompt-crafting`（MODIFIED「一章一个提示词（单轨）」「前情上下文来源升级」「故事状态（截至上章）块注入」＋REMOVED「AI 润色提示词（会员）」「提示词内容骨架」）、`chapter-plot-items`（MODIFIED 软提示）、`workbench`（MODIFIED 右栏 AI 助手面板＋章提示词查看与存稿）、`workbench-3-label`（MODIFIED 提示词单卡入口表述）
- [x] 3.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记 c-retire-prompt-polish 条（实现向原型回归：modalAi 本无润色按钮；徽标文案变更；无需改原型；**标准层待回填**：design-language A3/N7 与 audit S5 的两段式例实例交设计侧）
- [x] 3.3 `openspec validate c-retire-prompt-polish --strict` → **is valid**
- [x] 3.4 parity 基线影响判定：`design-parity.spec.ts` 只覆盖书架屏（list.html），不含 AiModal → **无需重录基线**；`design:check` 无新增红面

## 4. 回归

- [x] 4.1 后端：`pytest tests/ -q` → **2045 passed, 1 skipped**；`ruff check --extend-select F811,F821,F841 .` → **All checks passed**（本地 ruff 0.16.3，与 CI 钉版本一致）
- [x] 4.2 前端：`npx tsc --noEmit` 绿；受影响 vitest **23 passed**；`npx vitest run --coverage` 全量绿（覆盖率四项 100% 阈值未破）
- [x] 4.3 `npm run design:lint` 绿（31 文件严格扫描零新增；存量统计不阻断）
- [ ] 4.4 e2e 两 spec 实跑（`prompt-pipeline`/`workbench-features`）——本机未跑（隔离栈未起，共享 demo 栈按环境约定不复用）；留待常规 e2e 环境，proposal Impact 已记录

## 5. 登记不做（待拍板，不在本 change 范围）

- [ ] 5.1 `ChapterContext.material_markdown()` 生产消费方随润色链消失（现仅测试在用）——未随链删除：两路同源是 4 处 spec 条款＋golden 对拍维护的既有不变量，删除＝独立退役，建议单独立项（proposal Impact 已登记）
- [ ] 5.2 `should_refresh_stored_prompt` 三锚保护只覆盖历史润色行；新存量稿（作家存稿）若删掉「上章结尾」块会在弹窗被重组稿顶替——既有守卫口径差，未改行为，登记观察
- [ ] 5.3 标准层回填（设计侧）：`docs/ux/design-language.html` A3/N7 与 `docs/ux/audit.html` S5 的「两段式」例实例改单段式（ADJUSTMENTS.md 已登记，实现侧不擅改标准）
