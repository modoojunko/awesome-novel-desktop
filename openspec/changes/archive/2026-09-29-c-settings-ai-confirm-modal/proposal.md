# 提案：设定域右栏 AI 交互统一弹窗确认制

## Why

设定域 7 个面板的右栏 AI 能力行（共 29 行），生成结果的呈现分三种不一致的形态：格下内嵌结果区（AiSink）、卡内预览块（角色）、无预览直写（文风润色/例句提炼）。其中文风「润色文字文风」「例句提炼」两行生成结果不经作者过目直接覆盖已填内容，与全产品「只加工你写的、确认才写入」的承诺相悖；内嵌结果区则挤在表单流里，与写作域已成熟的弹窗出卡确认制（AI 检测、精盘、抽卡）交互割裂。统一为「点击 → 弹窗出卡 → 作家确认」，与写作域对齐。

## What Changes

- 右栏 AI 能力行点击后，生成结果一律进**弹窗出卡**（复用 `design/Modal.tsx` 弹窗壳，C端 局部）；弹窗内确认才写回，关闭即弃、不落库。
- **非右栏的 AI 出稿口同批统一**：主线第三问行内「AI 帮我填」（tone）、世界格头快捷钮（与右栏共用入口）、世界体检报告内「AI 补」快捷链——结果一律进同一弹窗，不再有内嵌结果区这条第三形态。
- **生成中关闭的保护口径**：生成中允许关闭弹窗，但最近一次结果缓存在面板 state；重开同一能力行直接展示缓存（不再发请求、不重复计 usage），「换一个」才重新生成（沿 CastReviewModal「误关重开还是同一批」先例）。
- 四种卡形（复用写作域既有弹窗元素与设定域既有行词汇；零新增视觉词汇**定义**——`.chk-*` 等既有词汇从 `.settings-v .ai-sink` 作用域**重挂**到弹窗卡体容器，因 Modal portal 到 body 后原作用域不命中）：
  - **文本卡**：复活零引用死代码 `AISuggestionModal.tsx` 为底座——内容＋「换一个」＋「接受这个」；采纳沿用既有回执一步撤销（ChangeReceipt）。
  - **体检报告卡**：复用 `AiCheckModal` 形状——打开即跑、findings 列表、「关闭」「重新检查」，无采纳键。
  - **候选勾选卡**：题材多看点、伏笔起草 3 候选——勾选后「采纳」（沿 PickCardsModal/CastReviewModal 先例）。
  - **结构化卡**：世界铁律 kv/势力行、角色逐格 diff、主线结局三问、文风三区——现有内嵌渲染搬进弹窗壳，确认键按域为「采纳 · 覆盖/合并/写入」。
- 文风「润色文字文风」「例句提炼」**从无预览直写改为弹窗预览确认**（行为变更；creation-flow spec 原文「采纳·覆盖才写回」与实现不符，本次把实现对齐 spec 承诺）。
- 世界体检报告区「AI 补」快捷链（checkFixAi）同批改走弹窗。
- **移除**：内嵌结果区的「最近 5 次」生成历史切换条（弹窗内「换一个」即可重生成，写作域弹窗先例均无历史切换；补偿＝文本卡显示已生成版数「第 N 版」，「换一个」期间旧版保持可读可采纳，新版到达后替换）；`AiSink.tsx` 组件退役（检查行渲染沿各域既有 `chk-*`/`chk-row` 词汇重挂弹窗卡体容器）。
- **不动**：文风蒸馏画像确认卡（已是确认制、三步流中段，保持面板内视图）；后端生成/体检端点全部零改动；右栏卡片布局与免费锁定门控不动。
- **BREAKING（测试面）**：依赖 `.ai-sink` 内嵌结果区与格下采纳键的单测（18 文件）与 e2e（11 spec）选择器全量改写为弹窗口径。

## Capabilities

### New Capabilities

（无——统一弹窗协议按 c-ai-rail-shared 先例归口 design-system 组件词汇，不另立新 capability。）

### Modified Capabilities

