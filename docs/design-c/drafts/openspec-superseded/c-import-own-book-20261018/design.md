# 设计：导入自有书

## Context

本 change 是跨 `novels`、`deconstruct`、`chapters`、`archive`、`write` 与前端书架/工作台/写作工具的一次贯通改造，动机与范围见 `proposal.md`。当前实现里有四条约束直接决定方案：

1. **两条解析链已经分叉**：`client/backend/novels/importer.py` 只认 Markdown 的 `#`/`##`，`client/backend/deconstruct/textparse.py` 认「第X章/回/节」、编码探测与 6000 字拆书卡喂料。书架导入走前者，拆书走后者，同一份 txt 在两处的章节边界可能不同。
2. **两条落库链各缺一半**：`novels/router.py` 的 `/import/parse|persist` 直接建书、章状态为 `draft`、设定播种；`deconstruct/apply.py::import_book` 会按拆书 structure 建卷、`create_project` 播种设定，并可能在开书时调用 AI 压缩世界设定；它没有章节正文落库，也没有书架配额预检。
3. **章节状态口径是全局的**：`chapters/frontier.py` 把「首个未归档章」当主线端点，`is_writable` 允许任何已有正文的章继续写；`write/story_state.py` 只折叠 archived 章；`archive/dossier.py` 的 `rows_only` 只对 archived 章返回行；前端 `NovelWorkspace` 的 `hereTarget` 也自带一套 frontier/last_write 逻辑。新增 `imported` 状态必须逐面收口，否则会出现「续写回第 1 章」「导入章基线不参与下文」「42 章全归档→待完本」三类错误。
4. **设计门禁**：C端 用户可见改动必须先落 `docs/design-c/prototypes/` 并登记 `ADJUSTMENTS.md`；本次原型已在 `docs/design-c/drafts/ai-novel-c端-导入自有书-原型.html`（实抓当前系统界面），实现前迁移并补齐章节级修正与 risk 状态。S端 无改动，不触碰 `base.css` 共享段（见 proposal `Design Impact`）。

约束：单用户桌面应用、SQLite、C端 React 19；拆书提示词仓本次不改（物品/认知不新增模板）；50MB 是文件技术上限，字数不设上限；所有验证使用本会话独立栈，不复用主检出或并行会话的服务（AGENTS 规则）。

## Goals / Non-Goals

**Goals:**

- 一次 txt 上传、一套解析 manifest、一套连续卷结构，A/B 两路共用。
- `imported` 章成为一等历史状态：可编辑、可归档、跳 frontier、进 story_state、不计完本；所有消费面有可执行的回归钉。
- B 路开书可原子 claim、阶段回执、断点续写、源文件 sha 校验；开书本身不调用模型。
- 大书（>约 60 万字）按章边界分段拆、段级续跑、按域合并；A 路大书分批写入。
- 任务来源/三态/开书出口、模型/配额前置在创建前可见。
- 旧 md/docx 入口退役，已有导入书 backfill 到 `imported`，不再落第 1 章续写。

**Non-Goals:**

- md/docx/epub 支持与格式转换；单章任意跨卷；逐章重命名/正文预览（二期，proposal 已列为不在本 change）。
- 物品/认知的全量提取与提示词契约改动；A 路补拆。
- 手工拆书任务的建书/导出出口改造（保持现状，只按 `source` 分型）。
- ¥ 费用换算（只给 token/时间与「由你的模型服务商计费」）；S端 改动；跨端共享段改动。

## Decisions

### D1. 单一 txt 解析器与冻结 manifest

**决定**：以 `deconstruct/textparse.py` 为唯一 txt 解析器（编码探测、卷/章标题、章节切分）；`novels/importer.py` 退化为适配层，不再维护第二套章节正则。第 1 步解析一次，产出并持久化 **manifest**：

```json
{
  "schema": 1,
  "parser_version": "textparse-2026-10",
  "encoding": "utf-8",
  "source_sha256": "…",
  "char_count": 316000,
  "chapters": [
    {"idx": 1, "source_no": 1, "title": "沉船", "volume_title": "第一卷 沉船",
     "char_start": 0, "char_end": 8200, "text_sha256": "…"}
  ],
  "volumes": [{"title": "沉船", "chapter_from": 1, "chapter_to": 24}],
  "warnings": [], "risk": "ok"
}
```

