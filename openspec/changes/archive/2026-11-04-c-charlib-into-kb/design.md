# c-charlib-into-kb 设计

## 决策

### D1 宿主方式：拆「视图体」，不嵌整页

`CharacterLibraryPage.tsx` 现在是「页面壳（main＋页头/h1 角色库＋统计）＋视图体（rail 四组＋toolbar＋cells/rows＋空态＋两弹窗）」一体的。搬法：

- 新建 `components/library/CharacterInstanceView.tsx`＝**视图体**（rail/toolbar/搜索/排序/双视图/统计/空态＋CardEditorModal＋UseInNovelModal 原样挂载），无页头无 `main` 容器。
- `KnowledgeBasePage.tsx` 在「concept=角色设定 且 src ∈ {全部, 手录, 拆书}」时渲染视图体替换通用列表区；否则走现状通用列表。
- `CharacterLibraryPage.tsx` 文件删除；`/tools/characters` 路由改为重定向组件。
- 样式零新增：`lib-*` 家族 CSS 原样保留（视图体继续用），不删不改。

理由：直接嵌整页会双页头双 `main`；抽视图体一次到位，页面壳本来就是退役对象。

### D2 数据源：视角打库列表端点，不打 kb entries

视角继续用 `useCharacterLibrary()`（`/api/character-library` 列表）——档案柜需要卡形状（dossier/cog/aliases/定位/小类），kb entries 端点没有这个形状。基线方法论条目永不落 `kb_entries`（`models/kb.py:442` 独立表＋读侧合并），天然不进视角，无需过滤。迁移自愈与题材回填挂点都在 `list_cards` 里（`library/service.py:360-362`），视角触达即触发——spec 的「挂点收敛」措辞由「页面退役、端点保留」自然兑现，后端零改动。

### D3 筛选联动：KB 左栏单向灌入视角（评审后收紧）

KB 题材栏选中 → 视角题材筛选**重置为该值**（单向 KB→视角；视角 rail 内再改不回写 KB 栏，避免双活互搏）。三个值域细则（双路评审实勘后补）：

- **跨题材通用不灌 `""`**：KB 该档 key=""（`kb/router.py:141`），而视角 Filters 空串＝「清除筛选」（`CharacterLibraryPage.tsx:112`）——照抄会把该档静默变成「显示全部」。灌入改用哨兵 `__empty__`，视角谓词相应分支判 `c.genre === ""`（真·未分题材）。
- **题材比对与 rail 选项走 `genre_norm`**：存量迁移卡可能带目录外自由题材（#980 拍板读取侧归一、存量不重写），原始 `c.genre` 严格比对必然 miss；`genre_norm` 已在列表载荷（`library/service.py:128`），rail 选项与过滤统一改用它（fallback 原始值）——正是兑现「读取侧归一」。`migrate_library.py:151` 注释与代码不符（声称目录外落 `""`、实为原样拷贝），后端注释修正挂账不改行为。
- **来源映射**：`手录→手建`、`拆书→拆书`、`全部→全部`；`官方精选/已隐藏` 不灌（这两种切通用列表）。搜索词不联动（两域口径不同）。

挂账（非本 change，评审发现）：KB 通用列表「跨题材通用」臂现状 `""` 被 `kbApi` falsy 丢弃＝显示全部（预存在缺陷），与视角无关，单列跟进。

### D4 通用列表在视角下的可见性

视角模式下 KB 的**来源筛选行保留渲染**（它是概念级语义，「官方精选/已隐藏」两臂切回通用列表，也是官方角色设定方法论条目的常规出口）；KB 的搜索框与库分组卡在视角模式下隐藏（视角有自己的搜索，库分组对实例无意义）。概念页签切走（文风/文笔/…）即回通用列表，无额外状态。

请求门控（评审后定）：视角模式下 `loadLibraries` **门控停发**（库分组卡已隐藏，数据零消费）；`loadEntries` **保留不门控**——左栏「全部」计数以它为源，且该请求带着迁移/回填挂点（`kb/router.py:155-158`），视角触达即自愈。

### D5 路由重定向与深链

- `/tools/characters` → `<Navigate to="/tools/kb?concept=角色设定" replace />`（照 `/books`→`/novels` 一个版本期先例，下版可删）。
- `KnowledgeBasePage` 目前**没有**实现任何 URL 深链（concept 是 `useState("全部")`；主 spec 所写 `?genre=&concept=&entry=` 三参从未落地）——本 change 落地 `?concept=` 一参：初挂载读 `?concept=`（合法值才生效，校验用 `CONCEPTS`），重定向即可落位；HashRouter 下中文 query 由浏览器百分号编码＋`useSearchParams` 解码（评审实勘路径通，`App.tsx:44` key={pathname} 保证全新挂载）。`?genre=`/`?entry=` 补齐挂账不随本 change。

### D6 文案清单（去「角色库」化）

