# c-char-ai-card-generic — Design

## Context

「从简介立主角」链路（`POST /settings/ai/characters/bootstrap`）实现上已经是卡级通用的：带 `character_id` 即以服务端空值为基准只补空格，端点对角色无门槛。主角专属的只有三处——前端行门控（`ctx.role === "主角" && ctx.nameless`）、空态引导、提示词模板 `settings_characters_bootstrap` 的主角措辞。配角/反派复用这条链即可，唯一的实质新产物是角色通用模板与右栏行。

## Goals / Non-Goals

Goals：配角/反派获得与主角对等的「一键立卡」体验；主角链零回归（模板字节不动、端点行为对主角路径不变）。

Non-Goals：不给路人加任何 AI 出稿；不改右栏既有四行与四档门控；不改「卡片上不放 AI 按钮」拍板（新增卡区提示为纯文案不可点）；不动 AiCardModal 结构。

## Decisions

1. **复用既有端点，不做新路由。** `bootstrap` 端点已具备卡级通用语义（character_id＋只补空格＋skipped）。泛化＝端点内按 `ch.role` 分派提示词：无卡/主角 → 现行 `settings_characters_bootstrap`；配角/反派 → 新增 `settings_characters_card`。备选「新开 `/ai/characters/card`」被否：两套路由承载同一语义，徒增门控/日志/前端类型面。
2. **新模板而非参数化旧模板。** 旧模板主角措辞贯穿全文（立卡师身份、产出 1 的拟名口径、剧情定位口径），参数化会把主角链拉进回归面，且 e2e 桩短语对主角路径的既有钉子必须零漂移。新增 `settings_characters_card.prompt`：`{role}` 占位（配角/反派），剧情定位口径改为「他与主角这条线的关系 / 他在故事里干什么」，其余格位口径、认知六层框架与铁律与主角版同源（自足成文，模板不互相引用——提示词仓惯例）。门禁：`test_prompt_layering` 等价约束随仓 tests 走。
3. **前端新 key「cardDraft」，不搭 bootstrap 的车。** 行文案、弹窗标题、空态语义都不同；`runAi` 内 cardDraft 走 `bootstrapDraft(projectId, card.id)` 同一 API，但 sink/action、弹窗 label（「AI 拟稿 · 为「名」立卡（采纳才写入）」）独立。采纳只走 adoptBootstrap 的**有卡分支**（patch-only，永不到达 create 主角卡分支）。
4. **行门控用 charCtx 现成缺口计数。** `role ∈ {配角, 反派} && personaGap + dossierGap + cogGap > 0`；卡满即退场。免费档沿用既有 aiState 统一门控（看得见、点不动）。
5. **usage operation 沿用 `settings_char_bootstrap`。** 同一端点同一操作名，llm.log 分诊不新增键值；失败计数同键。
6. **简介未填 400 按角色分文案。** 配角/反派分支：「简介还没写——先去 01 简介写几句，再来立卡」；主角文案一字不动。前端 toast 已有出口语义，spec 场景只约束「带可点击出口的中文提示」。
7. **提示词仓 companion 提交先行合入。** C端 实现可在新模板缺失时仍对主角路径工作，但配角路径会解析失败——故 tasks 把提示词仓提交（模板＋manifest＋sync 重生成＋仓内 gates）列为 C端 后端分派的前置；发布走仓内 publish.py 常规链，随下个发版带出，C端 dev 验证以 dev 源/重发布后的 pack 确认加载到新模板。

## Risks / Trade-offs

- [新模板首次真书质量未知] → 模板沿用主角版已验证的格位口径与铁律骨架，仅角色口径改写；apply 时用现有三桩（角色/世界/主线齐、部分空、全空）各跑一次对拍。
- [端点语义被两路共用，回归互相牵连] → 主角路径的字节级对拍钉子（模板渲染结果不变量）进后端测试；e2e 主角链既有断言不动即回归哨兵。
- [卡区提示行与「无 AI 按钮」拍板的边界] → 提示行纯文案不可点，落 §13 口径（动词、无内部术语），原型与 ADJUSTMENTS.md 登记。
- [旧包/旧 pack 灰度期配角行点了 502] → C端 端点对模板缺失按既有 load_layers 异常路径走 502 文案；发版链保证 pack 与端点同版本带出（c-prompt-pack-delivery 既有契约）。

## Migration Plan

提示词仓 companion PR → C端 实现分支（依赖其合入）→ 原型先行 → 常规四档门禁 → 随发版带出（pack 发布＋打包门禁既有链）。回滚＝前端行门控还原即可整体下线，端点对主角路径不受影响。

## Open Questions

（无）