- `design-system`：AI 结果区组件词汇条款（`.ai-sink` 内嵌形态→弹窗出卡词汇）；角色页「结果区 SHALL 落在 `.ai-sink` 内」条款同步改。
- `intro-genre-settings`：简介三行（体检/补缺失/润色）结果落格下内嵌→弹窗确认；体检弹只读报告卡。
- `world-settings`：五行生成＋体检「结果落对应格下方＋最近 5 次可切回」→弹窗确认；历史切条退役；体检报告与「AI 补」快捷链弹窗化。
- `storyline-settings`：主线三行（起草/结局校准/体检）→弹窗确认。
- `character-settings`：角色五行（从简介立主角/人设/档案/认知/体检）卡内预览块→弹窗确认；逐格只补空格复查逻辑保留。
- `foreshadow-settings`：伏笔四行→弹窗确认；起草候选为勾选卡形态。
- `creation-flow`：设定视图三段式条款中文风四行「答案落卡底结果区或对应字段，采纳·覆盖才写回」→统一弹窗确认口径；补齐润色/例句的确认步骤。

## Impact

- **代码**（仅 C端 前端）：7 个表单的 `runAi`（简介在 SettingsView 内嵌 IntroPanel；题材/世界/主线/人物/伏笔/文风各自表单）结果改推弹窗；`AISuggestionModal.tsx` 复活并扩展四卡形；`AiSink.tsx` 退役；`AiWriterAssistant.tsx` 行文案与 footNote 改口；世界 `WorldSettingPanel` sinkZone/checkFixAi 改造；文风 `StyleSettingForm` polish/fewshot 加预览。后端 `client/backend` 零改动。
- **原型**：`docs/design-c/prototypes/` 中 character-settings.html（19 处）、foreshadow-settings.html（18 处）、genre-signup.html（12 处）三个 parity 原型＋style-settings.html（8 处，未入 parity）的 ai-sink 演示块同批调整为弹窗触发态（book.html 实测零命中，不在清单）；ADJUSTMENTS.md 逐条登记（4 条）。
- **测试**：单测约 8 个文件真正命中设定域结果区选择器（AiSink.test、GenreSettingForm.test、WorldSettingPanel.test、StoryArcForm.test、SettingsView.introHandle.test、CharacterManager.bootstrap.test、StyleSettingForm 相关、AiWriterAssistant.test）；e2e 11 spec（ai-assist、world-settings、story-arc、foreshadow-ai、genre-ai-settings、style-quant、settings-forms、plot、reconcile、prompt-pipeline、ui-spec-parity），改写分三类：**删除**历史切回用例（story-arc/genre-ai-settings/world-settings 的「最近 5 次」段）、**重写**弹窗断言、**重写** parity 样式断言（ui-spec-parity 的 evaluate 量底色/几何断言深绑 `.settings-v .ai-sink` 作用域）。

## Design Impact

- **受影响端**：仅 C端（S端 无对应界面）。
- **受影响屏/弹层**：设定视图（工作台「设定」域）右栏 7 面板；新增弹层＝设定视图内「AI 出卡确认弹窗」（一个壳、四种卡形），全部复用 `design/Modal.tsx` 与写作域弹窗词汇（`ck-list`、勾选卡、预填表单卡）。
- **对象状态**（对照状态语言总表）：弹窗生成中＝prog 语气行；生成失败＝warn 提示＋「重新生成」可点击出口；确认写回＝既有回执一步撤销（ChangeReceipt）；**无新增状态档位、无新胶囊形态**。
- **是否触碰两端共享段**：否——不动 `base.css` 令牌与共享组件类；弹窗壳与卡内词汇均为 C端 局部类。
- **是否需要原型先行**：需要**原型同批修改**（3 个 parity 原型＋style-settings 的 ai-sink 演示块因实现退役而须调整并登记 ADJUSTMENTS.md），但**不新做 HTML 原型设计**——不新增视觉词汇定义，弹窗卡形逐一对齐写作域既有实现（AiCheckModal / CastReviewModal / PickCardsModal）；既有 `chk-*` 等行词汇从 `.settings-v .ai-sink` 作用域重挂到弹窗卡体容器（词汇不变、选择器前缀变）；弹窗触发态不进 parity 截图（沿「未动原型、只在应用侧扩展的不进 parity 截图」先例）。
- **设计工件产出方**：实现侧自查（对照写作域弹窗实现与 design-language §6 组件词汇），无需设计侧会话。
- **判定依据**：不触共享段、不新增令牌/字号档位/胶囊形态；design:lint 校验既有词汇即可，design:check 需在原型同批改后回归全绿。
