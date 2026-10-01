## Context

「AI 起草」现状是一条完整纵切：右栏行（`AiAssistPanel` og 页签 `draft` 行，testid `og-ai-draft`）→ `Rail` 透传 → `ChapterWorkspace.handleAiDraft`（覆盖确认判定 `ogHasDraftContent` + `draftOutline` API）→ 后端 `POST .../outline/ai-draft`（`chapters/ai_draft.py` 的 `ai_draft_outline` + 素材组装 + `_sanitize_draft` 清洗）→ `prompts/outline_draft.prompt` 模板。同文件里的 `fill-gaps` 端点（补全缺失字段）与起草共用素材零件（`_setting_blocks`/`_material_from_ctx`），**必须保留**。约束：撤行是用户可见改动，按硬性流程原型先行；`railChapter` 在 parity 页集内，原型与实现须同批撤行。

## Goals / Non-Goals

**Goals:**
- 右栏章纲页签撤「AI 起草」行，六行变五行；行级门控/免费副行/升级出口语义不变（「需 PRO」行数随行数变化）。
- 起草专属代码全链退役（前端 handler/props/API 函数、后端端点与清洗、提示词模板），不留孤儿；共享零件（fill-gaps、素材零件）零行为变化。
- 规格同步：outline-ai-draft 撤五条 requirement 留 fill-gaps；workbench 撤起草入口 requirement 并改「两态」requirement；chapter-data 撤「有现有章纲」判定引用。

**Non-Goals:**
- 不动章纲「确认/撤回确认/保存草稿不自动确认」链路（c-og-draft-no-autconfirm 成果是通用保存语义）。
- 不动「补全缺失字段 / AI 帮写剧情 / 剧情推演 / 盘点出场人物 / 与卷纲冲突检测」五行。
- 不动 token_log 里 `outline_draft` 历史记账（只读留存）；不清理其他 spec 里的残句（chapter-cast-review / volume-plan-ai 的「AI 起草」字样留归档 sync 扫净）。
- 不做后端 `/ai-draft` 的 410 兼容响应（本地单用户应用、无外部消费方，直接 404）。

## Decisions

- **capability 不改名**：`outline-ai-draft` 名下保留 fill-gaps requirement，能力延续；改名会让 chapter-data 等 cross-ref 全链空转，收益为零。
- **撤行而非置灰**：置灰留一行「需 PRO」死行是负资产；直接撤行与「AI 入口收口右栏」（2026-09-20）的撤入口先例一致。
- **`ogHasDraftContent` 随功能退役**：唯一消费方是起草的覆盖确认；「填了内容要不要二次确认」的通用语义由「确认章纲」显式门承担，不挪用。
- **后端同批撤端点**：CLAUDE.md 孤儿代码口径——本变更使端点成为死代码，留着只会被误认可用；e2e 桩（`page.route("**/outline/ai-draft")`）只存在于整删的 outline-ai-draft.spec.ts。
- **chapter-data 只撤第 ① 项消费链路**：挑战/阶段两列的判定消费方只剩「写正文素材」（第 ② 项，保留）；防覆盖由「章纲表单整表回传」条款独立保障，不随起草退役。

## Risks / Trade-offs

- 撤行后章纲页签从「六行」变「五行」，`castReviewRail` 等单测钉了「其余五行」「需 PRO ≥5」——同批改数，避免存量红。
- 后端 `test_story_arc.py` 的 premise 镜像回归借用 `_arc_markdown` 作读方——随函数删除该测试；镜像本身的存储层回归（`test_put_roundtrip_and_mirror` 等）不动。
- parity：`railChapter` 若在基线页集，原型与实现必须同批撤行，否则 design:check 红的根因会指向本次改动（登记进 ADJUSTMENTS 备查）。