- `chapters[].idx` 是**活动章序**（1..M，忽略/删除后重排）；`source_no` 保留原文序号用于显示与排错；`char_start/end` 指向源文件解码后的字符区间，落库时按区间切片，避免把 180 万字正文塞进 manifest。
- manifest 在第 1 步后存临时导入会话（A 路）或任务（B 路）；开书/落库使用 manifest，不重新解析源文件。这样 parser 升级不会让已拆的卡与章节错位。
- `source_sha256` 在 B 路开书前复核；不一致返回 `need_reupload`，不写半本书。
- 只收 `.txt`；50MB 在 HTTP 层拒绝；不设字数上限。解析一次性读入（≤50MB），按行切分；大书后续的批量与分段在落库/拆书层做，不在解析层设上限。

**备选**：保留两套 parser 并对齐正则——否决，现有 Markdown/标题口径已经漂移，双维护必再分叉；让拆书解析器兼容 Markdown——否决，第一期明确只收 txt，兼容会扩大测试面。

### D2. 连续切分的结构契约与共享校验

**决定**：第 2 步的输出固定为：

```json
{"volumes": [{"title": "沉船", "chapter_from": 1, "chapter_to": 24},
             {"title": "灯下", "chapter_from": 25, "chapter_to": 42}]}
```

- 范围是**活动章序** 1..M 上的闭区间；`chapter_from` 必须等于上一卷 `chapter_to+1`，首卷从 1、末卷到 M；每卷 ≥1 章。
- 前端只提供「在第 X 章后分卷 / 少一章 / 多一章 / 合并到下一卷 / 改名 / 折叠 / 忽略或删除章」，不提供拖拽单章或复选框任意归卷；后端 `volumes/service.py` 增加同一套校验，任何缺口/重叠/空卷 400，且不部分建书。
- 卷号按位置分配；`title` 存去掉「第N卷」序号后的卷名（空则 `第N卷`）；显示时统一拼「第N卷 · 卷名」。章标题同样在入库前剥掉「第X章/回/节」序号，显示时拼一次；归一函数前后端共用 fixtures 对拍。
- 忽略/删除发生在结构确认之前：manifest 的活动章序重排，结构范围随之重算；落库只处理活动章。

**备选**：按章传 `volume_ref` 任意归属——否决，会产生不连续卷，且与「卷是连续段」的产品口径冲突；允许单章跨卷——否决，存储与目录排序都会出现无法解释的洞。

### D3. `imported` 状态、来源标记与消费面收口

**决定**：章节新增两个正交字段：

- `status = imported`：当前状态，表示「来自作者原文、尚未归档」；作者编辑后仍是 imported；单章归档后变 archived。
- `origin = import`：不可变来源，导入落库即写；归档后仍保留。它解决「导入章归档后不计入待完本」——阶段判定不能只看 status。

新增集中判据（后端 `chapters/scope.py` 或同层 helper，前端同义函数）：

- `is_historical(ch) = ch.status == "imported"`
- `is_imported_origin(ch) = ch.origin == "import"`
- `counts_toward_completion(ch) = ch.status == "archived" and ch.origin != "import"`

逐面改动：

| 消费面 | 现状 | 改为 | 回归钉 |
|---|---|---|---|
| `chapters/frontier.py` | 首个未 archived 章；全归档→待写 N+1 | 首个 `status not in (archived, imported)`；全归档/全导入→待写 N+1 | 42 章 imported → frontier 43；导入章不抢端点 |
| `is_writable` | 有正文的章可写；未来无正文章 409 | 保持；imported 有正文故可写；不新增历史章只读 | 导入章 PUT prose 200；未来无正文章 409 |
| 前端 `hereTarget`/「续写」 | 会话→frontier→首章 | 会话优先（允许停在编辑中的导入章）；无会话→frontier；章节树「继续写作」单独用 frontier→N+1 | 导入书首次续写 43；编辑导入章后树入口仍 43 |
| `write/story_state.py` | 只折叠 archived | 折叠 archived 或 imported 且存在 accepted 基线行；stale 章跳过并注明 | 导入基线进第 6 章素材；A 路无基线不出空段 |
| 阶段/完本 | archived 计数 | `counts_toward_completion` 排除 `origin=import` | 42 章归档仍「写作中」 |
| `preview-reader` | 拟定/草稿/已归档 | 加「原文」；计数加原文；完本进度排除 | 42 章全 imported 概览 原文 42、已归档 0 |
| `chapter-plan-ai` | 已拆章节/上一章 | imported 作为历史上下文进 ③/⑧；不计当前卷配额/末章 | 拆 43 时 ③ 含 42 章摘要；43 是唯一待拆 |
| `chapter-dossier` | `rows_only` 只 archived | imported 有基线行时返回；行带 `origin=import` | 导入章基线可读；补算不替换 |
| 章节树/归档页 | draft 草稿 | imported 标「原文」；归档页标「已导入基线（可复核）」/「已导入（未归档）」 | 不出现「草稿」误标 |
| `confirm/delete/save/versions` | 只认 draft/archived | imported 按可编辑历史章处理；删除走既有引用清理 | 保存/删除/版本链不 500 |

