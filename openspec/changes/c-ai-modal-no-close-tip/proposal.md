## Why

作家在 AI 弹窗（抽卡/生成）进行中看不出「还要多久、能不能关」，误关弹窗＝作废在途生成（拆章/三选一成卷/章剧情抽卡 busy 中关窗即弃该批），白烧 token 又误以为产品坏了。2026-09-30 拍板：所有 AI 助手弹窗在生成中，于弹窗中间明确提示作家「不要关闭弹窗，AI 创作中」。

## What Changes

- 9 个 AI 弹窗组件的 10 处生成中（busy/loading）状态，在转圈主文案下方统一加一行弱色提示：
  - 创作类＝「AI 创作中，请勿关闭弹窗」：拆章三方向、三选一成卷（换 3 套）、章剧情三版（换一批/再试一次）、人物方向抽卡（换一批/从头再来）、设定域 AI 出卡弹窗（首跑＋「换一个」在途）、正文改写对比；
  - 非创作类按实义动词＝「AI 盘点中，请勿关闭弹窗」（角色盘点）／「AI 检查中，请勿关闭弹窗」（AI 检测）／「AI 推演中，请勿关闭弹窗」（剧情推演）。
- 首次生成与「换几个」重抽共用同一 busy 态，提示两态都出现。
- `book.css` 新增 `.no-close` 提示行词汇与 `.pick-busy.col` 纵排变体（C端局部样式）。
- **例外（已报备）**：分卷规划台手写页生成盒（VolumePlanModal）不加提示——其设计口径是「生成在后台跑，关掉它也不影响」（页脚现成文案＋代码注释双钉），旁边再写「请勿关闭」会自相矛盾。
- 只作文案提醒：不改变任何弹窗的可关闭行为与守卫语义（代际守卫、关闭缓存口径、在途互斥全部原样）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plan-ai`：「AI 抽卡四态」的 ① 正在想态——该 spec 逐字钉了 busy 态文案，补「AI 创作中，请勿关闭弹窗」提示行。
- `design-system`：「AI 写作助手卡片与结果区组件词汇」的生成中占位口径——占位 SHALL 附「AI 创作中，请勿关闭弹窗」提示行（全 AI 弹窗统一；只作文案提醒，不改「生成中允许关闭」既有口径）。
- 其余弹窗（chapter-plot-items、chapter-cast-review、volume-plan-ai、world-settings、AI 检测、剧情推演、正文改写对比）的主 spec 均未钉生成中文案，无 requirement 变化，不加 delta。

## Impact

- 代码（全部 C端 `client/frontend`，后端零改动）：9 个组件文件＋`book.css`＋2 个 vitest 钉子（chapterPlan、plotDrawModal 的 busy 态断言补 toHaveTextContent）。
- 门禁：`tsc --noEmit` 干净；相关 vitest 全绿；不触两端共享段（`book.css` 为 C端局部）；不触 parity 基线（busy 态为瞬态，不入 parity 页集）。
- e2e：现有用例只断言 busy 容器可见（`split-busy`/`ai-card-loading`），不受影响；新文案的 e2e 钉子需隔离栈，留待合流前按需补。

## Design Impact

- 受影响端：仅 C端。
- 受影响弹层清单：拆章弹窗、三选一成卷弹窗、章剧情三版弹窗、角色盘点弹窗（盘点中＋抽卡中两处）、设定域 AI 出卡弹窗（loading＋「换一个」在途两处）、AI 检测弹窗、剧情推演弹窗、正文改写对比弹窗。
- 用到/新增的对象状态：全部为既有 busy/loading 态上加提示行，不新增状态档位、不新增胶囊/徽标形态、不引入第四种提示语气；`.no-close` 是纯文本说明行词汇（11.5px、faint），与 CastReview 既有 `.none` 副行同族。
- 是否触碰两端共享段：否（`book.css` 为 C端工作台局部样式）。
- 是否需要原型先行：需原型补登记——各弹窗原型的 busy 态补同一行提示，并在 ADJUSTMENTS.md 登记偏差原因；实现已先行落工作区（2026-09-30 会话），apply 阶段同批回填对齐。
- 设计工件由谁产出：实现侧自查（无新视觉词汇，复用既有弱色说明行先例）。
