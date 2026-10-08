# c-rail-tier-badge — AI 助手卡头收口（角标随套餐）＋同族错档文案清理

## Why

PRO 会员报「我已是 PRO，写作页仍让我升级 PRO」。定诊＝文案判据 bug（非权益问题）：

- 章纲页签那块「标「需开通／需 PRO／需 MAX」的行按套餐逐档解锁 ＋ 升级套餐」的判据写成 `!aiPlan || !aiPlot || !aiGenerate`，而 `ai-plot`（剧情推演）按设计属 **MAX**（PRO 快照里本就没有）→ 对任何 PRO/标准用户**恒为真**，免费态向导文案常驻；该句在设计稿里本为 `only-free`（book.html），React 版把「免费态文案」实现成了「任一 key 缺失」。
- 卡头角标写死「PRO」：免费/标准/MAX 全错。
- 同族错档文案：卷页签「拆下一章」标「需 PRO」而门禁是 `ai-plan`（标准档）、抽人锁卡同样说「PRO 功能／升级 PRO」（`ai-plan`）、蒸馏两处标签写「PRO」（实为 `style-quant`＝MAX）、升级弹窗标题写死「升级 PRO」、拦截弹窗标题恒「PRO 专属功能」。
- 规划台「铺空缺」前端按 `isPro` 拦，而后端端点 `/ai/expand` 的注解是 `@ai_feature("ai-plan")`（标准档）——标准档用户被前端多拦一档。

用户两条口径拍板（2026-10-08）：① 那句说明文案**直接去掉**（锁定行自带「需开通／需 PRO／需 MAX」hint 自解释）；② 卡头**角标改成跟套餐走**，卡头文案只有「AI 助手 · 页签名」——各档差异由下面能力行「能用几行」体现。

## What Changes

- **档位角标随套餐**：新钩子 `usePlanBadge()`（`hooks/useTier`）文案单源＝`lib/tier.tierShort`（与账号菜单同口径：S端 display_name 优先、试用剩 N 天、过期合并免费版）；色调随 tone（`accent` 会员／`muted` 免费版与过期／`warn` 试用临期）；档位未知（无快照）不标角标——宁空不说错。
- **卡头套餐文案退役**：章纲页签那句说明（副行／页脚／出口块三处）与卡头「你的 PRO 已包含 · 只加工你写的，不代写」「你的套餐已包含…」「未解锁 · 开通后本书 AI 即可用（标准档起）」全删；副行只承载功能性状态（无 Key／缺模型／模型失效／能力包未就绪）。`subTitle` 插槽无调用方，删除。
- **行级出口收窄**：章纲页签出口判据由「任一 key 缺失」改为 `!ai-generate`（免费/标准可见，PRO/MAX 不再被推升级），按钮移回能力行下方、不带说明文案。
- **升级弹窗目标档随档位**：已有 `ai-generate`（PRO/试用）→ 推 MAX（剧情推演／去AI味／文风蒸馏）；否则推 PRO（原有三行权益文案不变）。
- **同族错档文案清理**：卷页签「需 PRO」→「需开通」、出口按钮统一「升级套餐」；抽人锁卡与 toast 改「需开通（标准档起）」、标签 `PRO`→`标准`；蒸馏两处标签 `PRO`→`MAX`；拦截弹窗标题「PRO 专属功能」→「升级套餐解锁」；免费态两处提示（「模型已配好 · 开通套餐后本书 AI 即可用」「AI 是会员功能，开通套餐后解锁」）去 PRO。
- **锁文案单源**：行内档位 hint 一律走 `lib/features.upgradeHintOf(featureKey)`（章纲页签四行、卷页签拆章行、抽人锁卡、规划台锁文案、朱雀徽标、文风量化徽标）——与主 spec「档位感知锁文案＝单源 helper，SHALL NOT 硬编码字面量」同口径；文案随 key 出「需开通（标准档起）／PRO 专属／MAX 专属」。**档位短名同时补单源** `lib/features.tierLabel(tier)`（`upgradeHintOf` 内部改由它拼「X 专属」），四处档位徽标（抽人锁卡／规划台「铺空缺」／粘贴文风样本／量化页签）不再写字面量。
- **卡头功能性副行槽**：`AiWriterAssistant.statusNote`（与无 Key／缺模型等功能状态同槽，功能状态优先）——朱雀显示开关关时注明「朱雀检测已关闭 · 其余可用」（zhuque-workbench 口径）；SHALL NOT 用来放套餐文案。
- **规划台门禁对齐**：`VolumePlanModal` 的 `isPro` → `hasAiPlan`（`useFeature("ai-plan")`，调用点用 `NovelWorkspace.hasAiPlan`），锁文案与徽标改「需开通（标准档起）／标准」——与后端 `@ai_feature("ai-plan")` 同档。
- **原型同步**：`docs/design-c/prototypes/book.html` 章纲/正文两卡头改为「角标随档位（free-mode → 免费版）＋只留标题」，页脚两态同文收成一句；补上免费态「升级套餐」出口（`#btnUpgrade3`，`design-parity-book` 的 `modal-upgrade` 例原就按它点击）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：「右栏「AI 辅助」面板」的 ra-head 结构（档位角标随套餐＋可选状态副行＋行内 hint 走单源 helper）＋升级弹窗目标档口径＋行级出口口径＋三条新 Scenario。
- `storyline-settings`：「免费/PRO 两态」的卡头口径（只留角标与标题，不出套餐文案）。
- `intro-genre-settings`：锁定卡角标措辞＋拦截弹窗标题口径＋简介右栏卡头（档位角标＋可选功能性副行）＋「本书模型设定」的免费态提示与 `member_required` 表格行。
- `design-system`：「AI 写作助手卡片与结果区组件词汇」的头部口径（档位角标＋可选功能性副行；无套餐锁定态＝档位角标转灰）。
- `zhuque-workbench`：显示开关关时的副行注记明确承载位（功能性副行；功能状态优先）。

