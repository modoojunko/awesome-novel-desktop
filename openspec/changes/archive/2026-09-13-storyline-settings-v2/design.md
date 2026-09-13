# 主线设定页 v2 — 技术设计

## Context

- 评审稿 `docs/design-c/drafts/storyline-settings-draft.html`（v1.3）为唯一设计事实源；三路工程师评审（前端 agent_c38d049c / 后端 agent_83c3065c / 测试 agent_b2a77f5b）的实勘结论已吸收进稿。
- 现实现：`StoryArcForm`（premise＋结局想法 tone-opt 选择题＋分卷规划行）＋ `useStoryArc`（ArcData={premise, ending, volumes}，PUT 整卡）＋ `ArcWizard`（四步 condense/ending/split/audit，`runArcWizard`）＋ readiness `_check_story_arc`（premise 或 volumes 非空）＋ ChapterContext 注入主线**无裁剪**。
- 约束：KV key=`story`（project_settings），整份 PUT 覆盖语义；库层零迁移（指纹留档＋包契约兜底）；「大字段五处 TEXT」清单不得新增；novel 一名纪律（新代码 novel_id）；naive UTC；AI 端点统一 `require_ai_access` ＋ 本书模型门 ＋ `record_usage` 注册；S端零感知（novel 数据不出本机）。

## Goals / Non-Goals

- Goals：主线面板收敛为「全景＋结局三问」；story_arc 契约换形且存量无感；右栏与设定页 AI 家族同构；fullstory 进写章注入且裁剪责任归一；归档域 schema 定稿留档。
- Non-Goals：不做写作阶段的拆卷/卷纲 UI；不建归档表与归档界面；不改其他设定面板；不做主线版本历史/时间线。

## Decisions

- **D1 KV 双写过渡（加键兼容，不升 format_version）**：读侧 `fullstory ?? premise` 归一；写侧把 fullstory 镜像回 premise 字段。替代方案「改布局升版＋旧版读窗」被否：无跨机旧版读窗需求，双写即可保旧代码读等价内容与资产包往返无损；volumes 键原样保留（PUT 缺省时服务端跳过该键不删）。存储命名为「project_settings KV story 键内 story_arc 对象」，不新增 TEXT 列（KV content 本就是 Text JSON，五处大字段纪律不冲突）。
- **D2 结局基调＝自由输入＋行内 AI 帮我填**（用户 09-12 拍板）：tone-opt 选择题退役；行内入口沿用文风/禁用词句页字段行内 AI 同款（field label＋.ai-fill），不新增组件类。三问问题行实现用现有 `.wb .field label`（问题句进 label 正文、例句进占位符）——评审稿内 q-label/rail-card 等类名仅为稿面参照，落地必须用现有词表：右栏 `rail-assist/ra-step` 系（`.rail-card` 与 base.css:204 撞名）。
- **D3 AI 四能力端点**：`POST /api/novels/{novel_id}/settings/ai/arc/{draft|calibrate|check|tone}`，出参沿现版 AI 信封（`{value}`），check 出 `{checks:[{name,status,note}]}` 四线（故事连贯/开头接结局/三问对得上/和简介一个方向）。门＝require_ai_access ＋ 本书模型绑定；operation 注册进 record_usage。前端 SettingsView 以 introRef/genreRef 同款句柄分发（StoryArcForm 补 runAi(key)/clearAi()）；行内 tone 与 rail 三行共享面板级 aiBusyRef＋父级 aiRowBusyRef 双锁（在途互斥）。
- **D4 裁剪责任归一**：存储不截断（PUT 硬上限 2000 字防滥用，600 字为前端建议值不硬校验）；写章注入在 ChapterContext「故事走向」段按 ≤600 字预算裁剪、与简介合并预算（现版注入无裁剪，必须补）；「全书主线：…」注入文案承接 intro-genre-settings 的剧情轨道退役线。
- **D5 ArcWizard 退役**（用户拍板「按建议」）：删除 `story/arc_wizard.py`、`runArcWizard`/`GET next_step` API 与前端 ArcWizard 组件、useStoryArc 的 wizard/resumeStep/next_step 状态；四步语义由三行吸收（condense→起草主线、ending→结局校准、audit→主线体检、split 随分卷移交写作阶段）。
- **D6 确认口径沿现版**：按钮不置灰；空内容后端 400（readiness `_check_story_arc` 改判 fullstory/ending 任一非空，legacy premise 归一）；确认成功计 5/8＋确认即前进（SettingsView.handleFootAction 现逻辑不动，仅判据改）。
- **D7 归档域 schema 定稿不实现**：主线进度 `{ref, kind(event/revision), event, stage, note, review, created_at}`，幂等键=(ref,kind)，stage 枚举外回退「发展」记 note；支线合流 hooks 按**实勘字段**映射（desc→description、intro_ref→introduced_in、生命周期→组归属、name/end_ref/review→新键，`kind:"subplot"` 注入过滤独立预算；hooks.priority 是数字串禁复用）；两记录为可审阅工作记录（非 append-only 台账）。建表随「正文归档」change。

## Open Questions

无——2026-09-12 拍板齐备（主线只管主线 / 结局三问＋行内 AI / AI 聚焦本设定 / ArcWizard 退役），三路评审无未决 P0。
