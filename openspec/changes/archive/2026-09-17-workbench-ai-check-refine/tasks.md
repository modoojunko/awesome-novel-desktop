## 1. 后端——六类案头检查（ai-check）

- [x] 1.1 新增 `write/ai_check.py`：六类枚举与指令表、素材装配（章纲/正文/卷纲/关系真表/伏笔台账/文风基线）、`_parse_findings`（title+detail 均非空、≤8 条、非 JSON 回空）；验证：`pytest tests/test_ai_assist_checks.py -k AiCheck` 全绿
- [x] 1.2 端点 `POST /api/novels/{pid}/chapters/{ref}/ai-check {kind}`：未知类别 400、AI＋模型双门控、超时/错误 502 且失败留痕；验证：同测试文件 403/400/502 三例通过
- [x] 1.3 `main.py` 挂路由（`include_router(ai_check_router)`）；验证：`python -c "import main"` 且 `ruff check .` 无 F401/F821

## 2. 后端——章纲缺项补全（fill-gaps）

- [x] 2.1 `chapters/ai_draft.py`：`_FILLABLE_KEYS` 白名单（与前端表单同口径含 `current_task/state/strategy/changes/mood/segments`）、`_sanitize_fills`（行列表去空、segments 结构化＋字数钳 100-4000、越界键丢弃）、`POST /outline/fill-gaps`；验证：`pytest tests/test_ai_assist_checks.py -k FillGaps` 六例（含结构断言）全绿
- [x] 2.2 记账 `outline_fill_gaps`（记账先于解析）与 `_fail`；验证：测试断言 token_log 中出现两条 operation
- [x] 2.3 提示词模板 `prompts/outline_fill_gaps.prompt`（缺失字段清单＋素材＋只输出 JSON 示例含 state）；验证：测试断言缺口清单过滤后进 system

## 3. 后端——提示词精修（refine）

- [x] 3.1 `write/router.py`：`_REFINE_MODES`（negative/concise）＋ `POST /write/prompt/refine`（未知模式 400、未传基底走 `build_chapter_context` 组装稿、空稿 409、空结果 502、`strip_code_fences`）；验证：`pytest tests/test_ai_assist_checks.py -k PromptRefine` 五例全绿
- [x] 3.2 `prompts/prompt_refine.prompt`（保结构/不删红线/不改作者确认事实）；验证：测试断言 system 含模式指令与基底稿
- [x] 3.3 记账 `prompt_refine_{mode}` / `_fail` 且记真实模型（源码守卫）；验证：`pytest tests/test_ai_prompt_and_boundary.py` 全绿

## 4. 前端——面板接线与占位退役

- [x] 4.1 `lib/aiCheck.ts`：`runAiCheck`/`fillOutlineGaps`/`refinePrompt`/`saveWritePrompt` 与类别/模式文案表；验证：`vitest run src/__tests__/aiCheck.test.ts` 端点契约七例绿
- [x] 4.2 `AiCheckModal.tsx`／`RefinePromptModal.tsx`：打开即跑、finding 列表/空态/失败重试、精修预览＋采纳写回＋失败不关闭；验证：`vitest run src/__tests__/aiAssistModals.test.tsx` 七例绿
- [x] 4.3 `AiAssistPanel.tsx`：六类检测/两精修/补缺全部接线、补「还缺」清单、撤三重复动作、`Act.onClick` 改必填并删占位分支；验证：`vitest run src/__tests__/AiAssistPanel.test.tsx` 九例绿（含撤项不存在断言）
- [x] 4.4 `ChapterWorkspace.tsx`＋`Rail.tsx`＋`chapterForm.ts`：`ogPatchFromFills` 补丁映射、缺项清单上抛、两弹窗挂载、精修采纳后重挂提示词页签；验证：`vitest run src/__tests__/aiCheck.test.ts` 映射 round-trip 与 `npx tsc --noEmit` 0 错
- [x] 4.5 `design/book.css`：`.rail-list`（还缺清单）与 `.ck-*`（检查/精修弹窗）样式；验证：`npm run design:lint` 通过

## 5. 原型与登记

- [x] 5.1 `docs/design-c/prototypes/book.html` 的 `HOOK_TYPES` 换为标准标签（悬念/威胁/承诺/线索/关系伏笔/能力伏笔/情绪钩/选择钩/渴望钩，与后端单源一致）；`prototypes/ADJUSTMENTS.md` #27 补 ⑫（检测/精修落地＋三处撤项）；验证：`npm run design:lint` 过 ＋ `DESIGN_PARITY=1 playwright test e2e/design-parity.spec.ts` 19 绿

## 6. 端到端与全量回归

- [x] 6.1 新增 `e2e/ai-assist.spec.ts`（桩 AI：PRO 六类检查弹窗＋补缺表单回填＋精修采纳落库；免费档锁定且零请求）；验证：该 spec 2 例通过
- [x] 6.2 更新 `e2e/workbench-features.spec.ts` 右栏面板用例（动作全部落地、无「规划中」）；验证：该 spec 13 例通过
- [x] 6.3 全量回归：后端 `pytest tests`（仅存量 brand/entitlement 挂载基线红）、`vitest run` 全绿、`npx playwright test` 全绿、`npm run design:check` 全绿；验证：四类命令输出与本条一致