| 位置 | 现文案 | 改为 |
|---|---|---|
| `CollectToLibrary.tsx:54` | 已把「X」收进角色库 | 已把「X」收进知识库 |
| `CollectToLibrary.tsx:54` | 「X」已经在角色库里了 | 「X」已经在知识库里了 |
| `CollectToLibrary.tsx:68` | 按钮「收入角色库 / 同步到角色库」 | 收进知识库 / 同步到知识库（与改后 toast 同屏一致，评审 P1 补） |
| `TaskDetailPage.tsx:386` | 已把 N 个角色收进角色库 | 已把 N 个角色收进知识库 |
| `TaskDetailPage.tsx:395/751/1119-1120/1167/1247` | 拆书收录面板「收进角色库」族 | 收进知识库（评审补：同屏不混称） |
| `ImportFromLibraryModal.tsx:104` | 「去『写作工具 → 角色库』先收几个角色」（空态指引） | 指去知识库的角色设定视角——phase 2 后旧指引是死路（评审 P1 补） |
| `ImportFromLibraryModal.tsx:77/103`、`CharacterManager.tsx:964` | 「从角色库导入」弹窗标题/提示族 | 从知识库导入 |
| `CarryDialog.tsx:227` | 角色库（迁移统计段标题） | 角色卡（描述的是存量卡数，不是页面名） |
| `KnowledgeBasePage CONCEPT_DESC` | 造角色的方法，成品在角色库 | 造好的角色，一人一条 |
| `ToolsMenu` 角色库菜单项 | 整项删除 | —（知识库 desc 已覆盖，不加词） |

**非目标**：「用到新书」撞名后缀「（角色库{n}）」不改——它是落进书内角色卡的来源标记，改它＝动数据口径，收益为零；「角色库」作为域名词在表名/路由前缀/代码注释里保留（`character_library` 表名、`/api/character-library` 路由前缀都不动）。

### D7 测试面迁移

- `__tests__/characterLibrary{,Coverage,Branches,Degenerate}.test.tsx`：宿主从 `CharacterLibraryPage` 换 `CharacterInstanceView`；「页面标题/页头」类断言删除，断言口径不变（筛选/搜索/高亮/统计/弹窗行为逐字保留）。
- `__tests__/knowledgeBasePage.test.tsx`：补视角切换两臂（角色设定页签→视角；来源官方精选→通用列表）。2.3 引入 `useSearchParams` 后，`knowledgeBasePage`／`knowledgeBaseCoverage` 两文件既有 10 处裸渲染 `render(<KnowledgeBasePage />)` 会抛 Router context 错——全部补 `<MemoryRouter>` 包装（先例 `apiKeyConfigPage.test.tsx:59`）；视角臂测试另需 QueryClientProvider（评审 P1 补）。
- `__tests__/toolsMenu.test.tsx`：删「角色库」菜单项断言；文件头「三项菜单」注释已过时（现四项）顺手修。
- `e2e/character-library.spec.ts`：入口三处断言（menu-charlib 可见／URL `#/tools/characters`／heading「角色库」）改走知识库入口；stubApi 须补 `/api/kb/genres|entries|libraries` 桩——否则兜底 `data:{}` 会让 KB 页渲染即崩（`setGenreCounts({})` 后 `.filter` 炸）；用例主体步骤不变。
- `coverage-contract.ts`：`CharacterLibraryPage.tsx` → `CharacterInstanceView.tsx`（契约测试对缺失文件是硬红，必须同批）。
- 后端零改动 → 后端测试不动。

## 风险

- **R1 双筛选行观感**（KB 来源筛选行＋视角 rail 来源组并存，D4）：原型先行时看效果；若拥挤，视角模式下把 KB 来源筛选行收进「官方精选」单钮再做（视觉微调不破 spec）。
- **R2 题材单向灌入与视角内改选**（D3）：KB 题材栏变化会覆盖视角内手选——以「用户最后动作」为准（视角内改选后，只要 KB 题材栏不再变就不打扰）；实现用 effect 监听 genre prop 即自然满足。
- **R3 「搬完再摘」分两步交付**：phase 1（视图体＋四动作在 KB 内）可独立发版——彼时角色库页还在，两视图并存一时，无功能缺口；phase 2 摘页面。两步各自全绿可合。

## 回归口径

- C端 `npm run design:lint` ＋ `npm run design:check`（本屏不在像素矩阵，跑通全量防误伤）。
- `tsc --noEmit`；`npm run coverage`（契约文件换血后阈值门槛照走）。
- 共享段零触碰 → 免 `design-cross.mjs`（依据：Design Impact 判定，只用既有 `lib-*` 家族与语义类）。
- e2e：`character-library.spec.ts`（入口/桩改造后）全绿；无 knowledge-base 专属 e2e 文件，知识库面由组件测试钉，涉知识库的 `settings-forms.spec.ts` 照实跑。