**备选**：复用 archived + 标记 `imported=True`——否决，会让 frontier/story_state/完本全部把历史章当已归档，且作者无法区分「导入」与「完本归档」；用 draft + `origin=import`——否决，frontier 会停在第一张导入章，续写回第 1 章的口径无法修。

### D4. 逐章基线的来源、覆盖与补算

**决定**：B 路开书时从拆书阶段既有 `dims_json.cards.entries` 逐章落基线，**不做 42 次新提取**：

| 拆书卡内容 | 落点 | 标记 |
|---|---|---|
| 设定变化 | `chapter_setting_changes` | `origin=import`, `status=accepted` |
| 关系变化 | `chapter_relation_changes` | 同上 |
| 伏笔动作 | 书级伏笔台账的章号锚定（不建逐章副本，台账唯一来源） | 锚定来源 `import` |
| 出场角色 | `chapter_characters` | 同上 |
| 物品/认知 | 不落行，记覆盖为 `not_extracted` | 回执明示可补算 |

- 新增 `chapter_dossier_coverage`（或章级 JSON 列，二选一，优先表）：`chapter_ref`, `source_card_id`, `domains_json`（setting/relation/hook/cast 为 `full|partial`，item/cognition 为 `not_extracted`），`char_from/char_to`（拆书卡只读首尾约 6000 字的范围）。A 路不写 coverage（无基线）。
- `archive/dossier.py` 的读取入口放宽：`rows_only` 在 `status in (archived, imported)` 时返回，imported 行只返回 `origin=import` 的 accepted 行；作者否决的行不消费。
- 「补算」新增 `fill_missing` 模式：只对指定域调用既有提取，结果只补该章缺失/未提取的域；**不替换**已 accepted 行、**不**把章置 archived、**不**触发下游 stale 级联。补算产物仍走既有待确认/采纳（如果选择直接采纳，必须在回执与按钮文案明示）。
- 编辑导入章正文/标题：只置该章 `dossier_stale`，不删基线、不自动全废；story_state 跳过并在块头注明；章档页签给「补算本章」入口。是否批量补算由作者决定。
- 单章「归档本章」：有基线默认沿用基线（不再调用 AI），显式「重新提取」才走正常四域提取并覆盖；无基线走正常提取。归档后 status=archived，origin 仍为 import，阶段不前进。

**备选**：开书时对每章跑一次提取——否决，成本 42 次调用且与「拆书卡已有产物」重复；物品/认知伪造空行——否决，会冒充已提取，误导 story_state。

### D5. 开书状态机：A 路单事务，B 路阶段回执

**A 路（直接导入）**：解析后 `POST /import/persist` 带 `import_id + name + volumes + import_token`，在一个 SQLite 事务里建书、建卷、建章、写正文；失败整笔回滚，不留半本书。`books.import_token` 唯一（nullable）用于双击/重试幂等；重复请求返回同一本书。无任务、无阶段回执、无 AI 调用。大书用批量 INSERT（每批 200–500 章）仍在同一事务内，避免部分可见。

**B 路（AI 拆书）**：任务表 `deconstruct_jobs` 增加：

```text
source            'manual' | 'import'          -- 任务来源/清单分类
structure_json    第 2 步确认结构
manifest_json     冻结的解析 manifest（含 sha/parser_version）
source_sha256     源文件 sha
parser_version    解析器版本
segments_json     [{index, from, to, chars}]    -- 大书分段
segment_index     当前/最后完成段
open_state        none|confirming|opening|partial|done
open_stage        validate|book|settings|volumes|chapters|receipt
open_claim        当前 claim token（nullable）
open_receipt_json 阶段回执/计数/错误
opened_at         done 时间
book_id           开书后回填（现有字段）
```

