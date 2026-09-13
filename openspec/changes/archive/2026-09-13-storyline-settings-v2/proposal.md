# 主线设定页 v2（storyline-settings-v2）

## Why

主线面板现实现（StoryArcForm：一句话主线＋结局想法＋分卷规划＋右栏 ArcWizard 四步向导）与 2026-09-12 用户拍板的目标形态有四处结构性差距：①主线只管主线——创建期只写「从头到尾的全景＋结局」，分卷/体量归写作阶段、进度/支线归归档；②一句话 premise 要升级为比简介更全的 fullstory 全景；③右栏四步向导与简介/题材/世界已收敛的「能力行卡」形态不一致且部分步骤越权（倒推分卷）；④基调选择题要改为自由输入＋行内 AI。评审稿 `docs/design-c/drafts/storyline-settings-draft.html`（v1.3）已经前端/后端/测试三路工程师评审并把实勘修正回灌，可立项落地。

## What Changes

- 中栏「主线」面板重写为两块：**这本书从头到尾说什么**（fullstory 大文本，建议 600 字以内、前端不硬截）＋ **结局是什么三问**（ending.scene / ending.hero / ending.tone 自由输入；问题句为标签、例句进占位符；第三问旁行内「AI 帮我填」）
- **BREAKING**（KV 内对象布局，不升 format_version）：`story_arc` 由 `{premise, ending, volumes}` 改为 `{fullstory, ending{scene,hero,tone}}`；双写过渡（读 `fullstory ?? premise` 归一、写时镜像回 premise），volumes 键原样保留不再读写
- 分卷规划（volumes 行）整块移交写作阶段：本页移除，数据保留，唯一其他消费方 readiness 同批改判
- 右栏 ArcWizard 四步向导**退役**（用户 2026-09-12 拍板「按建议」），替换为 AiWriterAssistant 三行：起草主线 / 结局校准 / 主线体检——AI 全部聚焦本设定（他项设定只作输入，结论只落主线字段）；新增四能力 AI 端点（draft/calibrate/check/行内 tone）
- 免费/PRO 两态：整卡可见＋锁定（ai_state 单源）、点击统一升级提示；两态文案对齐作家视角（「Max 同享」等内部词不上面板）
- 确认口径沿现版：按钮永远可点、空内容由后端 400 提示、确认成功计 5/8 并确认即前进下一设定项
- fullstory 进写章提示词「故事走向」段（ChapterContext 唯一裁剪点，≤600 字注入预算）；readiness arc 判据改 fullstory/ending 任一非空（legacy premise 归一）
- 归档域两条记录（主线进度 / 支线）的 **schema 本 change 定稿、不建表不出界面**——建表与交互随「正文归档」change

## Capabilities

### New Capabilities

- `storyline-settings`: 主线设定页契约——中栏两块（全景＋结局三问）、确认与进度口径、右栏 AI 三行与行内 AI 填、免费/PRO 两态文案与门控、story_arc KV 契约与 legacy 迁移、四能力 AI 端点、写作注入与归档域 schema 定稿

### Modified Capabilities

- `creation-flow`: 「主线卡（建书后、卷纲前的拆纲环节）」需求（含分卷表）整体移除，页面契约迁至新能力 `storyline-settings`
- `readiness`: 新增 arc（第 05 项主线）内容判据——fullstory/ending 任一非空即已填，legacy premise 归一
- `intro-genre-settings`: 「题材面板」需求中主线写作注入的字段引用 premise → fullstory（剧情轨道退役承接线随改版更新）

## Impact

- 前端：`StoryArcForm`/`useStoryArc`（ArcData 换形＋runAi/clearAi 句柄）、`SettingsView`（arc 接线 runAi 分发/onReceiptChange/desc 文案）、`AiWriterAssistant`（三行 rows、ready 态头部文案去「Max 同享」）、`ArcWizard` 删除；右栏落地用现有 `rail-assist/ra-step` 词表（`.rail-card` 与 base.css 撞名，评审稿内类名仅参照）
- 后端：`story/arc` 读写（KV key=story 内 story_arc 对象；整份 PUT 改兼容读＋镜像写）、`workflow/readiness.py` arc 判据、`write/chapter_writer.py` ChapterContext 主线注入段（补裁剪）、新增 `settings/ai` arc 四能力端点（require_ai_access＋本书模型门＋record_usage）、删除 `story/arc_wizard.py` 与 `runArcWizard` API（`next_step` 为 GET/PUT story-arc 响应内嵌字段，随向导退役一并移除）
- 数据：存量书无感迁移（双写过渡）；volumes 数据保留
- e2e：`story-arc.spec.ts` 三用例随改造整体重写；od-id 清单见 design/tasks
- 不影响：S端（novel 业务数据不出本机）、format_version、其他设定面板
