# c-ai-modal-confirm — AI 结果一律出卡过目、采纳才落框（存量违规整改）

## Why

用户 2026-10-28 立规（看了 c-intro-ai-draft 出卡交互后）：**凡是 AI 功能一律弹窗——作家过目生成结果、点采纳才写入输入框；禁止 AI 结果不经过目直接落框**。全量盘点（前端写入路径逐一查证）发现设定七面板与章纲侧大部分能力已合规，但存量有 4 处明确违规＋1 处边界：

1. 章纲缺项补全：`fillOutlineGaps` 产物 `setOgForm` 直写章纲表单（无弹窗、无撤销）；
2. 卷纲 AI 铺空缺（手写路）：完成态只有一行摘要，「回填」后全文逐段直写表单，且**生成中关掉规划台、后台完成后自动回填**（关窗即写入，连回填点击都可绕过）；
3. （边界，本次不动）卷纲抽卡「确认成卷」：确认的是四问摘要卡，expand 产物未过目即写库——有确认步、付费链路刚拍板——**用户 2026-10-28 拍板：不动**；
4. 封面画面描述提取：`extractCoverScene` 结果直接 `setCoverPrompt` 填输入框；
5. 头像外貌草稿：`extractAvatarLook` 结果直接 `setAvatarPrompt` 填输入框。

**豁免**（不属「结果写输入框」）：正文流式写作/一键续写＝写作面本体（生成前有确认弹窗、SSE 逐字上屏、版本历史兜底），改弹窗审阅会打断核心写作流——按豁免处理，boss 如另有拍板再改。

## What Changes

- **章纲缺项补全出卡化**：产物进「章纲缺项 · AI 补全稿」出卡（逐字段展示，只补空缺格），「采纳 · 填入章纲」才写表单并进编辑态；关闭即弃、「换一个」重掷。
- **卷纲铺空缺出卡化**：完成态在规划台内展示 AI 产物全文（卷名/概要/冲突/反派类型/反派主线/卷末去向/建议章数＋伏笔建议＋checks）；「采纳 · 回填卷纲」才写表单；**移除「生成中关掉→后台完成自动回填」臂**，改为完成后 toast 提醒「打开规划台过目后采纳」，直接关闭＝不采纳、什么都不写。
- **封面/头像提取出卡化**：提取/起草结果进「AI 起草稿」出卡（展示全文），「采纳 · 填入描述」才填输入框；关闭即弃、「换一个」重掷（重掷走同卡，不重复弹层）。
- 行为契约落 openspec：`outline-ai-draft` / `volume-plan-ai` / `cover-avatar` 三 capability 的对应 Requirement MODIFIED。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `specs/outline-ai-draft/spec.md`: fill-gaps 产物改「出卡过目、采纳才回填表单」；场景同步。
- `specs/volume-plan-ai/spec.md`: 手写路完成态出全文过目；回填语义改「采纳」；删除后台完成自动回填臂（改提醒）。
- `specs/cover-avatar/spec.md`: 封面提取/头像起草结果改「出卡过目、采纳才填输入框」；场景同步。

## Impact

- 前端：`ImageWorkshopModal.tsx`（extractDraft 出卡＋采纳/换一个）、`ChapterWorkspace.tsx`（gapsDraft 出卡＋采纳，runFillGaps 与写入分离）、`VolumePlanModal.tsx`（完成态全文过目＋文案）、`NovelWorkspace.tsx`（删自动回填 effect，改提醒 toast）。
- 测试：imageWorkshop 两用例改钉出卡流（关闭即弃＋采纳写入）；chapterWorkspace.plotFlow 新增 2 例（采纳写入进编辑态/关闭即弃）；volumePlan 既有 desk-done 断言兼容。
- 不动后端；不动正文流式写作；不动卷纲抽卡确认成卷（#3 边界，留拍板）。