- **确认**：任务 `completed` 后打开开书弹窗，进入 `confirming`；确认页只读结构，可改书名，可「调整结构」回第 2 步（此时尚未建书，安全）。
- **原子 claim**：`UPDATE deconstruct_jobs SET open_state='opening', open_claim=:token WHERE id=:id AND open_state IN ('none','confirming','partial') AND (open_claim IS NULL OR open_claim=:token)`；影响 0 行则返回「正在开书」。同一任务只有一个写入者。
- **阶段**：`validate → book → settings → volumes（卷纲/逐章基线）→ chapters（卷/章/正文）→ receipt`。每阶段完成写 `open_stage` 与回执 JSON；重试时跳过已 `done` 且 `source_sha256/structure_json` 未变的阶段。
- **幂等键**：`books.import_job_id` 唯一；卷/章按 ref upsert；基线按 `(chapter_ref, domain, key)` upsert；正文按章节 hash 比对，已一致不重写。
- **部分态**：`open_state=partial` 时书已存在但未完成。书架查询过滤 `import_job_id` 指向未 done 任务的书；任务行显示「开书未完成 · 继续开书」，点继续从阶段回执续跑。禁止此时「调整结构」，提示先完成任务或删除任务/书。
- **源校验**：开书前复核 `source_sha256`；文件丢失/不一致 → `need_reupload`，不写任何阶段。
- **开书不调用模型**：世界设定压缩从 `apply.import_book` 移出，改为 B 路拆书收尾阶段完成并落产物；开书只写已生成产物。手工拆书任务的现有出口保持不变（`import_book` 加 `condense_world` 开关，默认沿用旧行为，导入任务显式关）。
- **进度呈现**：始终写阶段回执；前端发起开书后先给按钮 loading，若 1.2–2 秒内未完成再显示四段真实计数（轮询/事件），完成后直接给回执。这样无需预知 p90，也满足「≤2 秒不显示四段进度」的拍板。
- **失败/取消降级**：`open_state` 仍可走 `chapters_only` 开书：只建书/卷/章/正文，不写设定与基线；`import_book` 的 items 传空、`seed_settings=false`；回执列明未写入项。进行中任务不提供该入口。

**备选**：B 路也整笔单事务——否决，42 章+设定+基线在 SQLite 单事务内可能跨秒级且中断后只能全重来，不符合「已写入不重复」；客户端假进度——否决，用户要的是真实计数，内部清单不能上屏。

### D6. 大书分段：按章边界切、一个任务 N 段

**决定**：解析时已拿到 `char_count` 与逐章区间；在创建 B 任务时按活动章序切段：

```text
segment = 连续章区间，累计字数 <= 600000；单章自身超 60 万时独占一段
segments = [1..N]；总段数 = ceil 式累加，不按固定字数硬切
```

- 任务存 `segments_json`；dispatcher 逐段串行跑既有十维管线，`segment_index` 记录完成段；某段失败只重跑该段，已完成段产物保留。
- 任务详情显示「第 X/N 段」与该段十步进度；总费用/时间按段累加；第 3 步按实际字数估段数与总 token/时间。
- 开书合并规则（确定性）：
  - 书级 meta（简介/题材/文风）：按段序取最后一个非空值；
  - 世界/角色/关系/伏笔：按名称/键去重合并，后段补前段缺失字段，冲突以后段为准；角色重名走既有 409 改名链；
  - 主线：按段序拼接弧，去重边界；
  - 逐章基线：按章落各自段产物，不跨段合并；`story_state` 开书后按章序统一折叠。
- 分段不新增提示词模板；拆书管线单段容量按既有 60 万字设计。

**备选**：提高单次上限——否决，管线容量与失败粒度都不支持；按固定字数切——否决，会把一章切两半，卡片与章号错位。

### D7. A/B 分型、任务来源与旧入口

**决定**：

- 单一入口＝书架「导入我的书」。第 3 步 A 卡「直接导入」→ `importPersist`；B 卡「AI 拆书」→ `POST /deconstruct/tasks` 带 `source='import' + import_id + structure`，**不建书**。
- 任务清单按 `source` 分「导入 / 拆书」，顶部筛选；导入任务详情页头标「导入」；导入任务无导出出口，完成态主按钮「开书」，已开书行「进入书内」。
- 交接通知：创建后落到任务清单/详情，文案为「拆书在应用内继续，可以离开页面；不要关闭应用（关闭会暂停，下次打开继续）」；禁止「后台会跟进」。
- 失败/取消/`need_reupload` 按 D5 降级；进行中不提供跳过。
- 旧 `ImportNovelModal`/`ImportPreviewTree` 退役；后端旧的 md 解析入口只保留给历史测试/兼容，新前端不再调用，非 txt 返回明确「暂不支持」。已有 `source=import` 的书 backfill（D9）。

