# c-chapter-dossier：正文保存后归档（章档）

## Why

长篇一致性的核心缺口：下一章提示词只吃上一章章纲留存字段，正文里实际发生的设定推进、关系变化、物品易手、谁知道什么都丢失，AI 越写越「失忆」。归档是正文定稿的天然时机——作者点「归档」时按最终正文（AI 稿+手改）提取四域变化存入**章节档案**（不动本书初始设定），已采纳的章档状态进下一章提示词，把「截至上章世界是什么样」变成可积累的结构化记忆。设计与四路评审（架构/前端/提示词/产品）已收官，12 项拍板＋6 项评审终拍全部落定（2026-09-28）。

## What Changes

- **归档流水线重构**：POST /archive 从「同步置位、永不卡」改为「受理→后台 AI 提取→成功原子收口」——提取成功（四域全 extracted）才在一个事务里置 archived；提取失败章不归档、可重试；本书模型未配置则放行归档（无章档、可后补）。
- **四域提取**：设定改动/人物关系/物品变化/角色知道的信息，一次 AI 调用出四域 JSON（各带证据句）；每域终态二值（extracted 含空数组/failed）；新分层模板 `chapter_archive_extract.prompt`。
- **章档存储**：四张章作用域子表（真表，非 JSON 列），行状态 pending/accepted/rejected；本书初始设定零写回。
- **待确认与采纳**：工作台新「章档」页签——四域待确认行（证据句可对读）、按域/全章批量采纳＋逐条兜底、已采纳行可删除；未采纳行不进提示词。
- **提示词消费**：写正文素材新增「故事状态（截至上章）」块（只取已采纳、按章现态 archived 过滤、每域配额截断、空块整段缺席、带防泄底规则行），两路同源。
- **重写级联**：重写＝本章章档清空重提＋下游章 `dossier_stale` 提示重提；unarchive 章档保留但不消费；重归档整体覆盖（确认弹层警示）。
- **门控拆分**：新提取全档可用（不挂会员门，仅要求本书模型就绪）；旧伏笔/lore 提案仍 PRO；免费档补配 key 引导，叙事统一「生成新内容是 PRO，整理你已写的内容全档」。
- **进度与软锁**：点归档即软锁本章直到归档完成；归档分步进度可见（受理→AI 提取→写入章档→置归档）；首次提取失败即出现「跳过提取仍归档」逃生阀（写明代价）。
- **BREAKING**：旧收尾三类（set_changes/relations/char_states）退役迁章档，`/reconcile/run` 的 kind 白名单收缩为 hooks/lore；归档从瞬时操作变为可失败的流程（配合重试与逃生阀）。

## Capabilities

### New Capabilities
- `chapter-dossier`: 章档全链——归档受理流水线（进度/软锁/逃生阀）、四域提取契约、章作用域子表存储、待确认采纳、下章提示词消费、重写级联、门控与成本、章档页签。

### Modified Capabilities
- `archive-reconcile`: 收尾五类收缩为 hooks/lore 两类（三类迁章档）；采纳写回分发器收缩；门控语义拆分（会员门只管旧两类）；「归档即刻生效」翻转为「提取成功才归档」；按需触发入口改向。
- `tier-access`: 「Archive is free」语义细化——无模型即刻归档不变；有模型时归档以提取成功为前置；提取调用不挂会员门。
- `chapter-data`: useChapterData 的 archive 契约从同步置位改受理态（archiveJob），chapter:archived 事件只在真置位后派发；提取窗口正文锁定。
- `prompt-crafting`: 新增「故事状态（截至上章）」块注入需求（两路同源、空块缺席、配额截断、防泄底）；组装来源只读展示从六处扩七处（含章档缺失提示）。

## Impact

- **后端**：`client/backend/archive/`（router 受理化、reconcile.py 每章键控单飞/job 状态落库/解析失败显式失败、新 dossier 服务）；`models/chapter.py`（四张章子表＋`dossier_stale` 列）；`chapters/store.py`（assemble 拆装加 dossier 键＋presence-gate）；`chapters/rewrite.py`（级联同事务）；`chapters/frontier.py`（revert 清理清单扩四子表）；`write/chapter_writer.py`（故事状态块单源渲染＋累计合并查询）；`prompts/chapter_archive_extract.prompt`（新分层模板）；`backup/export.py`+`importer.py`（dossier 往返）；`auth_local/deps.py` 门控调整＋`ai_client.py` 门禁 grep 豁免名单。
- **前端**：`ChapterWorkspace.tsx`（新页签＋归档进度状态机）；`useChapterData.ts`（受理态）；新 `DossierPane.tsx`＋`dossierApi.ts`；`ReconcilePane`/`Rail.tsx`（三入口改向）；`ArchiveModal`（覆盖警示＋模型未配置文案）；`OutlineTree`（dossier_stale 角标）。
- **数据**：四张新表＋一章一列（server_default，无 NOT NULL 无默认列，避开迁移链整表跳过坑）。
- **e2e**：reconcile.spec / modals-pr5 / free-writing-flow / chapter-rewrite 四条主链受归档两段式冲击，需同步改写＋提取提速桩。
- **排期**：不插队 v0.25，打版后第一迭代开发；立项期先做提取质量 baseline 评测（样章跑四域人工标采纳率）。