（`chapter-plan-ai`／`chapter-cast-review` 两处的档位措辞已由 `tier-plan-four-tiers` C端 半批 sync（#769）写进主 spec，本 change 不再出 delta——实现侧改由单源 helper `upgradeHintOf(featureKey)` 兑现其「SHALL NOT 硬编码字面量」。）

## 与 tier-plan-four-tiers 的关系

本 change 的出口/锁文案口径与其 C端 半批（`#769` 已 sync 规格）同源：规格里的「档位感知文案＝单源 helper」由本 change 的 `upgradeHintOf` 接线兑现；规格里的「升级弹窗按 `tier_required` 分档文案」亦已按此实现——出口把被点那行的 feature key 传入弹窗（`onUpgrade(required?)` 通道：卷页签拆章行/规划台 → `ai-plan`、朱雀检测行 → `ai-detect`、章纲页签行内出口 → 该用户下一件未解锁的件），弹窗出标准/PRO/MAX 三套口径之一；全局入口（本书偏好/账号区）不带 key，回退「当前档的下一档」。

## Impact

- 代码：`AiWriterAssistant`／`AiAssistPanel`／`VolumeAssistPanel`／`VolumePlanModal`／`CastReviewModal`／`ChapterWorkspace`／`SettingsView`／`StyleSettingForm`／`StylePasteModal`／`MemberBlockPrompt`／`UpgradeModal`／`BookPrefsModal`／`ModelSettingForm`／`NovelWorkspace`／`hooks/useTier`／`design/book.css`。
- 行为变更（唯一一处）：标准档用户获得规划台「铺空缺」（此前被前端 `isPro` 多拦一档；后端本就放行）。
- 设计资产：`docs/design-c/prototypes/book.html`；`book.free` parity 基线待随 `design:check` 重录（parity 为本地工具、不进 CI）。
- 测试：vitest 全量（含新增角标/出口钉子）、e2e 断言同步（plot／style-quant／story-arc／prompt-pack／world-settings／modals-pr5）。
