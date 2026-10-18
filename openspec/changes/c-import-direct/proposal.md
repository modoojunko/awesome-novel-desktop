# 导入自有书 · 直接导入（c-import-direct）

## Why

存量作者要把已经写完的书搬进来接着写。当前书架导入能带卷/章/正文，但章状态是 `draft`、设定被模板播种、续写会回到第 1 章；而且它只认 Markdown，和拆书 txt 解析器各切一套章节边界。先把「直接导入」做成一条完整、可验收的链：上传 txt → 确认卷章 → 秒级建书 → 续写 N+1。AI 拆书补设定拆到 `c-import-deconstruct`，本 change 不依赖模型、不产生拆书任务。

## What Changes

- 书架「导入我的书」三步向导（A 路版）：①选文件（仅 `.txt`、≤50MB、字数不设上限；格式告知/检查/样例下载）②确认卷章（连续切分、忽略/删除误识别章、ok/warn/risk）③直接导入（0 token；AI 拆书卡显示「即将开放」不可点）。
- 第 1 步解析产出冻结 manifest（编码、字数、章区间、卷范围、sha、parser_version）；A 路落库按 manifest 切片，不再重复解析源文件。
- 章节新增不可变 `origin`（`authored|import`）与 `imported_at`；**不新增 `status=imported` 值**。历史章由 `origin=import && status!=archived` 派生，可编辑、可归档、跳 frontier、不计完本。
- 全书章号 `global_no` 派生（卷序累计），不落库、不重排 ref；frontier/树/预览/新建章统一使用。
- A 路新增事务级 writer：书/卷/章/正文/`import_token` 一次提交，失败整笔回滚；`seed_settings=false`，只把第一章前 200 字机械填入简介并标「自动识别」，题材留空。
- 消费面收口：frontier、续写、章节树、预览、拆章素材、上一章上下文、跨卷实际收尾、完本阶段全部按 origin/global_no 统一；完本分母改为 `authored_total/authored_archived`，只有导入章的书永远「写作中」。
- v1 只支持导入前忽略/删除章节；落库后不提供删章，提供「删除本书重新导入」出口。
- 作者词表冻结：直接导入（只带正文）、原文、10 项拆书产物、每章摘要、补齐本章等；内部词不上屏。
- **BREAKING**：旧 md/docx 导入入口退役，只收 txt；旧 `/import/persist` 不再作为前端入口；已有 `source=import` 的书 backfill 为 `origin=import`。

## Design Impact

- **受影响端**：仅 C端；S端 无改动。
- **受影响屏/弹层**：书架导入向导、写作工具任务清单（A 路无任务，保留 B 路占位）、写作页（续写/树/预览原文标签）、设定页（简介自动识别提示）。
- **对象状态**：章节 `origin`/`imported_at`；书 `import_kind=direct`、`import_token`；无新章节 status；无章节 `imported` 值。语气词只用 info/ok/warn/err。
- **两端共享段**：不触碰 `base.css` 令牌与共享组件词表；复用 `.mcard/.notice/.pill/.field/.textarea/.btn/.dim-row` 等既有类。新增「原文」标签走既有 `.pill` status 家族，需在 design-system 登记，不新增胶囊形态。
- **原型先行**：原型在 `docs/design-c/drafts/ai-novel-c端-导入自有书-原型.html`（实抓当前系统）；实现前迁入 `docs/design-c/prototypes/` 并在 `ADJUSTMENTS.md` 登记。
- **文案**：按钮用动词；不出现 `imported/frontier/baseline/pipeline`；A 路成功主 CTA「开始写第 N+1 章」，并给「补主线 / 补当前卷卷纲」清单（A 路没有 mainplot）。

## Capabilities

### New Capabilities

- `import-own-book`: A 路全链路——txt 三步向导、连续卷章确认与忽略/risk、直接导入、历史章 origin/global_no、原子落库、费用/隐私告知、A 路成功落点与词表。

### Modified Capabilities

- `workbench`: frontier/续写/bar-here 跳过历史章；global_no；章节树「继续写作」落 N+1。
- `volume-chapter-service`: 连续结构校验、原子导入 writer、origin/imported_at、global_no、标题归一；落库后不删章。
- `volume-chapter-index`: `chapters.origin/imported_at`、`books.import_kind/import_token`、`import_sessions` schema 与旧书 backfill。
- `chapter-plan-ai`: 历史章作为历史上下文进拆章素材；不占当前卷配额/末章；无摘要用正文首段。
- `preview-reader`: 目录加「原文」标签；概览拆 authored/imported 计数；完本进度排除 origin=import。
- `novel-workspace`: 四态 view machine 改用 authored_total/authored_archived；只有导入章的书=写作中。
- `works-finish-flow`: finish 守卫改用 authored 分母；导入章归档不满足完本。
- `prose-writing`: 上一章是历史章时提供摘要/原文摘录，不返回「上一章未归档」。
- `volume-outline`: 跨卷实际收尾包含历史章。
- `design-system`: 登记「原文」状态标签与 A 路词表；不新增胶囊形态/内部词。

## Impact

- 后端：`chapters/`（origin/global_no/lifecycle/frontier）、`novels/import_writer.py`、`novels/router.py`、`novels/importer.py`、`deconstruct/textparse.py`（作为 txt parser）、`volumes/service.py`、`write/prompt_sources.py`、`models/chapter.py`、`models/novel.py`、迁移/回填。
- 前端：书架导入向导、工作台树/预览/续写、设定页、相关 vitest/e2e。
- 数据库：新增 `chapters.origin/imported_at`、`books.import_kind/import_token`、`import_sessions`；旧导入书 backfill；无新 status 值。
- 提示词仓：本 change 不改。
- 不在本 change：AI 拆书、逐章基线、开书状态机、大书分段、落库后删章、逐章重命名/预览、物品/认知提取、md/docx。