**备选**：保留旧弹窗并存——否决，两个入口会造出两套状态；B 路失败时另建空书——否决，会造第二本书，后续章节落错书。

### D8. 上限、模型与配额前置

- 50MB 文件上限在 `/import/parse` 与任务创建/落库入口统一；字数无上限。
- `require_project_limit` 补到 A 路 persist、B 路任务创建与 B 路开书三处；配额不足返回可执行错误（归档/删除/升级），前端在第 3 步就显示并禁用创建。
- B 路创建任务前跑既有模型探针；无可用模型不建任务；前端卡 A 置灰并给「去配置」。
- 两条路都占 1 个书位；第 3 步明示。

### D9. 数据迁移与已有书 backfill

**Schema（加法为主）**：

- `chapters`：`status` 允许 `imported`（若列有 CHECK 约束则按 SQLite 重建表法迁移）；`origin`（`authored|import`，默认 authored）、`imported_at`（nullable）。
- 四域章档表：`origin`（`extract|import`，默认 extract）。
- `deconstruct_jobs`：D5 列；`source` 默认 manual。
- `books`：`import_token` 唯一 nullable、`import_job_id` nullable；B 路部分书靠任务 `open_state` 过滤。
- 覆盖表 `chapter_dossier_coverage`（若选表方案）。
- schema 指纹变化必须进 carry/升级用例；迁移幂等、可重入。

**Backfill**：

1. 已有 `source=import` 的书（旧导入链）：`chapters.origin='import'`；非 archived 章 `status='imported'`（原 draft → imported）；archived 保持 archived + origin import；`books.import_state`/任务无则置 done。
2. 已有手工拆书任务：`source='manual'`，open 字段为 none；不改变现有导出/建书行为。
3. 已有导入书没有基线：A 路口径，story_state 不折叠、预览标原文、续写 N+1；设定留空。
4. 旧 md/docx 导入书不回填格式，只回填状态；发布说明告知新入口只收 txt。

**回滚**：迁移前自动备份 DB（既有 backup 链）；旧版本代码不认识 `imported`/新列，回滚需恢复备份，不支持「降级读新库」。发布说明写清。

### D10. 前端结构与交互落点

- 新 `ImportOwnBookWizard` 替换 `ImportNovelModal`：
  - Step 1 `ImportStepFile`：只收 `.txt`；常显格式要求/示例/下载；解析后就地显示编码、章数、字数、risk；risk 必须勾选确认。
  - Step 2 `ImportStepStructure`：左侧只读扫描结果（卷/章、章号、标题、前 200 字可选预览）；右侧卷卡列表（卷名输入、范围、chevron 折叠、分卷/少一章/多一章/合并）；章节行支持忽略/删除（忽略在确认前，删除需应用内确认）；`valid()` 与后端同契约；无卷时先「+ 新增卷」得到「正文」；>500 章虚拟滚动/搜索。
  - Step 3 `ImportStepMode`：A/B 两卡；模型行、费用/时间、隐私说明；模型未配/配额满的禁用与出口；CTA 按路径变化。
- 任务清单：`ImportTaskRow` 支持来源标签、筛选、三态、开书/进入书内；`OpenBookDialog` 三态（确认/执行/回执），执行态按 2 秒延迟显示四段；「调整结构」回 Step 2；失败/取消的「跳过设定直接开书」。
- 工作台：`OutlineTree` 显示「原文」；`hereTarget` 与「继续写作」分离；`story_state` 提示沿用；章档页签显示「已导入基线（可复核）」/「已导入（未归档）」与 stale 横幅；补算入口。
- 预览：`PreviewView` 状态标签加「原文」，概览加原文计数；完本进度排除。
- 组件词汇：只用既有 `.mcard/.notice/.pill/.field/.textarea/.btn/.dim-row/.rail-card` 等；新增标签先登记 design-system（见 delta）；不新增胶囊形态。

### D11. 测试与验证策略

**后端（pytest）**：

