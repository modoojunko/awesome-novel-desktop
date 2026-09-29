# Proposal: c-write-prompt-layering（写正文提示词模板分层重构）

## Why

写正文是全仓唯一没有模板的 AI 调用：`write/router.py` 用 f-string 拼 system（身份句＋铁律），user 层由 `ChapterContext.to_prompt()` 一整包组装——恒定素材（题材/文风/世界观/卷纲）与章级动态素材混在一起，逐章重复发送且被「存为本章提示词」的存量稿整包替换路径放大。外部评审（提示词工程师实勘 2026-09-28）确认：真实发出的 system 存在「你是。」空串缺陷（`get("role", 默认)` 对空串不生效）、铁律缺「本章必须完成 vs 剧情条目」冲突仲裁、输出契约只在 user 层单写；世界观按 600 字预算裁剪势力导致本章驱动势力（圣银教团）被「从略」。四路评审（提示词工程师/后端/架构/产品）已复核本提案修订稿。

价值口径（诚实边界）：本改动的作者可感知收益是**四个实锤缺陷修复**（势力裁剪、空身份句、仲裁缺失、契约单写），同时为后续素材类改动（地点 lore/NPC 设定/题材 persona）提供正确地基；缓存省钱是**地基性收益而非本次直接收益**——Anthropic 系不打 `cache_control` 零命中、计费侧无缓存传导机制，均不在本次范围。

## What Changes

- **新增写正文 system 层模板** `prompts/write_chapter.prompt`（`<<system>>/<<user>>` 分层，走 `load_layers` 既有机制）：system＝角色定位＋输出契约（铁律三条＋新增「本章必须完成视为已写情节」仲裁句）＋节奏分档＋故事前提与全书主线＋题材设定＋文风基线（量化六行＋文风例句＋禁用词，空则跳过）＋写法要求（质感/语言）＋世界观（全量，势力不再「从略」）＋世界铁律（从 user 红线区上收）＋本卷卷纲＋人物档案锚（全书角色静态档案）。`WRITING_IRON_RULES` 常量与 router f-string 拼接退役。
- **user 层拆出**：`to_prompt()` 重构为章级动态素材组装（本章位置标注/章纲概要/剧情条目/要撞的墙/卷内位置/章末落点/叙事目标/前文回顾/角色状态/文风影子覆盖块/活跃伏笔——补 `[编号]`＋优先级前缀与素材包渲染器同口径/章级红线（必须完成/必须兑现/必须维持/禁止）/字数目标含 ±10% 与压缩策略），删除「## 角色定位」「## 题材设定」「## 文风」「## 原则与禁忌」「## 故事背景」等恒定块；「疲劳词见上方」悬空引用与空节渲染随之退役。三个调用方（GET /write/prompt fresh、写正文兜底、提示词精修）同步切换；`prompt_refine.prompt` 中引用旧分节结构的文案同步。
- **persona 单源修复**：`get("role", 默认)` 空串缺陷改为集中 resolver（手填优先，空/缺省兜底「一位小说家」），system 组装与素材包渲染同源消费。
- **收尾重申行**：写正文调用前由代码在 user 内容最末字节强制追加一行压缩输出契约（「输出：仅正文，无标题、无总结、无引导语、无 Markdown。」），不落库、不进弹窗预览、对存量稿路径同样生效。
- **存量稿 legacy 分级引导**：GET /write/prompt 对持久化 write-prompt 行判定是否旧版整包（润色稿按 `_POLISH_ANCHORS` 三锚同现判定、粗组存稿按恒定块标题判定），响应新增 `legacy` 字段；弹窗对「润色过的旧整包行」只做信息性提示（恒定设定已由系统注入），对「粗组存稿旧整包行」建议刷新重组——避免引导作者用粗组稿覆盖刚润色的稿。**BREAKING（契约形状）**：fresh 组装返回值从整包变为纯章级 user 层。
- **组装 lint**：组装时校验「本章必须完成未被剧情条目覆盖」与「活跃伏笔混入已兑现记录」两类问题并显式告警（不阻断）。
- 润色链（`/prompt/polish`，输入＝`material_markdown()` 素材包）本次不动；其落库行按上述分级提示处理。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`：「基于确认提示词生成」（分层后持久化提示词＝user 层、legacy 分级引导、fresh 返回形状）与「写作铁律注入」（铁律＋仲裁句进 system 恒定层、收尾重申行）两条 Requirement 修改；新增「system 恒定层组装」Requirement。

## Impact

- 后端：`write/router.py`（system 组装切换、收尾行追加、GET legacy 字段）、`write/chapter_writer.py`（to_prompt 拆层、resolver、铁律常量退役、伏笔渲染口径、组装 lint）、`write/prompt_assembly.py` 或同域新模块（安全渲染 helper）、新模板 `prompts/write_chapter.prompt`、`prompts/prompt_refine.prompt`（旧结构词同步）、`settings/ai_router.py`（档案块函数抽至 `prompt/context.py` 共享、原处委托）。
- 前端：`client/frontend/src/components/novel/workbench/modals.tsx`（legacy 分级提示＋两处「设定＋章纲」文案对齐 fresh 新语义）。
- 测试：`test_chapter_writer.py`、`test_write_prompt_polish.py`、`test_novel_genre_relational.py`、`test_prose_pipeline.py`（WRITING_IRON_RULES 直断言迁移）、`test_prompt_layering.py`（新模板自动纳管）、AiModal vitest 补 legacy 分级用例。
- **前置依赖**：「本章位置」标注（chapter_position，user 层行＋节奏分档激活）依赖另一会话的开篇期 WIP 先合入 main——本提案 rebase 于其上；其素材包侧漏加标注由该会话补齐。
- 缓存验收：`ai_client.py` 流式链路无缓存读数字段（`StreamEvent` 仅 input_tokens），验收走非流式 `chat()` 同 system 试发核对命中、按供应商分列判定（Anthropic 系 0 命中记为预期内），局限写明；流式缓存记账字段另立。
