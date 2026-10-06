# Tasks: c-tier-gating-completion

## 1. 原型对照与影响判定（UI 变更先行）

- [x] 1.1 原型对照：`docs/design-c/prototypes/style-settings.html`（蒸馏行/右栏锁态）、拆章弹窗自检行（`book.html` 或对应原型文件）逐点核对；两个锁态差异（自检点击拦截、蒸馏行 MAX 锁）按需登记 `docs/design-c/prototypes/ADJUSTMENTS.md`。verification：ADJUSTMENTS 条目写入或明确「原型已含/无需登记」的结论落文
- [x] 1.2 双端影响判定：纯 C端、不触共享段（依据 proposal「Design Impact」）；无新视觉形态（锁态复用既有行锁样式与 `upgradeHintOf` 单源）。verification：判定结论与 proposal Design Impact 一致，无需 design-cross

## 2. 后端补门（client/backend）

- [x] 2.1 `chapters/ai_plan.py` 自检端点：挂 `@ai_feature("chapter-review")`＋`Depends(require_ai_access)`（置于 `require_novel_model` 之前），清理模块头与端点的「只读例外：免费可用」注释。verification：`curl`/pytest 免费档 → 403 `feature_required(chapter-review, standard)`，标准档过门
- [x] 2.2 `volumes/ai_plan.py` 卷体检端点（`POST /{ref}/ai/check`）：挂 `@ai_feature("ai-plan")`＋门；同清注释。verification：免费 403、标准过门
- [x] 2.3 `chapters/ai_cast.py` 盘点只读端点（`POST /ai-review`）：挂 `@ai_feature("ai-plan")`＋门；同清注释（模块头「免费只读」口径同步改）。verification：免费 403、标准过门
- [x] 2.4 `settings/ai_router.py` key 挪位：`/ai/style-distill/{action}` → `style-quant`；`/ai/style/{action}` → `style-suggest`。verification：标准档打 distill → 403(max)、标准档打 style → 过门；pro/trial 打 distill → 403(max)；max 全过
- [x] 2.5 `novels/router.py` 删除 `POST ""`（建书）死标注 `@ai_feature("ai-plan")`。verification：免费档建书仍 201（仅受 1 本上限）；注册表对拍不将建书列为门禁消费点
- [x] 2.6 `workflow/router.py` `ai-backfill/step1`、`step2` 挂 `@ai_feature("ai-plan")`＋门；`status`/`confirm` 不挂。verification：免费 403、标准过档位门（无模型走既有 503 引导）

## 3. 前端拦截（client/frontend）

- [x] 3.1 `hooks/useChapterPlan.ts`：增参 `hasChapterReview`＋`onUpgrade`；`runSelfcheck` **首行**判定无 key → 走升级出口、任何请求都不发（先于缺进场时的 anchor 补取）；同步 `ChapterPlanState.selfcheck` 的「免费」注释；`components/novel/NovelWorkspace.tsx` 接线（`useFeature("chapter-review")` 判定 + member-block 事件，与 CastReviewModal 先例同口径）。verification：vitest 免费档点击不发任何请求（selfcheck 与 anchor 都无）、弹升级；标准档照常发请求
- [x] 3.2 `workbench/SettingsView.tsx`：`styleAiRows` 的 `distill` 行用 `variant:"maxlk"`＋`hint:"MAX 专属"`（`useFeature("style-quant")`；锁定视觉但保持可点——`AiWriterAssistant` 行契约禁 disabled 吞 click，点击经后端 403 走 member-block 升级出口，评审整改）；免费档由整卡锁承接不落行级。verification：vitest 渲染断言（标准档 distill 行带 maxlk 锁视觉＋MAX 专属徽章且可点；max 无锁；免费整卡锁不变）——已绿。实现批注：锁文案走 `badge`（pill-warn「MAX 专属」）非 hint——AiWriterAssistant 仅 disabled 行渲染 hint，maxlk 行按 zhuque 先例走徽章；点击端内直出 member-block 升级口（后端门仍权威兜底）
- [x] 3.3 `ChapterPlanModal.tsx`：锁定时按钮态与提示复核（保留「需开通」胶囊；点击走 3.1 的升级出口，不再静默发请求）。verification：组件测试免费档点击断言升级事件、请求数 0

## 4. 守卫测试修复与双向断言

- [x] 4.1 `tests/test_ai_feature_registry.py`：扫描器改递归展开懒路由（`original_router` duck-typing，APIRoute 直命中兼容），断言枚举结果非空。verification：修复前写一条「枚举数 > 0」先红（现状 0）、修复后绿——红绿实证
- [x] 4.2 同文件双向断言：装饰端点 key ∈ 词汇表（原意恢复）＋装饰端点必有 `require_ai_access`（依赖树递归）＋关键 key 消费点非空清单（十键）。verification：临时注释掉一个依赖即红（误删/死标注可捕获），恢复后绿
- [x] 4.3 `tests/test_ai_feature_http.py` 补 HTTP 级档位钉子：免费打 selfcheck/卷体检/盘点 → 403；标准打三个 → 过门（走模型就绪门）；标准打 distill → 403(max)、max 过门；标准打 style → 过门。verification：新钉子全绿，且实现回退版本上先红（对拍有效性自证）

## 5. 测试随批与 e2e

