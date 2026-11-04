# c-charlib-into-kb：角色库页面退役，视图搬进知识库

## Why

数据层早已合流：角色卡就是知识库条目（`KbEntry`，concept=角色设定），角色库后端读写全落 `kb_entries`，头像同一份字节；knowledge-base 主规格也已写明「角色库是知识库在『角色』维度的投影」。但界面仍有两个入口（写作工具菜单里「知识库」「角色库」并列），同一批数据两个视图并排，作家（boss 实测）会困惑「角色设定和角色设定库是不是重复了」。拍板（2026-11-04）：角色库就是知识库在角色这个视角的视图，界面去掉角色库这个页面；概念是 schema，角色是实例。

节奏（boss 拍板「搬完再摘」）：先把页面独占的四个能力搬进知识库角色设定视角，任何时刻能力都有出口，再摘页面。

## What Changes

- **搬（phase 1）**：知识库「角色设定」概念页签升级为**角色实例视图**——原角色库档案柜体验整体迁入：四组筛选（题材/定位/来源/小类）、多词搜索＋高亮、排序、卡片/列表双视图、三项页头统计，以及四个此前仅该页有的动作：**编辑卡、新建角色、用到新书、生成头像**（复用既有 `CardEditorModal`／`UseInNovelModal`／头像端点，零后端新能力）。
- **摘（phase 2）**：**BREAKING（界面级）**：退役 `/tools/characters` 路由与写作工具菜单「角色库」入口；`/tools/characters` 301 跳知识库并预选角色设定页签（照 `/books`→`/novels` 一个版本期的先例）。
- **文案去「角色库」化**：收录出口全套改口「收进知识库」（拆书详情 toast＋按钮、书内收录按钮、任务清单角色数文案）、书内导入弹窗标题与空态指引（旧指引「去写作工具→角色库」在摘页后是死路）、迁移面板「角色库」段标题、知识库概念页签说明句（「成品在角色库」改口）——全表见 design D6。
- **后端不动**：`/api/character-library` 全部端点保留（书内收录/导入/同步/头像/用到新书都靠它，它本来就是 KbEntry 的形状适配层，非独立存储）；迁移自愈与题材回填的两个**后端读面挂点都保留**（kb 条目列表＋视角所打的库列表各带各的，`kb/router.py:155-158` 与 `library/service.py:360-362`），页面级调用点随退役消失——后端零改动兑现。
- 测试面随行：`characterLibrary*.test.tsx` 页面级用例迁改为知识库视角用例；`coverage-contract.ts` 把 `CharacterLibraryPage.tsx` 换成知识库视角宿主文件；e2e `character-library.spec.ts` 改走知识库入口。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `knowledge-base`：浏览界面 requirement——「角色设定」概念页签从通用列表升级为角色实例视图（档案柜 UX＋四动作宿主）；概念说明句改口；角色库存量一次性迁移 requirement——迁移触发挂点从「知识库条目列表或角色库卡列表」收敛为知识库读面单挂点。
- `character-library`：列表与检索／增删改查／用到新书三个 requirement 的呈现宿主从「角色库页」改为「知识库·角色设定视角」（行为与后端契约逐字保留）；字段契约、收录、书内导入、同步、改名换龄、归属、头像生成、拆书收录八条 requirement 不动行为。

## Impact

- **代码**：`client/frontend/src`——`App.tsx`（路由）、`components/tools/ToolsMenu.tsx`（菜单项）、`pages/KnowledgeBasePage.tsx`（角色设定视角宿主＋`?concept=` 深链）、`components/library/*`（CardEditorModal/UseInNovelModal/LibraryAvatar 等组件原地复用；`CharacterLibraryPage.tsx` 拆出视图体后退役删除）、`coverage-contract.ts`（文件清单换血）、文案收口（design D6 全表）；`src/__tests__/characterLibrary*.test.tsx` 与 `e2e/character-library.spec.ts` 迁改。
- **后端零改动**：`client/backend/library/`（router/service）与 `kb/` 不动；`/api/character-library` 端点全保留。
- **依赖关系**：角色库原型 draft（docs/design-c/drafts/ai-novel-c端-角色库-原型.html）退役标注；知识库 draft 原型补角色实例视角一屏。

## Design Impact

- **受影响端**：C端 单端（S端零接触，不触共享段：不新增/修改 base.css 令牌与语义类，全部复用既有组件类与 library 家族既有样式）。
- **受影响屏/弹层清单**：
  - 知识库页（列表视图）：「角色设定」页签选中态换角色实例视图宿主；
  - 知识库页内弹层：编辑卡弹窗（CardEditorModal 原样入）、用到新书弹窗（UseInNovelModal 原样入）、新建角色（编辑弹窗空卡态）、生成头像（编辑弹窗既有按钮）；
  - 写作工具下拉菜单：减「角色库」一项；
  - 拆书任务详情/书内角色页：收录 toast 文案两处；
  - 迁移确认弹窗（CarryDialog）：「角色库」统计段措辞。
- **对象状态**：全部沿用状态语言总表既有形态（notice/pill/toast 用 info·ok·warn·err 既有语气词），不新增状态形态。
- **共享段**：零触碰（理由：档案柜版式与弹层均已在 c-character-library 落地并上线，本 change 只搬家不改样式）。
- **原型先行**：需要——知识库 draft 原型（docs/design-c/drafts/ai-novel-c端-写作知识库-原型.html）补「角色设定视角」一屏（档案柜迁入态＋四动作）；角色库 draft 顶部加退役标注指向知识库视角。两屏均不在 design:check 像素矩阵（矩阵只跑 list.html/preview.html），无 parity 基线负担。
- **设计工件产出**：实现侧自查（版式零新设计，纯搬运）。