- 解析：txt UTF-8/GBK/Big5、无卷、单章、误识别章、50MB 边界、manifest 区间切片。
- 结构：覆盖/缺口/重叠/空卷/单章跨卷 400；前后端 fixtures 同值。
- imported 消费面：frontier（全导入/混合/全归档）、is_writable（导入章可写/未来章 409）、story_state（基线/无基线/stale）、阶段计数（导入归档不完本）、预览/树/章档读取。
- 基线：卡→四域映射、origin/coverage、补算 fill_missing 不替换、编辑 stale、单章归档默认沿用。
- 开书状态机：claim 并发只一个成功、阶段回执重试跳过、sha 不一致 need_reupload、部分书不可见/继续、调整结构仅 confirm 期、chapters_only 降级。
- 大书：180 万字/240 章 manifest → 3 段；段 2 失败重跑只跑段 2；合并规则。
- 迁移：旧 import 书/旧任务 fixture → 状态/来源/续写落点。

**前端（vitest）**：

- 向导三步、txt 拒绝、risk 勾选、无卷新增/切分/挪边界/合并/改名/折叠、忽略/删除确认、valid 禁用。
- 模型未配/配额满；费用数字随字数变化；任务筛选/三态/开书/进入书内；开书三态与 2 秒延迟；失败降级。
- 树/预览「原文」标签、续写 N+1、编辑导入章不改变树入口、stale 提示。

**E2E（隔离栈）**：

- A 路：上传 42 章 txt → 结构确认 → 直接导入 → 续写 43 → 编辑 10 → 预览标签。
- B 路（mock/真实模型二选一）：任务创建 → 清单「导入」→ 完成 → 开书确认 → 回执 → 进入书内 → 续写 43；失败任务降级开书。
- 大书 smoke：180 万字/240 章，A 路可开；B 路 3 段（AI 用桩）。
- 旧书 backfill：旧 import fixture 打开后续写 43、预览原文。
- 设计门禁：`npm run design:lint`、`npm run design:check`、`tsc --noEmit`；不触共享段，`design-cross` 按 proposal Design Impact 判定不需要（若实现中新增共享类，改为双端同批并跑）。

**性能/观测**：

- 开书 p90 打点（claim→done）；若 ≤2 秒，前端四段永不出现，保留按钮 loading＋回执；>2 秒按真实阶段显示。
- 50MB 解析内存/耗时；180 万字 A 路落库耗时；分段任务段级耗时。
- 不使用并行会话的栈；测试前确认无同类进程，跑完收环境。

## Risks / Trade-offs

- **消费面漏改** → 集中判据 + D3 表格逐面回归钉；任何新增 status 分支必须过 `rg` 清单。
- **基线质量被误解为全量** → 回执与章档明示「首尾约 6000 字，中段可能未覆盖；物品/认知未提取」；补算入口可见。
- **B 路开书部分态** → 阶段回执、书架过滤、任务行继续；删除任务/书有明确出口。
- **大书分段合并漂移** → 固定合并优先级（后段补/覆盖）、逐章基线不跨段、测试 3 段样例。
- **50MB 解析内存** → 一次性读入上限 50MB；如实测超预算，改为分块解码（manifest 区间不变），不改变契约。
- **旧 md/docx 用户流失** → 发布说明与弹窗明示「暂不支持、不提供转换」；保留历史书可读。
- **原型尚未覆盖的 v1 交互**（章节忽略/删除、risk、大书段 UI、开书 2 秒延迟）→ 第一组任务先补原型与自检，再进实现。
- **A 路无设定** → 第 3 步与回执明确代价；不承诺补拆。

## Migration Plan

1. **Phase 1（A 路先上）**：schema（imported/origin/import_token/coverage）→ 统一解析器与 manifest → 结构契约/向导 → A 路落库与 imported 消费面 → 迁移/backfill → 发布说明（md/docx 退役）。此阶段 B 路入口可隐藏或标记「即将开放」，避免半成品。
2. **Phase 2（B 路同批）**：任务 source/segments → 分段拆书 → 基线与 coverage → 开书状态机/回执/调整结构 → 任务三态/开书弹窗 → 失败降级 → 大书与 p90 验证。
3. **提示词仓**：本次不改；物品/认知补提取若立项，另起跨仓 change。
4. **回滚**：发布前自动备份 DB；回滚应用版本需恢复备份（新状态不被旧代码识别）；保留旧导入后端端点一个版本，前端不再暴露。
5. **发布后观测**：A 路导入成功率、续写落点、开书 p90、分段失败率、导入章编辑/stale 比例；异常按任务/书 id 留痕。

<!-- 本 change 无开放问题：9 条第二轮拍板与 20 条口径已全部落入设计；p90 是测量任务，不是待定方案。 -->
