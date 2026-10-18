# 设计：导入自有书 · 直接导入（A 路）

## Context

见 `proposal.md`。本设计只覆盖 A 路；B 路（AI 拆书、基线、开书状态机）在 `c-import-deconstruct`，A 路不得依赖其表/字段。

当前实现约束：
- `novels/importer.py` 只认 Markdown，`deconstruct/textparse.py` 认「第X章/回/节」与编码；同一 txt 在两处可能切出不同章。
- `/import/parse|persist` 直接建书，章状态 `draft`，会播种设定；旧 `import_persist` 每卷/每章各自 commit。
- `chapters/frontier.py` 用「首个未归档」＋卷内 `chapter_no`；`is_writable` 对任何有正文的章放行，包括 archived。
- `write/story_state.py` 只折叠 archived；`archive/dossier_router.py` 只在 archived 时返回行/补算入口；阶段/完本用 `archived >= total`。
- 前端 `NovelWorkspace`、`OutlineTree`、`PreviewView` 直接用 `chapter` 卷内号；`hereTarget` 优先 localStorage 会话。
- 当前工作区落后 `origin/main` 61 个提交，实施必须在新 worktree。

## Goals / Non-Goals

**Goals:**

- 一次 txt 上传、冻结 manifest、连续卷结构、A 路原子建书。
- 历史章用不可变 `origin=import` 派生，不新增 status 值；续写永远全书 N+1。
- 全书号 `global_no` 派生，所有界面/提示词统一。
- 完本/阶段改用作者章分母；只有导入章的书永远写作中。
- v1 不删落库章；词表冻结；旧 md/docx 入口退役与旧书 backfill。

**Non-Goals:**

- AI 拆书、逐章基线、开书状态机、大书分段（B 路）。
- 落库后删章、逐章重命名/正文预览（二期）。
- 物品/认知提取、提示词仓改动、md/docx 转换。

## Decisions

### D1. 历史章＝`origin=import` 派生，不新增 status

**决定**：`chapters` 加 `origin`（`authored|import`，不可变）与 `imported_at`；`status` 保持 draft/confirmed/archived。谓词集中到 `chapters/lifecycle.py`：

```text
is_historical(ch)            = origin == 'import' and status != 'archived'
is_imported_archived(ch)     = origin == 'import' and status == 'archived'
counts_toward_completion(ch) = status == 'archived' and origin != 'import'
```

- 历史章可编辑、可确认章纲、可归档；confirm/unarchive/版本恢复只改 status，origin 不动，因此历史语义稳定。
- `frontier` 跳过 historical；`is_writable` 保留「有正文可写」，另补 archived 只读守卫（spec 既有承诺）。
- API 可派生 `historical: true` 供前端使用；DB 不出现 `status=imported`。
- 旧书 backfill 只写 origin，不改 status，回滚时旧代码可忽略新列。

**备选**：保留 `status=imported` 并给 confirm/unarchive/revert/rewrite/version-restore 六个入口加矩阵——否决，入口多、漏一个就回退到第 1 章。

### D2. 全书号 `global_no` 派生

**决定**：`chapters/numbering.py::global_no(volumes, chapters)` 按卷序＋卷内序累计；`/frontier`、`/volumes`、`/tree`、章详情返回；待写占位 `global_no = 主线活动章数 + 1`。存储保留 `chapter_no/ref`，不重排。

- 前端删除 `last.chapter + 1`、`chapters.length + 1` 等本地算法；新建章默认标题用 `global_no`。
- ghost 分支不计入；忽略/删除只发生在导入前，活动章序连续。
- 章标题剥「第X章/回/节」序号，展示时拼一次；卷名同理。

**备选**：把全书号落库——否决，跨卷插章/回退会触发重排，破坏 last_write 与归档引用。

### D3. A 路原子 writer

**决定**：新增 `novels/import_writer.py::persist_import()`：

```text
async with session.begin():
  existing = await find_by_import_token(token)
  if existing: return existing
  book = Novel(source='import', import_kind='direct', import_token=token)
  add/flush
  for vol in structure:
    upsert volume; for active chapter:
      chapter(origin='import', chapter_no=..., ref=..., title=...)
      content(prose slice, word_count, has_prose=True)
  commit
```

- 不复用 `create_project`/`save_chapter`（内部 commit）；批量 `add_all`，显式派生字段。
- `import_token` 唯一；命中直接返回，不再检查配额（重试不 403）。
- 正文从 `import_sessions` 的 manifest 区间切片；HTTP 只传 `import_id + name + volumes + token`。
- 先按单事务实现并压测 240 章；若实测写锁/耗时不可接受，再加「隐藏 staging 书 + 原子发布」，但 v1 默认单事务。

**备选**：复用旧 `import_persist` 并逐章 commit——否决，失败留半本书，重试重复。

### D4. 消费面收口与完本分母

**决定**：所有跨模块判断只调用 `chapters/lifecycle.py`；完本/阶段使用作者章分母。

