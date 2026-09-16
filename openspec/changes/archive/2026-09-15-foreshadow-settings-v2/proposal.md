# foreshadow-settings-v2

## Why

伏笔是网文作者最痛的「埋了忘了还」问题，也是 AI 写章连续性的关键事实源。现行伏笔设定是 KV 整存整取的裸表单（截 14 字列表、状态下拉搬移、无收束闭环、无 AI 台账能力），且章节引用是自由文本——归档 mentioned 标记与写章「排除本章伏笔」都靠格式猜测，静默失灵。用户已三轮拍板：伏笔升级真表＋id 引用、章节匹配用章节 id、确认门禁保留（伏笔不能为空）。

## What Changes

- **数据模型**：伏笔从 `settings/hooks.yaml`（active/resolved/abandoned 三数组）升级为真表 `novel_hooks`（id UUID＋每书单调 seq、description、type slug、priority Integer、status 单列、introduced/planned/resolved_chapter_id、payoff_note、mentioned_in_chapter_id）；旧 KV 三数组经升级链迁入真表
- **升级与备份**：schema 指纹变更走「整库留档＋空库＋v1 包恢复」链路——导入器补 v1 hooks 读窗（mentioned→active＋mentioned 列、绑不上的章引用置 NULL 不丢行、priority/type 混形归一）；导出包新增 hooks 段（章引用存 ref 不存 id）；FORMAT_VERSION 2→3
- **CRUD 与持久化**：条目级 REST（GET/POST/PATCH/DELETE/restore，ops token 撤销按原 id 恢复，seq 永不复用）；前端字段级防抖 PATCH＋串行队列自动保存，save()=flush，「存草稿」按钮对伏笔隐藏
- **伏笔面板重写**：台账三分组（活跃/已收束/废弃，状态点 N5 同源、空组不渲染、搜索、添加置顶）；伏笔卡 kv 档案表（描述/引入/计划收束/类型/优先级/状态三态显式切换/收束记录软引导）；章节三格＝卷章选择器（按卷 optgroup，存 chapter id，悬挂显示「章节已删」，未建章留空降级）
- **确认门禁**：确认「伏笔」≥1 条描述非空（任意状态）；判据口径不变、checker 数据源换真表；确认后内容有变徽标降级「内容有变 · 待重新确认」（charStale 先例）
- **AI 四行（PRO，右栏助手卡）**：起草伏笔（3 候选勾选采纳）/拟收束方案（对选中条目，覆盖明示可撤销）/埋坑体检（活跃×已写章纲，点名超期/在期/未定期/无留痕，可点跳转，无章纲降级）/查一致性（选中×简介/题材/世界）；新端点 `/ai/hooks/{action}` 只出建议、采纳走前端组合
- **退役**：旧 `POST /settings/ai/hooks/description` 单字段端点（400 退役文案）、`settings_hooks.prompt`、`PUT /settings/hooks` 整存整取、`_canonical_chapter_ref` 两处副本
- **消费方切换**：写章注入判据 status==active＋chapter id 排除本章；归档联动改单条 UPDATE mentioned_in_chapter_id
- **卷章树 API**：`GET /volumes`、`GET /tree` 响应补 chapter id（现役不吐 id，选择器数据源前置）
- 明确不做（non-goals）：mentioned_in_chapter_id 本期只迁不增（归档 UI 归写作期 change）；工作台侧埋坑体检入口留写作期 change；ConfirmGuard 组件不新造（沿现役两处 confirm 守卫）

## Capabilities

### New Capabilities

- `foreshadow-settings`: 伏笔设定面板行为契约——真表 novel_hooks、台账三分组与伏笔卡、条目级 CRUD＋ops token 撤销、自动保存、卷章选择器（存 chapter id）、确认门禁（≥1 条非空任意状态＋内容有变降级）、AI 四行契约（只出建议、采纳走前端组合）、术语「收束」单源

### Modified Capabilities

