# c-kb-relations-view · 知识视图「关联知识」只读段

## Why

AI 整理产出的关系，作家点「采纳」后落库 active，但知识视图没有展示位：关系读取链路其实早已存在（`GET /kb/entries/{id}/relations` 端点＋`organize.entry_relations` 服务＋前端 `kbApi.entryRelations` 封装＋`KbEntryRelations.tsx` 完整组件），真正的缺口是 `KnowledgeBasePage.tsx` **导入了组件却从未渲染**（死导入），且组件本身是 c-kb-organize 批D 的旧形态——关系类型显示英文裸键、无对端点跳、无 active 过滤、无对端归档剔除。本 change 把这条现成链路接通并升到 v2 口径，堵住「采纳完就再也看不见」的黑洞。手动建删关系不在本 change（另行立项，见 c-kb-knowledge-v2 归档评审挂账）。

## What Changes

- **后端（小改）**：`entry_relations` 服务加 `status` 入参（`"active"` 只回生效关系；默认不变保持兼容）；关系行剔除「对端缺失或对端已归档（status=archived）」的死链行——点跳永不落 404。
- **前端**：
  - `KnowledgeBasePage.tsx` 知识视图抽屉在「其他字段」之后渲染现成的 `KbEntryRelations`（死导入转正）；基线条目（代理 id）天然查无关系、整段不出。
  - `KbEntryRelations.tsx` 改造为 v2 口径：调取数传 `status=active`；关系类型显示中文标签（词表抽到 `src/lib/kbRelations.ts`，六类齐：细化/相冲/依赖/属于/源自/适用于——`refines` 沿用现网「细化」，不改词）；行文案按关系类别定制句式（「适用于 B」「源自 B」「属于 B」「依赖 B」「与 B 相冲」「细化 B」，入向「B 适用于本知识」式），替换现箭头「←」；对端知识名可点跳（新可选 prop，页面传 `selected` 切换回调）；「这条不对」反馈按钮保留（现成 `POST /relations/{id}/feedback`）。
  - 段落提示语口径「来自知识整理」——存量 active 关系行未经作家采纳，不得表述为「你采纳的」。
- **不提供**手动新建/删除关系的入口；点跳深链（`?knowledge=` URL 同步）不在本 change（挂账）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `knowledge-base`:
  - **MODIFIED**「知识条目增删改查」：查看段细化——「关联知识」只读段的行为契约（active 过滤、按类句式、对端可点跳、归档/缺失对端剔除、基线条目不出段、「这条不对」反馈保留、无关系不占位）＋对应 scenario。

## Design Impact

- **受影响端**：C端 only（S端不动）
- **受影响的屏/弹层**：知识库页 → 知识视图抽屉（右侧详情段），新增一个只读列表段（复用 `KbEntryRelations` 既有版式：小节标题＋行列表＋notice）；无新弹层
- **用到或新增的对象状态**：零新增——复用关系既有 `active/pending/archived`（视图只展示 active，pending 清单仍在「知识整理」面板），不新增状态词
- **是否触碰两端共享段**：不触碰 `base.css` 令牌/基础类与 design-system 共享段；复用组件既有版式与 `KbOrganizePanel` 同源标签词表
- **是否需要原型先行**：**否**——单个只读列表段的既有组件改造，实现侧对照 design-language §13 自查
- **设计工件产出**：实现侧自查（关系类型词与整理面板同源不漂移；点跳行有可点击样式；无内部术语）
