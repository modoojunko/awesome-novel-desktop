# c-charlib-into-kb 任务

## 1. 原型先行

- [x] 1.1 `docs/design-c/drafts/ai-novel-c端-写作知识库-原型.html` 补「角色设定视角」一屏：档案柜视图体（rail 四组＋toolbar＋卡片/列表＋统计）嵌知识库页（页签选中角色设定、来源筛选行在位）；演示编辑卡弹窗、用到新书弹窗、新建角色入口。新建角色主按钮/统计条/加载失败 notice 原住角色库页头，视图体落点（顶部条/工具行）在本屏定，`lib-new` 等 testid 随落点走。
- [x] 1.2 `docs/design-c/drafts/ai-novel-c端-角色库-原型.html` 顶部加退役标注（指向知识库角色设定视角），不改版式；`ai-novel-c端-角色库-设计说明.md`（含 /tools/characters 引用）随行标注。
- [x] 1.3 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记本批（两屏均不在 design:check 像素矩阵——登记视角切换规则 D3/D4 与「双筛选行」观感处理）。

## 2. 搬（phase 1：视图体进知识库，四动作在位）

- [x] 2.1 新建 `components/library/CharacterInstanceView.tsx`：从 `CharacterLibraryPage.tsx` 抽视图体（rail/toolbar/搜索/排序/双视图/统计/空态＋CardEditorModal＋UseInNovelModal），无页头无 main 容器；props 接 `genre`（KB 题材单向灌入）与 `srcPreset`（手录→手建、拆书→拆书、全部→全部）；`charlib.view` localStorage 口径不变。
- [x] 2.2 `KnowledgeBasePage.tsx`：concept=角色设定且 src ∈ {全部, 手录, 拆书} 时渲染视图体替换通用列表区；来源筛选行恒渲染（官方精选/已隐藏切回通用列表）；视角模式下隐藏搜索框与库分组卡、`loadLibraries` 门控停发（`loadEntries` 保留——计数源＋挂点，D4）；CONCEPT_DESC 角色设定改「造好的角色，一人一条」。
- [x] 2.3 `CharacterInstanceView.tsx` 值域细则（D3 评审整改）：题材筛选与 rail 选项改用 `genre_norm`（fallback 原始值）；KB「跨题材通用」灌入走哨兵 `__empty__`＋谓词分支判 `c.genre === ""`，不得把 `""` 当「全部」灌入。
- [x] 2.4 `KnowledgeBasePage.tsx` 补 `?concept=` 深链：初挂载读合法值进 concept state（校验用 `CONCEPTS`；为路由重定向落位）。
- [x] 2.5 视角下四动作验证：编辑卡（CardEditorModal 原样）、新建角色、用到新书（UseInNovelModal＋题材硬门）、生成头像（编辑弹窗既有按钮）——组件测试钉行为（见 §4）。

## 3. 摘（phase 2：页面与入口退役，文案收口）

- [x] 3.1 `App.tsx`：`/tools/characters` 路由改重定向组件 `<Navigate to="/tools/kb?concept=角色设定" replace />`；删 `CharacterLibraryPage` import。
- [x] 3.2 `ToolsMenu.tsx`：删「角色库」菜单项（menu-charlib）。
- [x] 3.3 删 `components/library/CharacterLibraryPage.tsx`。
- [x] 3.4 文案收口按 design D6 全表执行：CollectToLibrary toast 两句＋按钮两枚（:68）、TaskDetailPage 成功/失败 toast＋收录面板族（:386/:395/:751/:1119-1120/:1167/:1247）、ImportFromLibraryModal 空态死路指引（:104）＋标题/提示族（:77/:103）、CharacterManager 导入入口（:964）、CarryDialog 段标题（:227）、CONCEPT_DESC（2.2 已含）、ToolsMenu 菜单项（3.2 已含）。
- [x] 3.5 `coverage-contract.ts`：`CharacterLibraryPage.tsx` → `CharacterInstanceView.tsx`（c-character-library 注释行同步改写）。
- [x] 3.6 后端跟进挂账登记（不改行为）：`kb/migrate_library.py:151` 注释与代码不符（声称目录外题材落 `""`、实为原样拷贝），随 PR 单独一行注释修正；KB 通用列表「跨题材通用」臂 `""` 被 falsy 丢弃＝显示全部（预存在缺陷）单列 issue 不随本 change 修。

## 4. 测试迁移与回归

- [x] 4.1 `characterLibrary.test.tsx`／`characterLibraryCoverage`／`Branches`／`Degenerate`：宿主换 `CharacterInstanceView`；删页头类断言；筛选/搜索/高亮/统计/排序/双视图/删除确认等断言口径逐字保留；题材类用例补 `genre_norm` 与哨兵 `__empty__` 两臂（D3）。
- [x] 4.2 `knowledgeBasePage.test.tsx`：补视角切换两臂（角色设定页签→视图体在位；来源官方精选→通用列表回位）＋ `?concept=` 深链落位断言。**前置**：2.4 引入 `useSearchParams` 后，`knowledgeBasePage`／`knowledgeBaseCoverage` 两文件既有 10 处裸渲染 `render(<KnowledgeBasePage />)` 全部补 `<MemoryRouter>` 包装（先例 `apiKeyConfigPage.test.tsx:59`）；视角臂测试另加 QueryClientProvider。
- [x] 4.3 `toolsMenu.test.tsx`：删角色库菜单项断言，菜单项数照实改；文件头「三项菜单」过时注释顺手修。
- [x] 4.4 e2e `character-library.spec.ts`：入口三处断言改走知识库入口（menu-charlib 可见／URL／heading）；stubApi 补 `/api/kb/genres|entries|libraries` 桩（兜底 `data:{}` 会让 KB 页渲染即崩）；用例主体步骤不变。
- [x] 4.5 回归门禁（实际跑并记录结论）：
  - `npm run design:lint` 全绿；
  - `npm run design:check` 全绿（本屏不在像素矩阵，跑全量防误伤）；
  - `tsc --noEmit` 干净；
  - `npm run coverage` 绿（契约换血后阈值照走）；
  - 相关 e2e 全绿（`character-library.spec.ts`；涉知识库的 `settings-forms.spec.ts` 照实跑——无 knowledge-base 专属 e2e 文件）。
- [x] 4.6 共享段判定记录：零触碰（只用既有 `lib-*` 家族与语义类，未新增令牌/家族类）→ 免 `design-cross.mjs`，依据＝proposal Design Impact。

## 5. 收尾

- [ ] 5.1 真机走查清单：写作工具菜单无「角色库」；旧地址 `/tools/characters` 落知识库角色设定视角；视角四动作逐个过；书内「从知识库导入」「收进知识库」文案核对新措辞；迁移弹窗「角色卡」措辞核对。
- [ ] 5.2 归档随实现 PR 走（sync delta＋移档 archive，不单开归档 PR）。**若实现拆两 PR（搬/摘）**：specs delta 的 sync 与归档必须随 phase 2（摘）的 PR——delta 里「独立页面退役／视角为唯一界面／入口收敛」三条 SHALL 在 phase 1 状态下尚未成立。
