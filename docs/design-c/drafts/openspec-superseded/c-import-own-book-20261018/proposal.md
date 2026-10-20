# 导入自有书（c-import-own-book）

## Why

存量作者要把已经写完的书搬进来接着写。今天两条链各缺一半：书架「导入」能带卷/章/正文，但设定几乎为空、导入章是 draft（点续写回第 1 章）；写作工具「拆书」能产出十维设定与逐章材料，但书不带章节、出口是参考材料。作者被迫搬两次，或者拿到一本「有正文没设定」的书。本 change 把两条链接成一条：一次上传 → 确认卷章 → 只导入正文或 AI 拆书 → 开书续写；并把跨章状态、开书幂等、大书、模型/配额前置这些数据正确性问题一并收口。

## What Changes

- 书架「导入」升舱为**三步向导**：①选文件（仅 .txt、单文件 ≤50MB、字数不设上限；格式告知＋检查＋样例＋下载）②确认卷章（左扫描只读／右按章切分：切、挪边界、合并、改名、折叠；卷必须连续，不允许单章跨卷；含章节忽略/删除与结构 risk 确认）③导入方式（直接导入 0 token / AI 拆书；模型门＋书架配额门）。
- **两条路**：
  - **A 直接导入**：立即建书，按第 2 步确认的结构落卷/章/正文；设定留空；导入章为 `imported`（历史章），不是 archived；作者可编辑，续写从 N+1；v1 不支持补拆。
  - **B AI 拆书**：建任务不建书；任务携带确认结构；超过约 60 万字按章边界**分段**拆十维；逐章基线来自拆书卡（设定/关系/伏笔/角色），物品/认知标未提取、可按章补算；书级伏笔台账唯一来源；完成后**开书三态**（确认/进度/回执），作家定书名；导入章 `imported`＋基线，frontier 跳过、story_state 折叠有行章、阶段不计入「待完本」。
- **开书正确性**：原子 claim＋阶段回执（建书/设定/卷纲与基线/章节）＋源文件 sha/parser version；中断可续、已写入不重复；世界设定压缩移出开书（或明确 token 口径）；开书回执列明写入项/未写入项/未提取域。
- **任务可见性**：任务清单按来源分「导入 / 拆书」并支持状态筛选；导入任务无导出；完成态「已完成·待开书」＋主按钮「开书」；交接通知「应用内继续、关闭会中断可从断点续拆」；应用内完成 toast。
- **上限与大书**：50MB 只是文件技术上限，字数不设上限；B 路按段串行、段级续跑、费用/时间按段累加；A 路分批解析/写入、章节列表可搜索筛选。
- **状态与数据口径**：新增 `imported` 章状态与来源标记；章档行加来源/域级未提取标记；章号/标题归一（存储保留卷内号，界面统一全书号；title 不剥序号不入库）；阶段判定排除导入来源的归档章；编辑导入章标 stale 并提示下游影响；作者可单章「归档本章」转 archived。
- **BREAKING**：旧书架导入入口（md/docx、10MB、预览树）取消，新入口仅 .txt；旧 `ImportNovelModal`/`ImportPreviewTree` 退役。已有 `source=import` 的书需要一次性 backfill（imported 状态/章号/基线标记）或明确保留只读，不能继续落第 1 章续写。
- **v1 分期**：A 路先上线（解析器、上限、imported 消费面、结构确认）；B 路后上（逐章基线＋开书状态机必须同批）。模型/配额门、任务分类与开书三态同批。

## Design Impact

