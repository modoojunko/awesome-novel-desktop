# c-kb-knowledge-v2 · 知识条目模型与星图视图

## Why

原型阶段已把「知识库」重新想清楚：一条知识不是一条扁平条目，而是一个**知识单元**——有名字、分类、知识定义，往下挂多个实例（案例），左右连其他知识；浏览从「图谱/条目图」换成一张单一大星系的星图。现有 `kb_entries` 把实例字段内嵌在一行里（instruction/example/evidence/src_*），关系表虽按条目 id 关联，但模型上分不出「知识」与「实例」，也撑不起「一个知识多个实例」和版本/更新时间。原型已定稿（`docs/design-c/drafts/`），现在按定稿形态进入前后端立项。

## What Changes

- **BREAKING**：知识数据模型由「单一条目表」改为「知识 / 实例 / 关系」三张主表：
  - 知识主体＝`kb_entries` **原地加列升级**（新增 `definition`/`version`/`origin`/`archived_at` 四列；`id` 原样即知识 id，不另建主表、不搬存量行）
  - `kb_knowledge_instances`（实例：id/knowledge_id 1:N/实例文本/来源/原文摘句/顺序）
  - `kb_relations` 沿用原表（表名不改、行不搬，两端 id 语义升级为知识 id；六类白名单、禁自环、active 唯一口径不变）
  - 辅助：`kb_knowledge_aliases`（别名可检索）、`kb_knowledge_revisions`（版本快照）
- **BREAKING**：存量数据就地升级：`kb_entries.id` 原样保留为知识 id；`instruction` 落为第 1 条实例（落 `kb_knowledge_instances`，原列保留）；`definition` 为新字段首轮待补；`kb_relations` 两端 id 原样沿用。迁移幂等、不搬移不删列，回滚以代码版本回退（不依赖独立备份件）。
- **知识条目增删改查**：列表页「+ 新建知识」；右侧知识视图按「知识名 → 分类 → 知识定义 → 实例 → 其他字段 → 关联知识 → 证据链」展示；新建/修改共用知识编辑器（知识名、分类＝题材＋类别、**知识定义与实例分开**——定义是知识本身的一般性说明，实例是具体案例可多条、各带出处与原文摘句；其他字段 status/version/created/updated/aliases）；删除只归档、可恢复；官方精选只给存副本/隐藏。
- **星图视图**：知识库浏览页签由「列表 / 图谱 / 条目图」改为「列表 / 星图」。星图＝单一大星系（中央核球＋四旋臂），节点是概念（4 题材 × 6 类别的概念星），边只走 D6 概念相容矩阵允许的概念对；点概念打开「解读 → 关系 → 总结 → 出处 → 原文 → 实例」；条目不进星图，作为概念的实例。移除 `KbGraph`（聚合下钻）与 `KbEntryGraphView`（条目图）。
- **入口与回退**：顶部「星图」页签（全局）、列表工具条「列表/星图」（带题材）、概念行「在星图里看这个概念」、行内「星图」（落到所属概念）；落地聚焦概念并开卡；画布左上「← 列表」/顶部「知识库」页签返回，保留筛选；深链 `#/starsea/题材/概念`。
- **版本与时间**：知识保存时 `version +1`、`updated_at` 刷新、`created_at` 不变；详情/编辑器展示 version/created/updated（编辑器只读）。

## Capabilities

### New Capabilities

（无——全部落在既有 `knowledge-base` 能力上）

### Modified Capabilities

- `knowledge-base`:
  - **MODIFIED**「知识条目数据模型」：单一实体表 → 知识/实例/关系三主表；知识有 id、实例有 id、关系两端用知识 id；BREAKING 迁移
  - **REMOVED**「手录与种子」＋**ADDED**「知识编辑器与种子」：手录表单由「写什么＋题材」升级为知识编辑器（知识名/分类/知识定义/实例/其他字段，四项必填；类别由作家选，不再只靠推断）
  - **MODIFIED**「知识库浏览界面」：页签改为「列表 / 星图」；知识视图按 Obsidian 式属性＋正文组织；删除页面级图谱/条目图
  - **ADDED**「知识条目增删改查」：新建/查看/修改/删除（归档可恢复）的完整行为、校验与官方精选分支
  - **ADDED**「知识星图视图」：单一大星系形态、节点＝概念、边只走 D6 矩阵、概念卡六段、题材筛选、空态与降级
  - **REMOVED**「整理运行、反馈与条目图」＋**ADDED**「整理运行与反馈」：条目图退役；关系读写沿用 `kb_relations` 表（两端 id 即知识 id），六类/矩阵/active-pending-archived 口径不变
  - **ADDED**「旧知识与关系迁移」：`kb_entries` 原地加列升级＋实例表就地生成的一次性迁移与幂等/回滚口径

## Design Impact

- **受影响端**：C端 only（S端不动）
- **受影响屏/弹层**：
  - 知识库页：页签 `列表 / 星图`；列表工具条「列表 / 星图」；「+ 新建知识」
  - 知识视图抽屉（右侧 500px）：知识属性＋正文
  - 知识编辑器抽屉（右侧 600px）：分类/知识定义/实例/其他字段/关联知识
  - 删除确认弹窗（归档）
  - 星图画布面板（深色圆角，同「本体星图」槽位）＋概念卡（复用浅色右侧抽屉）
  - 题材/概念筛选、搜索、空态
- **对象状态**：知识 `draft / formed / needs_work` ＋归档（`archived_at`）；关系 `active / pending / archived`；不新增全局状态词，沿用现有状态语言
- **两端共享段**：不触碰 `base.css` 令牌/基础类与 design-system 共享段；星图颜色走既有类别/关系色，编辑器复用现有表单/抽屉词汇
- **是否需要原型先行**：**否**——原型已定稿并按 base.css 令牌复查对齐（`ai-novel-c端-知识库星海-原型.html`、`…知识库星图-整合原型.html`、`…知识库星图-流程原型.html`、`…知识条目-obsidian式建模-原型.html`、`…知识条目-数据模型.md/.sql`，设计语言对齐见设计说明 §5.3）
- **设计工件产出**：设计侧已出（上述 drafts），并已按 `docs/ux/design-language.html` 与 `base.css` 令牌复查对齐（暖纸色/紫色 wiki 链接/英文属性键已清除；按钮/胶囊/ListEditor/ConfirmGuard/Toast 位按现网词汇）；实现侧只做设计走查与文案复核（§13）

## Impact

- 后端：`client/backend/models/kb.py`（`kb_entries` 加四列＋实例/别名/版本三辅表）、`kb/router.py`、`kb/service.py`、`kb/organize.py`、`kb/match.py`、`kb/merged.py`、`kb/book_scope.py`、`write/write_block.py`、备份导出/导入（书级与账号级）、迁移脚本与测试
- 前端：`pages/KnowledgeBasePage.tsx`、`lib/kbApi.ts`、新增 `StarSeaPanel` / `KbKnowledgeEditor` / `KbKnowledgeCard`，删除 `components/tools/KbGraph.tsx`、`KbEntryGraphView.tsx` 及对应测试/coverage 契约
- 依赖新增：`three`、`3d-force-graph`（均 MIT，过许可证白名单；星图代码复用 okf-galaxy-visualizer MIT，需在 `THIRD-PARTY-NOTICES.txt` 归属）
- 数据：`kb_entries` 原地加列＋实例表就地生成（不搬存量行）；回滚路径＝代码版本回退
- 测试：后端数据模型/迁移/关系/闸门；前端覆盖 100% 契约（新组件走 `npm run coverage`）、e2e 列表/CRUD/星图/深链
