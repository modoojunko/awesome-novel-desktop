## Context

四档门禁机制（快照单源＋`require_ai_access`＋`ai_feature` 装饰器＋403 双 reason）在 tier-plan-four-tiers 已建成，42 个端点已挂 key。本 change 是**既定规格的实现补齐**：3 个只读端点（章自检/卷体检/盘点只读）规格明文收标准档但仍是免费例外；文风蒸馏（MAX 件）挂标准档 key；守卫测试因框架懒路由空转；另有两处零散（死标注、回填端点裸奔）。审计证据：`chapters/ai_plan.py:697`、`volumes/ai_plan.py:822`、`chapters/ai_cast.py:602`、`settings/ai_router.py:1832/1959`、`novels/router.py:128`、`workflow/router.py:153-210`、`tests/test_ai_feature_registry.py`。

约束：tier-plan-four-tiers 尚未归档，其 delta 是本 change 要实现的规格来源；主 spec 目前没有「按 feature key 的 AI 门禁」要求，故本 change 的 delta 只新增自身立法的两条要求（对拍守卫、回填门禁），SHALL NOT MODIFIED 未归档要求（避免 validate 悬空）。

## Goals / Non-Goals

**Goals:** 三个只读端点与两个文风端点按既定规格门禁；守卫测试真实生效且双向；死标注清除；回填端点收口；全部以回归钉子锁死（防回潮）。

**Non-Goals:** 不改档位矩阵与 key 词汇表；不做入口隐藏或新视觉形态；不动 `ai-check` 归属（已按 10-05 终拍挂 `ai-generate`）；不动 S端/发布链/DDL。

## Decisions

1. **门禁挂法**：`@ai_feature(key)` 置于 `@router.post` 之下（setattr 不 wrap，先例 42 处）＋签名补 `_: bool = Depends(require_ai_access)`，顺序在 `require_novel_model` 之前（会员/档位门在前，模型就绪门在后——与既有端点同口径）。同步清理「只读例外：免费可用」注释（与规格的「原免费例外通道退役」一致）。
2. **自检前端拦截**：`useChapterPlan` 增参 `hasChapterReview`＋`onUpgrade`，`runSelfcheck` **首行**判定：无 key 走统一升级出口（`window.dispatchEvent(new CustomEvent("member-block", …))`，与 CastReviewModal/NovelWorkspace 先例同口径），**任何请求都不发**——拦截须先于缺进场时的 anchor 补取（规格：SHALL NOT 发起调用）。备选「仅置灰按钮」被否——死按钮无出口，违反补救语句须带可点击出口的口径；「modal 内自判会员」被否——口径单源在 `useFeature`。`ChapterPlanState.selfcheck` 的「免费」注释随批退役。
3. **蒸馏行锁**：`SettingsView.styleAiRows` 的 `distill` 行用 `variant: "maxlk"`＋`hint: "MAX 专属"`（`useFeature("style-quant")`）——**锁定视觉但保持可点**，点击过 guard（标准档 state=ready）→ 后端 403 feature_required(max) → api.ts 广播 member-block → UpgradeModal。评审整改：不可用 `disabled`——`AiWriterAssistant` 行类型契约明写「guide/maxlk SHALL NOT 置 disabled，disabled 会吞 onClick 与点击有出口冲突」（c-zhuque-ai-detect 先例），且 chapter-plan.spec 已有判例注释「原实现把 onUpgrade 放在 disabled 按钮里＝死代码」。免费档由整卡 `settings-ai-fields` 锁承接（guard 升级出口），不落行级。`polish/check/fewshot` 三行不动（改挂 `style-suggest` 后标准档仍可用，锁态与现状一致）。
4. **守卫扫描穿透懒路由**：递归展开 `getattr(route, "original_router", None)`（duck-typing，不 import 私有 `_IncludedRouter`；starlette<1.6 时顶层即 APIRoute，双形态兼容）。备选 openapi.json 被否——不含 `__ai_feature__` 元数据。
5. **守卫双向断言**：①装饰端点 key ∈ 词汇表（原意，修复后真实生效）；②装饰端点**必有** `require_ai_access`（依赖树递归查，防死标注）；③关键档位 key 消费点非空清单（chapter-review/style-quant/ai-plot/ai-polish/ai-detect/ai-generate/prompt-panel/ai-plan/settings-ai-fields/style-suggest 各 ≥1）。
6. **e2e 种子**：`style-quant.spec.ts` 蒸馏链路 seed trial→**max**（trial 无 style-quant）；其余 spec（chapter-plan/cast-review/volume-plan）所需 key trial 已含，不动。
7. **回填门（评审 #12 收口）**：`ai-backfill` step1/step2 挂 `ai-plan`（确定性 AI 提取＝建书辅助 AI，与 `/ai/suggest-meta` 同档；当前无客户端消费点，零 UX 冲击）；`status`/`confirm` 纯状态读写不挂。
8. **死标注删除**：`POST /api/novels` 移除 `@ai_feature("ai-plan")`（无门依赖、零行为）；不补门——建书必须对免费档开放（仅受 `max_projects` 上限），补门会误伤。

## Risks / Trade-offs

- [标准档失去文风蒸馏（行为收紧）] → 这是 10-05/10-06 拍板的应然口径（MAX 件），landing 卖点已按 MAX 表述；e2e/单测种子随批改。
- [免费档失去自检的本地两组（衔接/配额）] → 三组与 AI 短评同端点绑定，规格明文整通道退役（chapter-plan-ai delta「原全档免费例外通道随四档改造退役」＋volume-plan-ai delta 免费档 403 场景）——有意识的取舍，非实现副作用；「需开通」胶囊已在卡面沟通。
- [trial 种子的 e2e 批量红] → 实勘后影响面收敛：现有自检/盘点/体检 e2e 均 trial 种子（trial 含 ai-plan/chapter-review，收门后仍绿），唯 `style-quant.spec.ts` 蒸馏链需换 max。
- [守卫修复后暴露未知漂移] → 先跑新守卫，暴露清单在同一 change 内补齐或单独登记（不静默放宽断言）。
- [三处收门影响既有后端测试（免费/试用户调用）] → 已实勘两处明文钉旧行为的翻转点（`test_volume_plan_ai.py` 体检族「免费档能 200 即证明不挂门禁」、`test_chapter_plan_ai_t3.py` 自检「免费档不被门禁拒」）与一处无种子文件（`test_cast_review_ai.py` 默认免费档，预计整文件红须模块级补 trial 种子）；按「规格应然」改判据（不得倒过来放宽门禁）。
- [tier-plan-four-tiers 归档顺序] → 本 change delta 用独立 requirement 名（ADDED），与该 change 不冲突，归档顺序无关。

## Migration Plan

无数据/接口迁移，纯门禁收紧；回滚＝revert 提交（无持久化副作用）。上线只需客户端随下个版本窗口发布（后端同包）。

## Open Questions

（无。ai-backfill 归属按建议拍定 `ai-plan`；若产品改判为「免费导入辅助」，删装饰器＋依赖两行即可，规格 delta 同批回退。）
