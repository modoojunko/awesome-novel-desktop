## Context

C端 有 9 个带 AI 生成态的弹窗（见 proposal 弹层清单），busy 态此前只有转圈＋一句主文案，部分弹窗另有弱色副行（`.pick-busy .none`）。拆章（useChapterPlan token 守卫「busy 中关窗＝弃」）、三选一成卷（closePick＝cancelPending）、章剧情（usePlotDraw「关窗也换代」）三处关窗确实作废在途生成。相关主 spec 中只有 `chapter-plan-ai`（逐字钉 busy 文案）与 `design-system`（AI 出卡弹窗占位口径）涉及生成中文案。实现已于 2026-09-30 会话先行落在工作区，apply 阶段逐项核对＋回填原型登记。

## Goals / Non-Goals

- Goals：生成中的作家一眼看到「别关窗」；文案全弹窗一个句式；不动任何关闭行为与守卫。
- Non-Goals：不改 VolumePlanModal（关窗安全是其明示设计，见 Decisions D3）；不新增挽留弹窗/拦截；不动后端与提示词；不做 e2e 钉子（需隔离栈，留合流前按需）。

## Decisions

- **D1 一行式提示，位置在 busy 块内主行下方**：转圈主行保持原样（现有 vitest/e2e 断言不破），提示行独立成行、居中、11.5px faint——与 CastReview 既有 `.none` 副行同族。备选「并进主文案一句」被否：会破 `StoryArcForm.test` 的 `getByText("AI 正在生成…")` 精确匹配，且主文案各弹窗不同、钉不住统一句式。
- **D2 文案按实义动词分四档，后缀统一**：创作类「AI 创作中，请勿关闭弹窗」；盘点「AI 盘点中，请勿关闭弹窗」；检查「AI 检查中，请勿关闭弹窗」；推演「AI 推演中，请勿关闭弹窗」。备选全用「创作中」被否：检测/推演不是创作，错位文案比不提示更糟。
- **D3 VolumePlanModal 例外**：其页脚现成文案「生成在后台跑，关掉它也不影响」＋代码注释「关弹窗不中断（完成后中栏自动回填）」是已拍板口径；加「请勿关闭」即同屏自相矛盾。用户已知情报备，若要一刀切须连该口径一起翻案。
- **D4 首跑与重抽同提示**：两者共用同一 busy 态分支，分态写两套文案零收益；关窗丢结果的风险两态一致。
- **D5 CSS 词汇**：`book.css` 新增 `.no-close{font-size:11.5px;color:var(--faint)}` 与 `.pick-busy.col`（纵排变体，附带 `.col .none` 12px faint 层级）；CastReview 不加 `.col`（`.cast-review .pick-busy` 已是 flex-column）。ContrastPreviewModal 是行内样式风格文件，就地用 `flexWrap+flexBasis:100%` 副行，不引外部类。`.no-close` 命名避开了语气胶囊族（info/ok/warn/err 不受影响，无第四形态）。
- **D6 spec 落点**：只在钉了生成中文案的 `chapter-plan-ai` 与统一占位口径的 `design-system` 开 MODIFIED delta；其余能力 spec 未钉生成中文案，不开 delta（避免为文案行扩 Requirement 面）。

## Risks / Trade-offs

- [「请勿关闭」与「允许关闭」并存显矛盾] → 两处 delta 均括注「仅文案提醒，不改可关闭口径」；chapter-plan-ai 的「SHALL 可取消」原句原样保留。
- [共享检出并行会话] → 本 change 只碰上列 9 组件＋book.css＋2 测试＋2 spec delta；CharacterManager、archive-reconcile、c-lore-reconcile-guardrails 等他人改动不纳入本 change 提交。
- [parity/design:check] → busy 态瞬态不入 parity 页集，`npm run design:check` 照常跑一遍确认零新红。

## Migration Plan

纯前端文案＋局部样式，无数据迁移；回滚＝revert 对应 commit 即可。演示栈验证需重建 client 镜像（改前端必须重建，既有教训）。

## Open Questions

（无——VolumePlanModal 例外已在 proposal 报备，用户未要求翻案。）
