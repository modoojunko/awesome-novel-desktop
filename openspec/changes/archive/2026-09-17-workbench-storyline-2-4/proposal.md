## Why

`storyline.html` 写作工作台原型的主体行为（章节状态机、回退与旧稿支线、双向关系图、本章文风影子、按回合剧情推演、提示词六来源）已在实现侧分四期落地并合入 main（#383/#386/#388/#389/#390/#392/本变更），但 openspec 只归档过「行头归一＋续写」（workbench-appbar-resume）与一期收尾提案（archive-reconcile 在途），二三/四期行为没有任何 spec 锚点——原型即事实源，却无契约可查。本变更把二三/四期行为一次性回填为 spec 增量并随归档固化。

## What Changes

- **主线端点与排队门禁（二期）**：新增 `GET /api/novels/{id}/frontier`（主线端点＝首个未归档章；全书归档→待写占位含下一章号）；正文 PUT 与 AI 写章端点对非 frontier 章返回 409（「还不能写这一章——先完成前面的章节」）；旧稿支线（ghost）章一律只读（409「旧稿支线只读」）。bar-here 主线定位由「最新归档章」切换为 frontier 口径。
- **回退与旧稿支线（三期）**：新增 `POST /api/novels/{id}/chapters/{ref}/revert`——主线截断到该章，其后章节转旧稿支线（`chapters.ghost_of` 记来源章号，只读保留），其派生数据（出场引用状态变化、来源章关系、本章伏笔留痕、收尾提案行、版本快照）按章序清除；`GET /api/novels/{id}/ghosts` 列支线章。工作台「操作」页签回退卡承接（二次确认，不可撤销）。
- **角色关系页签（四期）**：`GET /api/novels/{id}/characters/graph` 汇总全书关系为图数据（节点/边/孤立点）；工作台新增「角色关系」页签，SVG 定距圆布图渲染（与 storyline.html 同款确定性布局），边标签 `关系类型 · 立场`，附文本清单兜底。
- **本章文风影子（四期）**：`chapters.style_shadow` JSON 列（原表加列，零新表）；三端点 `GET .../style-shadow/baseline`（全书基线只读＋本章影子）、`PUT .../style-shadow`（形状清洗：非 dict 行与全空行丢弃、维度字符串化、值不脱空格）、`POST .../style-shadow/suggest`（PRO 门控＋本书模型门控＋按真签名记账；读基线＋本章章纲产出行级建议，不落库）；写章提示词量化基线段按行覆盖（影子行渲染为「约 X（本章覆盖：理由）」）；「文风」页签（PRO）承接展示与逐条采纳。
- **剧情推演（四期尾）**：新增 `POST /api/novels/{id}/chapters/{ref}/simulate`（PRO 门控＋本书模型门控）——AI 以上一章结尾为起点、按本章章纲关键事件产出 2-4 个回合（每回合含关键事件/在场/落下，以及顺、拗两条走法结果句）；调用失败或产物不合格回落原型同款确定性推演（关键事件环＋模板走法，`source` 字段标注），保证弹窗永远可用。工作台章纲页签「剧情推演」入口（PRO）打开弹窗：按回合逐步展开、每回合先定走法再推进、走完「按这条走法收进章纲」（写 `memo.reader_expectation.strategy`，走法行＝任一回合一拗→中途先接一次意外）。推演产物不落库。
- **提示词六来源展示（四期尾）**：新增 `GET /api/novels/{id}/chapters/{ref}/prompt-sources`——复用写作侧同一套组装链（build_chapter_context＋同款渲染函数），返回六处来源（全书设定 / 大纲·卷纲 / 本章章纲 / 全书文风＋本章调整 / 伏笔进展·截至上一章 / 本章涉及角色）的只读投影（label/chars/preview/empty）。「提示词」页签在既有编辑区上方展示「组装来源」chips 与来源清单（含未填标注），行序与标签固定。
- 退役：bar-here 的「最新归档章」口径（由 frontier 取代）。

## Capabilities

### New Capabilities

- `plot-sim`: 按回合剧情推演契约——simulate 端点门控与素材口径、AI 产物清洗与确定性兜底（source=ai|fallback）、回合结构与走法定形（顺/拗、label/out 由后端出）、产物不落库、收进章纲写预期策略的走法行口径。

### Modified Capabilities

- `workbench`：bar-here 主线端点切换为 frontier 口径；新增「章节状态机排队门禁」（非 frontier 章正文只读且写请求 409）；新增「回退与旧稿支线」（操作页签回退卡、ghost 章只读）；新增「角色关系页签（全书关系图）」；新增「文风页签（本章影子）」与「章纲页签剧情推演入口」的挂载契约。
- `style-quant`：新增「本章文风影子」需求——`chapters.style_shadow` 存储与三端点行为、写章提示词按行覆盖渲染（「本章覆盖」标注）、免费可写门禁现状（PUT 不挂 AI 门控）。
- `chapter-data`：`chapters` 表新增 `style_shadow`、`ghost_of` 列的导出/导入语义（加键兼容）。
- `prompt-crafting`：新增「组装来源只读展示」需求——prompt-sources 六来源投影与「提示词」页签展示。

## Design Impact

- **受影响端**：C端（工作台 bar-here／章纲／正文／文风／角色关系／操作页签与剧情推演弹窗）。S端无改动。
- **受影响屏/弹层**：书工作台（六处页签行为＋主线定位）＋「剧情推演」弹窗（新增，storyline.html sim modal 复刻）。
- **对象状态**：无新语气档——沿用 info/ok/warn/err（草稿/已归档/只读/待定走法）；「旧稿支线」为既有「只读」语义的承载者（ghost 章横幅复用只读家族）。
- **共享段**：未触碰（全部样式落在 `.wb` 屏级作用域与弹窗版式内）→ 免 design-cross。
- **原型先行**：已由实现侧完成——`docs/design-c/drafts/storyline.html` 为行为事实源；`prototypes/book.html` 与 `ADJUSTMENTS.md` 随各期登记（#24-#26 等）。
- **设计工件**：实现侧自查（按 storyline.html 逐段移植，弹窗文案逐字对齐）。

## Impact

- 后端：`chapters/frontier.py`（新）、`chapters/router.py`（frontier/ghosts/revert 端点＋prose PUT 门禁）、`write/router.py`（AI 写章门禁）、`write/style_shadow.py`（新）、`write/plot_sim.py`（新）、`write/prompt_sources.py`（新）、`write/chapter_writer.py`（影子注入）、`settings/render.py`（quant_section shadow 参数）、`models/chapter.py`（style_shadow/ghost_of 列）、`models/character.py`（origin_chapter_id）、`main.py`（幂等 ALTER 与路由挂载）。
- 前端：`components/novel/workbench/`（SimModal/PromptPane/StyleShadowPane/RelationsGraphPane/ReconcilePane/OgPane/ChapterWorkspace）、`components/novel/NovelWorkspace.tsx`（bar-here frontier）、`lib/plotSim.ts`、`lib/promptSources.ts`、`design/book.css`。
- 接口：新增 frontier/ghosts/revert/style-shadow×3/plot-sim/prompt-sources/graph 端点；既有章写接口新增 409 语义（非 frontier/ghost）。
- 兼容性：加列走幂等 ALTER；`chapter_reconcile` 与新列不随导出包（style_shadow/ghost_of 随章档案导出——见 chapter-data 增量）。
- AI 成本：simulate/suggest 均走本书模型（用户自配 Key），失败路径不记账（调用未发生）或留痕（调用已发生）。