- `creation-flow`: 「无 AI 能力设定项」清单移除伏笔（伏笔获得右栏 AI 四行）；伏笔确认门槛口径（≥1 条描述非空、任意状态）并入设定确认流
- `readiness`: hooks checker 数据源从 KV YAML 换真表；「已填」判据扩展为任意状态（≥1 条描述非空，不再只读 active）
- `prompt-crafting`: 伏笔注入口径随真表化调整——只注入 status==active、按 chapter id 相等排除本章引入（替代 ref 字符串比较）、优先级注入标签与存储口径对齐（高/中/低）
- `write-archive-meta-sync`: 归档联动从「整文件读改写 status:mentioned」改为「单条 UPDATE mentioned_in_chapter_id」，状态枚举不再被归档污染
- `backup-restore`: FORMAT_VERSION 2→3；导出包新增 hooks 段（章引用存 ref）；导入器补 v1 hooks 读窗与 ref→id 重绑（章循环落库之后）
- `volume-chapter-service`: `GET /volumes`、`GET /tree` 响应补 chapter id 字段
- `design-system`: 新增 hk-* 词表（台账两行条目、状态点三色活跃=warn/已收束=ok/废弃=muted、卡面状态徽标同源）、保存四态在伏笔面板的应用、`.kv` 家族作用域化映射（避让世界面板现役 `.kv-row`）

## Impact

- **C端后端** `client/backend`：新 `models/hook.py`＋`settings/hooks_model.py`（词表单源）＋`settings/hooks_router.py`（CRUD/restore）；`settings/ai_router.py`（新 /ai/hooks/{action}、旧字段生成退役）；`workflow/readiness.py`（checker 换源）；`prompt/context.py`、`write/chapter_writer.py`、`write/auxiliary.py`、`chapters/ai_draft.py`（消费方切换）；`archive/service.py`（mentioned UPDATE）；`backup/{format,export,importer}.py`（FORMAT_VERSION 3＋hooks 段＋v1 读窗）；`volumes/service.py`（树响应补 id）；`filesystem/paths.py`、`filesystem/init.py`（hooks 键与种子摘除）；`legacy_archive.py`/`scripts/upgrade_drill.py`（演练扩阶段）
- **C端前端** `client/frontend`：`lib/hooksApi.ts`（新，对齐 charactersApi 形态）；`components/novel/settings/HooksSettingForm.tsx` 重写为伏笔台账＋伏笔卡；`SettingsView.tsx`（右栏 foreshadow 分支、formRef、存草稿显隐、panel-foot）；`AiWriterAssistant.tsx`（四行接入）；`design/book.css`（hk-* 词表收编＋ADJUSTMENTS 登记）
- **迁移**：所有存量用户库触发一次「留档＋空库＋v1 包恢复」；导出包格式升级（旧包兼容读窗保留）
- **测试**：后端矩阵约 30 例（表约束/CRUD/迁移/归档联动/门禁/AI 四组）、e2e 14 例＋存量改造（creation-flow hooks 段、readiness/workflow 种数据换新 API）、六阶段升级演练扩伏笔种子
- **设计工件**：设计稿 `docs/design-c/drafts/ai-novel-c端-伏笔设定.html`（v3 终稿）→ 转正 `docs/design-c/prototypes/` 并登记 ADJUSTMENTS

## Design Impact

- 受影响端：**C端**（S端 无涉）
- 受影响屏/弹层：设定页「伏笔」面板（中栏台账＋伏笔卡、panel-foot 保存态与确认、右栏 AI 助手卡四行）；无新弹层（覆盖采纳为行内警示＋回执撤销，不加二次弹窗）
- 对象状态（对照状态语言总表）：伏笔三态 活跃=实心 warn（进行中·待收束）／已收束=实心 ok／废弃=muted 描边；徽标 「N 条待收束」warn→「已确认 · N 条待收束」done→「内容有变 · 待重新确认」warn→「全部收束」ok；回执条沿用 accent 回执语言（面板内自管、最近一条、8 秒自清）；保存四态（保存中…/已自动保存）落面板脚
- 触碰两端共享段：否（hk-* 词表为 settings-v 作用域新类，沿 `.cap`/`.ai-sink` 先例落 book.css settings-v 段；`.kv` 家族作用域化避让世界面板现役 `.kv-row`，映射表随 ADJUSTMENTS 登记）
- 原型先行：是——`docs/design-c/drafts/ai-novel-c端-伏笔设定.html`（v3，用户已终审）转正入 prototypes 并登记 ADJUSTMENTS 后再动实现
- 设计工件来源：设计侧会话（已产出，经前端/后端/架构师/UX＋前端/后端/测试/产品两轮共八份评审）
