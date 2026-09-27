## Context

拆卷/拆章 AI 素材拼装共享 `volumes/ai_plan.py` 的 `_book_material`（拆章经 `chapters/ai_plan.py::_chapter_material` 复用）；世界块由共享零件 `settings/world_model.py` 渲染——`WORLD_BLOCK_BUDGET = 600` 焊死在 `render_world_block` 内部，`world_summary_text(…, char_budget=1200)` 的参数是死的（内部先按 600 截，外层二次切片永不生效）。真书实测（用 backend venv 直接渲染）：三家势力只进一家，从略注混称"世界细节"。拆卷素材另缺已拆卷清单（卷 4/卷 5 同走向重抽实锤）；拆章素材现状完全没有世界块。决策口径见 `docs/design-c/drafts/提示词素材给量-决策记录.md`（已拍板：设定侧信息不设预算）。

## Goals / Non-Goals

**Goals:**
- 世界块在拆卷三端点与拆章素材中全量渲染；渲染预算参数修活；从略注按类别计数。
- 人物块改全名单一行卡（退役 6 张×80 与聚光单换位）。
- 新增已拆卷清单（options/expand）与无卡出场名单派生块（options/expand 全书、拆章本卷）。
- 已知实体集合（比对单源）纳入无卡名单名字。

**Non-Goals:**
- 档案级深卡（认知六层等）进素材（另行立项）。
- 写正文（`prompt/context.py` 的 600 现状）与设定页五体检（`settings/ai_router.py`）的预算口径（本 change 只修活参数，不改它们的传参；放宽与否各自动评）。
- 章纲起草（`outline_draft`）素材、主线散文与势力表两套词汇的数据对齐、D20 人物引入精盘、D21 重抽排除。

## Decisions

1. **预算参数修活，不动默认**：`render_world_block(raw, char_budget=None)`——`None`＝不截；`world_summary_text` 透传；拆卷/拆章调用传 `None`（全量）。写正文与设定体检不改传参（行为不变），是否放宽由各自后续 change 决定。备选"直接删预算"被否：写正文链的紧块是当初有意设计，且 world-settings 规格钉了"截断以整条为单元"语义，保留截断能力只放宽调用方侵入最小。
2. **从略注按类别**：条目装箱跳过时按 `势力/历史与旧账/世界细节` 分别计数输出（"另有 N 个势力从略"）。world-settings 规格只钉"显式标注从略数量"，按类别是实现细化，无需 delta。
3. **全名单一行卡格式**：`- 名字（定位）：一句人设≤80`，角色表全量、主角置顶（沿用现有排序），**无数量上限、无聚光**——聚光单换位机制（`_book_material` 的 chosen/in_view 逻辑）整体删除。排序＝主角置顶、其余按角色表 `seq`；`_chapter_material` 为聚光构造的 spotlight 拼接（卷纲三字段扫描）属死代码，一并删除。备选"保留聚光作为排序加权"被否：全量下聚光无意义，留徒增复杂。
4. **已拆卷清单只进 options/expand**：一行＝`卷N·标题｜主旨｜坎：类型·一句话｜卷末：落点`，字段直接取卷行，主旨／坎一句话／卷末各截 ≤60 字（行内格式约束，非预算）；expand 排除目标卷自身（防把本卷当成"上一卷的走向"）；check 不带（本卷卷纲在手，递进判据已有上一卷对抗物）。不改八条硬规则——跨卷走法差异的引导若后续需要，属 rules 单源改动，另评。
5. **无卡名单为派生块，零新存储**：查 `chapter_characters` JOIN `chapters`（`ghost_of IS NULL`），名字去重保序＋章号列表，单条 JOIN 聚合（防 N+1），与 `_aggregate_cast` 同口径；拆章取本卷、拆卷取全书已拆章。该名单同时并入越纲对拍的已知侧（`known_entities`）；名单为空时整块省略（沿用 `_blocks` 空块跳过惯例）。
6. **拆章世界块追加为 ⑩，不打乱既有编号**：chapter-plan-ai 的位置感知契约与 volume-plan-ai 的跨规格引用（⑥ 聚光）都按号引用，重编号的连带改动远大于收益；铁律 ⑦ 保持原位。素材顺序对模型注意力的影响以块标题显式化补偿。
7. **对拍与 fixture 同批更新**：`test_volume_plan_t1_fixtures` 等素材断言、"世界摘要 ≤1200"相关断言、`volume_rules` 对拍三件套均按新契约更新；`_blocks`/`_blocks_chapter` 新块插入位置照 spec 顺序表。拆章模板 `chapter_split.prompt` 与卷级三模板均**不改**——新块经 `<<material_blocks>>`/素材占位符吸纳，rules 对拍三件套不受影响。
8. **死参数修活的连带行为变化（接受）**：`world_summary_text` 参数修活后，`settings/ai_router.py` 五处设定体检从「名义 1200／实际 600」变为「真实 1200」——这是修复死参数的必然结果，体检只增信息不减，判为可接受改进并带回归确认项；写正文（`prompt/context.py` 走 `render_world_block` 默认 600）不受影响。

## Risks / Trade-offs

- **提示词变长**：全量世界块＋全名单使 system 增大（估算：本书世界块 544→约 1.1k 字；41 人名单约 1.5k 字）。输入 token 成本可忽略；注意力稀释风险用块标题与顺序缓解（人物块紧邻"申报对拍"用途）。
- **无卡名单噪声**：旧稿实验留下的无卡怪名会进素材——已用 `ghost_of IS NULL` 剔支线；主线里的龙套名属真实上下文，保留。
- **聚光退役的行为变化**：6 张时代"点名者挤位"的隐性保障消失，但全量下人人都在包内，覆盖只增不减。
- **重抽同走向**：已拆卷清单让模型"看得见"，但不保证不再重抽——批间防撞归 D21（独立 change），本 change 只供料。