| 消费面 | 改法 |
|---|---|
| `chapters/frontier.py` | 首个非 archived、非 historical；返回 `global_no`；全导入/全归档→待写 N+1 |
| `write/prompt_sources.py` | 上一章 historical 用摘要/首段，不返回「上一章未归档」 |
| `volumes/service.py::resolve_prev_ending` | archived 或 historical 都算实际收尾 |
| `chapters/ai_plan.py` | 历史上下文集合与当前卷配额分离；历史章不占配额/末章；摘要槽与原文摘录分块 |
| `novels/router.py` / `lib/novelStage.ts` | 下发/消费 `authored_total/authored_archived`；阶段用作者章 |
| `works-finish-flow` | finish 守卫 `authored_total>0 && authored_archived==authored_total` |
| `preview-reader` | 标签「原文」；计数桶 archived/原文/草稿/拟定；完本进度只用作者章 |
| `novel-workspace` | 四态机加 authored 参数；只有导入章=写作中 |

- `total_chapters` 仍含历史章；`total_archives` 只用于展示；`authored_*` 用于阶段/完本。
- 新增 delta：`works-finish-flow`、`novel-workspace`、`prose-writing`、`volume-outline`、`volume-chapter-index`（原 proposal 未列）。

### D5. 结构与导入前修正

- 结构契约 `volumes: [{title, chapter_from, chapter_to}]` 覆盖活动章 1..M；缺口/重叠/空卷 400；前后端共享 fixtures。
- 第 2 步支持「不导入此章」与撤销；risk 勾选；warn 显示具体问题但可继续；0 章/单章 >60 万在 A 路可导入但提示（B 路禁用）。
- v1 落库后不删章；提供「删除本书重新导入」。
- manifest 冻结：第 1 步解析一次，`import_sessions` 存 manifest + source + sha + TTL；A 路落库不再重解析。

### D6. A 路 UI 与词表

- 三步向导：Step 1 只收 txt/格式样例/检查；Step 2 左只读扫描、右卷卡（切/挪边界/合并/改名/折叠/不导入）、risk；Step 3 只显示直接导入（AI 卡「即将开放」不可点），显示 0 token/本机处理/设定留空。
- 成功落点：工作台第 N+1 章待写位；主 CTA「开始写第 N+1 章」；次 CTA「去核对设定」；右侧「补主线 / 补当前卷卷纲」清单（A 路无 mainplot）。
- `hereTarget` 会话优先；树「继续写作」独立 `continueTarget` 恒 N+1；导入书不自动聚焦第 1 章，last_write 只在真实输入时记录。
- 词表冻结：直接导入（只带正文）/原文/每章摘要/补齐本章/10 项拆书产物/手动拆书/回到上次写作/写下一章；内部词不上屏。
- 组件只用既有 `.mcard/.notice/.pill/.field/.textarea/.btn/.dim-row`；新增「原文」用既有 `.pill` status；不新增胶囊/emoji/字号。

### D7. 迁移与旧入口

- 新增列全部 `server_default`：`chapters.origin='authored'`、`projects.import_kind='authored'`；`import_token` 唯一可空；`import_sessions` 新表。
- carry 完成后按 `app_meta.import_backfill_v1` 幂等回填：`source='import'` 且 import_kind 空 → legacy；其章 origin=import、imported_at=created_at；status 不改。
- 旧 `/import/persist` 前端不再调用；为兼容历史脚本/测试保留端点，但写入 `origin=import` 与 `import_kind=legacy`，不再造「无来源的 draft 书」；md/docx 前端入口明确暂不支持。
- 回滚：旧版本+旧库可启动；新库多出的列被旧代码忽略，status 未变，数据不损坏；发布前备份。

### D8. 测试策略

- 契约测试：同一 manifest 的 A 路结构/ref/title/origin/global_no 逐字段断言。
- 生命周期矩阵：status × origin × frontier/is_writable/stage/preview/finish 全组合。
- 原子 writer：240 章成功、第 120 章失败零残留、同 token 重试同书。
- 迁移：旧 import 书 carry→backfill→续写 43/预览原文/完本阶段不变。
- 前端：三步向导、ignore/risk、续写 43、树/预览原文、last_write 不污染、任务页旧 mock 更新。
- 设计门禁：prototype、design:lint、design:check、tsc；不触共享段，`design-cross` 按 proposal 判定不适用。

## Risks / Trade-offs

- **origin 派生需要全站改判断** → `lifecycle.py` 单源 + 静态扫描 `status == "archived"` + 端点矩阵。
- **单事务大书写锁** → 先压测 240 章；超预算再上隐藏 staging + 原子发布，不改变外部语义。
- **旧书 backfill 时机** → carry 后按 app_meta 标记执行，不在首启无条件跑；加真实旧库演练。
- **A 路没有主线/卷纲** → 成功页给补主线/卷纲清单，不假装可立即拆章。
- **旧 md/docx 用户** → 发布说明与弹窗明示「暂不支持、不提供转换」；旧书仍可读。

## Migration Plan

1. 新 worktree 从 `origin/main`；记录基线。
2. schema/backfill → manifest/结构/global_no → 原子 writer → lifecycle/消费面 → 向导/A 路落点 → 测试。
3. 发布说明：仅 txt、md/docx 退役、旧书回填。
4. 回滚：旧版本+旧库可启动；新库先备份。

<!-- 无开放问题：A 路 5 个方向已拍板；B 路问题不在本 change。 -->