- **受影响端**：仅 C端；S端 无改动。
- **受影响屏/弹层**：书架导入弹窗（三步向导）、写作工具任务清单/详情、书内设定页（开书回执）、写作页（续写就绪/bar-here）、归档页（导入章节分组）、预览目录（原文/历史章标签）、开书确认/进度/回执弹窗。
- **对象状态**：章节新增 `imported`（产品文案「原文/历史章」，不计入完本进度）；任务 running/queued/completed·待开书/opened/failed/need_reupload；开书 confirming/opening/partial/done；基线 imported/stale/未提取域。语气词只用 info/ok/warn/err；不新增胶囊形态。
- **两端共享段**：不触碰 base.css 令牌与共享组件词表；复用 `.mcard`/`.notice`/`.pill`/`.dim-row`/`.rail-card` 等既有类。若最终新增「原文/历史章」状态标签或新的步骤条形态，需在 design-system 规格登记，不在前端另造第四种胶囊。
- **原型先行**：C端 设计工件已在本轮产出 `docs/design-c/drafts/ai-novel-c端-导入自有书-原型.html`（实抓当前系统界面）；实现前须迁入 `docs/design-c/prototypes/<screen>.html` 并按 `ADJUSTMENTS.md` 登记偏差。设计侧会话产出，实现侧不得凭空补视觉。
- **文案**：按钮用动词；不出现「门控/就绪度/SSE/基线/imported」等内部术语；用户可见处用「原文/历史章」「拆书」「开书」「章状态草案」等作家语言。需在实现前做一次全量文案替换（原型里「基线」等词属设计口径，落地时替换并登记）。

## Capabilities

### New Capabilities

- `import-own-book`: 导入自有书全链路——三步向导（txt 格式告知/检查、按章切分的卷章确认、章节忽略与 risk 确认）、两条路（直接导入 / AI 拆书，含模型与书架配额门）、导入任务（来源标记、交接/完成确认、无导出）、开书三态与回执、大书分段、导入章 `imported` 状态与逐章基线、与任务/书内页面的状态呈现。

### Modified Capabilities

- `workbench`: `frontier`/`last_write`/「续写」与 bar-here 必须跳过 `imported` 章；导入章编辑不回退续写光标；工作台不再把导入章当「草稿/待确认」。
- `volume-chapter-service`: 卷章结构改为连续切分（切线校验、覆盖 1..N、每卷非空）；章号/标题归一（存储卷内号、界面全书号、title 不掺序号）；章节新增 `imported` 状态与来源；导入建书的卷/章一次成型。
- `chapter-dossier`: 章档行增加 `origin`/未提取域标记；imported 基线补算只刷指定域、不替换已采纳行、不顺手归档；编辑导入章的 stale 与下游提示口径；`story_state` 折叠 imported 有行章；阶段判定排除导入来源的归档章；单章归档转 archived 的轻量路径。
- `chapter-plan-ai`: 拆章素材与「上一章结尾」跳过 imported 章；导入章的章纲/章号显示按全书号；不把 imported 章计入「未确认/待拆」。
- `preview-reader`: 导入章标「原文/历史章」而非草稿；概览计数区分导入章与完本进度；不把 imported 章计入待确认。
- `design-system`: 登记「原文/历史章」状态标签、导入任务三态、开书三态与切分编辑器的状态语言/组件词汇；不得新增胶囊形态或内部术语。

## Impact

- 后端：`deconstruct/`（任务/分段/开书状态机/apply）、`models/deconstruct.py`（source/structure_json/source_sha256/parser_version/open_state/opened_at）、`models/chapter.py`（imported/provenance、章档 origin）、`chapters/`（frontier/status/confirm/unarchive）、`write/story_state.py`、`volumes/service.py`、`novels/router.py`/`importer.py`/`deconstruct/textparse.py`（统一 txt adapter）、`auth_local/deps.py`（配额预检）、迁移/升级 carry。
- 前端：书架导入（新向导替换旧弹窗）、写作工具清单/详情（来源/状态/开书）、工作台（frontier/last_write/树标签）、设定页（回执/状态）、预览（原文标签）、相关 vitest/e2e。
- 提示词仓：MVP 不改卡片契约（物品/认知标未提取）；若后续补提取需跨仓改 `deconstruct-card` 与发包。大书分段不新增模板。
- 数据库：新增列/状态与一次性 backfill（旧 import 书、旧 deconstruct 任务 source=manual）；schema 指纹变化需 carry 用例。
- 破坏性：旧 md/docx 导入入口移除；旧导入书的续写落点与状态需 backfill 或明确只读，发布说明需告知。
- 不在本 change：md/docx 支持、单章任意跨卷、物品/认知全量提取、A 路补拆、逐章重命名/正文预览（二期）、开书进度形态（先实测 p90 再定）。