- [x] 5.1 后端受影响的存量测试逐个实跑并修种子/断言（不得放宽门禁）：`test_volume_plan_ai.py`（体检族 :413-484 两条「免费档能 200 即证明不挂门禁」断言＝语义翻转点，改判 403＋补标准档过门钉）；`test_chapter_plan_ai_t3.py`（:177 自检用例 docstring「免费档不被门禁拒」翻转——种子 bump trial 保住提示词内容断言＋另补免费 403 钉）；`test_cast_review_ai.py`（全文件无档位种子＝默认免费档，收门后预计整文件红，模块级补 trial 种子）；`test_style_settings_v2.py`（蒸馏族 seed trial→max）；`test_plan_pacing_rules.py`。verification：`cd client/backend && .venv/bin/python -m pytest` 全量绿——**1956 passed / 1 skipped / 0 failed**。实况批注：`test_style_settings_v2.py` 无需动种子（该文件模块级 override require_ai_access，门语义由 HTTP 钉子文件管）；`test_volume_plan_ai.py` 体检族与 `test_chapter_plan_ai_t3.py` 自检族按翻转改判据（trial 过门保内容断言），`test_cast_review_ai.py` 新增免费直调 403 钉＋形状钉改走门 override
- [x] 5.2 `client/frontend` vitest：新增/更新 useChapterPlan、ChapterPlanModal、SettingsView 用例——优先扩进既有测试文件；若新增文件，同批登记 `coverage-contract.ts`（仓规：新前端测试文件不入表 CI 红）。verification：`npx vitest run` 全量绿（记录数字）
- [x] 5.3 e2e：`style-quant.spec.ts` 逐用例过——凡触蒸馏链的换 max 种子（若存在「trial 可蒸馏」断言＝语义翻转点改判据）；`chapter-plan.spec.ts` 补免费档自检拦截断言（点击弹升级、selfcheck 与 anchor 零请求；现有免费段 :310-330 无自检断言、现有自检用例 trial 种子收门后仍绿，已实勘）；`cast-review/volume-plan` 复核锁态断言。verification：受影响 spec 在隔离栈实跑全绿——**34/34**（chapter-plan 12＋cast-review ＋style-quant 6＋volume-plan 5；隔离栈 -p an-tg，端口 5175/8010/19010/5176，容器/数据目录全独立；前后端容器特征串自证＝「文风蒸馏为 MAX 专属」「章纲自检需开通」「只读评估归标准档」；跑完 down -v 销毁）。插曲：老 spec（style-quant/volume-plan）不认 E2E_CLIENT_DATA、硬编码仓库根 .docker-data/client——worktree 软链到隔离数据目录解决，零代码改动
- [x] 5.4 `test_dossier_pipeline.py` 等使用 `ai_access_granted` 桩的存量测试复核（归档撤门语义不受本改影响）。verification：相关文件实跑绿——全量 pytest 1956 passed/0 failed 覆盖（含 test_dossier_pipeline/test_archive_free 族，两次复跑同数）

## 6. 归档前对齐（tier-plan-four-tiers 文档）

- [x] 6.1 修正 tier-plan-four-tiers 两处与 10-05 终拍冲突的 delta 文本：volume-plan-ai/workbench「六类案头检查归 ai-plot(MAX)」→ `ai-generate`(PRO)；workbench「文风建议归 style-quant 标准起」→ `style-suggest`；tier-gating 词汇表删旧口径行。verification：`openspec validate tier-plan-four-tiers --specs` 仍过；两处文本与代码/前端一致
- [x] 6.2 `openspec validate c-tier-gating-completion --specs` 通过（输出：两 change 非严格/严格均 valid；s-payments/s-pay-cashier 两条 INFO＝拆仓存量归属，tier-plan tasks 6.6 已登记）

## 7. 回归门禁（实际输出结论回填）

- [x] 7.1 门禁实跑结论：`client/backend` 全量 pytest（数字）＋`client/frontend` `tsc --noEmit`／`vitest run`／`design:lint`／`design:check`（结论与存量红区分）＋受影响 e2e 隔离栈实跑（34/34），全部回填本行——**C端 pytest 1956 passed/1 skipped/0 failed**（收尾复跑两次同数）；**tsc --noEmit 零错**；**vitest 1207/1207 绿**；**design:lint exit 0**；**design:check 7/8**（唯一红＝书架屏 empty 存量光栅漂移，记忆在案与本改零交集）
- [x] 7.2 守卫有效性自证：在实现回退的临时工作区跑新守卫与 HTTP 钉子（应红），复原后绿——已留档：六文件 git checkout 回基线后跑新守卫＋HTTP 钉＝**恰红 6 条**（test_decorated_endpoint_must_have_gate 抓 POST /api/novels 死标注；test_required_keys_have_consumers 抓 chapter-review/style-quant 零消费点；4 条 HTTP 钉抓三未收门端点＋蒸馏 key 挂错），恢复实现后全绿——守卫对本 change 修复的每一类漂移都有抓捕力。另有 staged 红绿：旧扫描器＋新「枚举非空」断言先红（0 枚举＝空转实锤）
- [x] 7.3 提交＋PR（标题不带硬编码 PR 号）；随下个版本窗口发布（无需 S端/DDL 联动）——两笔提交（工件 52e588b9＋实现 fee76257）已推远端并验 head，PR 已开
