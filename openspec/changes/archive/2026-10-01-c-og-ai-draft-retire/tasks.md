## 1. 原型先行（硬性流程）

- [x] 1.1 `docs/design-c/prototypes/book.html` 右栏 `railChapter` 卡撤「AI 起草」行（`.ra-step` 一枚）；ADJUSTMENTS.md 追加登记小节（撤行原因＝与拆章/补全重复，零新视觉词汇）。验证：grep book.html 无「AI 起草」行、ADJUSTMENTS 有本 change 小节。（完成证据：book.html 仅存 changelog 历史句「提升章纲 AI 起草的稳定性」，rail 行已撤；ADJUSTMENTS.md 已追加「章纲右栏撤『AI 起草』行」小节）

## 2. 前端退役

- [x] 2.1 `AiAssistPanel.tsx`：撤 og 页签 `draft` 行、props `canAiDraft/aiDrafting/onAiDraft`、running 键 `draft`；注释行数口径「五行」改「四行」。验证：grep 无 `og-ai-draft`/`onAiDraft`。（完成证据：residual grep 仅剩设置域同名「AI 起草」（无关功能）与操作页签脚注改写后的非起草表述）
- [x] 2.2 `Rail.tsx`：撤 `RailChapterData` 三字段与透传，渲染条件撤 `d.onAiDraft`。验证：grep 无 `onAiDraft`。
- [x] 2.3 `ChapterWorkspace.tsx`：撤 `draftOutline` import、`aiDrafting` state、`handleAiDraft`、railData 三字段与依赖项；两处注释的起草措辞同步改写。验证：tsc 无未用符号报错。
- [x] 2.4 `chapterForm.ts` 撤 `ogHasDraftContent`；`lib/ai.ts` 撤 `draftOutline`。验证：grep 两函数零引用。

## 3. 后端退役

- [x] 3.1 `chapters/ai_draft.py`：撤 `ai_draft_outline` 端点与 `_sanitize_draft/_arc_markdown/_existing_outline_markdown/_clamp_word_target/_str_list/_PAYOFF_KINDS` 及随之未用的 import；模块 docstring 改为「章纲缺项补全」。验证：`python -c "import chapters.ai_draft"` 干净、fill-gaps 端点仍在（pytest fill-gaps 用例全绿佐证）。
- [x] 3.2 删 `prompts/outline_draft.prompt`；删 `tests/test_outline_ai_draft.py`；`tests/test_story_arc.py` 撤 `test_outline_ai_material_uses_mirror`。验证：grep 后端无 `outline_draft`（除模块 docstring 的退役注记与 token_log 历史语义）。

## 4. 测试更新

- [x] 4.1 `AiAssistPanel.test.tsx`：撤 onAiDraft/canAiDraft/aiDrafting 与「AI 起草」点击断言。验证：该文件 vitest 绿（9/9）。
- [x] 4.2 `aiAssistPanel.plotTool.test.tsx` / `castReviewRail.test.tsx` / `rewriteFlow.test.tsx`：撤三 props；castReviewRail「其余五行」→「其余四行」、需 PRO 计数 5→4、「PRO：五行可点」→四行。验证：三文件 vitest 绿。
- [x] 4.3 `chapterForm.plotItems.test.ts`：撤 `ogHasDraftContent` import 与用例块；`chapterForm.promptGrid.test.ts`「AI 起草回填映射」改框为 ogToForm 通用合并语义（覆盖语义仍由章节装载链承重，保留覆盖）。验证：两文件 vitest 绿。
- [x] 4.4 删 `e2e/outline-ai-draft.spec.ts`（整删，桩只服务本功能）。验证：grep e2e 无该文件引用；其余 e2e 的「AI 起草」字样为设置域功能与 changelog 历史句，不涉本改。

## 5. 回归

- [x] 5.1 C端 `npx tsc --noEmit` 干净（exit 0）；全量 vitest 1058 绿＋3 失败＝`CharacterManager.adopt` 存量红（main 检出同文件同红，[[og-hooks-projection-shipped]] 已登记）。
- [x] 5.2 后端 pytest 全量：1735 绿＋1 失败＝`test_plot_prompt` plot golden 存量红（main 检出同红，[[retire-local-file-storage-pr623]] 已登记）；fill-gaps 链路（test_ai_assist_checks/test_plot_ai）全绿。
- [x] 5.3 `npm run design:lint`：本改零新增违规；唯一 ✗＝`model-config.html:1 emoji`，为已提交版本的存量（c-zhuque-quota-ledger 在主检出的未提交工作已修该字样，见 ADJUSTMENTS 2026-10-01 小节）。`openspec validate --strict` 通过。
- [x] 5.4 门禁实跑记录：design:check book 屏——本检出 11.605% / main 检出（client 未改）同法 11.395%，同为整页竖向级联差异（更新通知横幅漂移类），判存量红非本改引入；隔离 e2e 全量未跑（合流前按 [[e2e-isolated-stack-config-path]] 配方补跑，本改删的是自含 spec，无新增 e2e 面）。
