## Context

works.html v2（2026-09-20 11:44）把书架从纯卡片流升级为可组织清单；当前实现（#440＋c-works-spacing-align 后）与 v1 逐像素一致。v2 新增全部为前端行为：list 接口已下发搜索/排序/分组所需全部字段（name/created_at/updated_at/word_count/total_archives/finished_at，后端评审逐字段实测确认），**零后端改动**；但接口时间戳是**无时区 UTC ISO 字符串**（非原型数字），「最近更新」只反映书级动作（正文/章纲保存不刷新，`chapters/rewrite.py:8` 注释自认不可靠）。书架现有资产：design-parity.spec.ts（books/empty/quota/finish）、works-finish-flow.spec.ts、novelListPage.test.tsx。**本设计已经前后端架构师评审修订**（评审发现折入下）。

## Goals / Non-Goals

**Goals:**

- 书架与 works.html v2 行为＋像素一致：工具栏三件套、状态优先排序、分组视图、分页、两种空态。
- 筛选/排序/分页逻辑纯函数化，可单测（vitest）。

**Non-Goals:**

- 不动后端（无新端点/字段/迁移；后端评审 F5.1/F5.2 确认）。
- 不动完本弹窗结构（仅骑手修 409 文案）、⋯ 菜单、导入/新建。
- 不在本批补 `--radius-pill` token（触碰共享段，另立 change）。

## Decisions

1. **状态机单对象**（评审 F6）：`const [filters, setFilters] = useState({kind:'all', q:'', sort:'recency', shown:12})`；所有变更点原子 reset shown（含重复点同一 chip、清空搜索——对齐原型 `works.html:691,694,725` 无「同值早退」）；**不用**多 useState＋effect 重置（避免先按旧 shown 渲一帧＋IO 交叉）。q 输入归一 `trim().toLowerCase()`。派生 `useMemo`：`visibleBooks(novels, filters)` → slice。
2. **纯函数模块 `src/lib/shelfSort.ts`**：`SHELF_PAGE_SIZE=12`、`visibleBooks`（过滤→状态 rank〔ready0→writing1→setting2→done3〕＞排序键＞书名 zh tie-break，与 `works.html:429-450` 1:1）、`slicePage`。**比较器容错**（评审 F1.4）：时间键走 `Number(new Date(v))`，null/缺失归 0；单测覆盖 ISO 字符串/null/字段缺失三态＋「创建时间序≠书名序≠字数序」可证伪数据。注意 vitest(Node ICU) 与 Chromium `localeCompare('zh')` 可能不同（评审未验证项）——顺序断言优先放 e2e，单测用可预期字串。
3. **渲染分支与结构**（评审 F4/F5/F11/F12＋用户裁定）：**工具栏随有书态渲染**（零书/加载/失败不渲染——零书入口由 first-run 承担，较 v2「恒渲染」为登记偏差）；新增无样式包裹 `<div className="bk-list">` 承载 `.cards`/`.bk-group`/`.load-more`（使 `.bk-group:first-child` 结构成立、复刻原型 DOM）；空态 `.bk-empty` 是 `bk-list` 直接子节点、**不放进 `.cards`**（否则成 1/3 列宽卡）。渲染优先级钉死：`loadError → loading → total===0（first-run）→ filtered 且 visible===0（bk-empty）→ 列表`。kind==='all'→单网格；单态→`.bk-group`（分组头「去完本」传该组排序首本，复用既有 finishTarget）。组件边界：`<ShelfToolbar>`＋`<ShelfBookCard>`（~130 行搬家），menuFor/menuRef/外点监听留页面层；`data-od-id` 全量携带（原型 287/288/293-297/299/467/473/475/481/513/558/562/563）。
4. **空态判据按原型、零书支保留现状**（用户裁定 2026-09-20）：`filtered = kind!=='all' || !!q` 分叉（**不是** total/visible 分叉）；filtered 支＝v2 `bk-empty` 逐字（标题「没有找到符合条件的作品」＋「换个关键词或状态再试试。」）；**零书支＝first-run 三步引导原状保留**（v2 零书简空态不采用，沿 ADJUSTMENTS #7 应用侧扩展口径随基线保留）。`清除筛选`＝kind 回 all、sort 回 recency、q 清空、shown 重置（**含排序回位**，原型 `works.html:693-698` 漏回写 `#sort.value` 是原型缺陷，受控 select 修正、ADJUSTMENTS 登记）。
5. **提示条退役**（评审 F9）：删 `readyDismissedId`（:88,:185）、`readyBook` memo（:214-219）、notice JSX（:339-357）；`.notice` 家族保留（四条 Banner 仍用）。
6. **分页与 IO**（评审 F23/F24）：`load-more` 按钮为主路径；IntersectionObserver 观察 load-more 容器（rootMargin '160px'），每次重绘 disconnect；**加 `typeof IntersectionObserver === 'undefined'` 守卫**（jsdom 无此 API 且仓库无 stub——不守卫打挂整份书架单测）。e2e：断言按钮 `[data-od-id="load-more"]` 点击路径；IO 冒烟用窄视口＋`scrollIntoViewIfNeeded`＋`expect.poll`；严禁断言「首屏恰 12 本」。
7. **CSS 落点**（评审 F14/F15/F16/F18/F19）：新样式进 `list.css`；`.chip`/`.chip.on` **作用域化 `.bk-chips .chip`**（book.css:437 同名现役、装载序对 app 不利；裸写会被覆盖且 parity 约 0.1% 低于阈值「静默绿」）；`--radius-pill` 用字面 `999px`；`.book-card .foot` 补抄 v2 三值；v2 壳层微差（icon-btn flex:none、logo nowrap、notice .nt min-width、.b nowrap、body padding-bottom）照 ADJUSTMENTS #12 体例记豁免。
8. **排序语义与语义钉死**（评审 F1.4/F1.5/F8）：状态 rank 恒优先＝产品语义反转（推翻 08-29 裁定与 ADJUSTMENTS #6→改写）——决策点 3；「最近更新」= 最后一次**书级动作**写进 spec 注记（正文/章纲保存不刷新，属后端事实；「最近写过」若需要则破零后端改动，另立）。
9. **原型晋级（替换式＋双重保留块）**（评审 F20/F21/F25＋用户裁定）：v2 并入，**保留 v1 的 quota 依赖块**（`.lock-tile` 家族、`ainovel.member` 读取、quota notice——应用侧扩展，沿 ADJUSTMENTS 先例）**与 v1 的 first-run 三步引导块**（零书态，用户裁定保留；v2 该支简空态不采用）；parity 注入键 `ainovel.books`→`od.works.v1`、PROTO_BOOKS 字段更名（`state/finishedAt`）＋数字 `createdAt/updatedAt`（缺了触发 v2 归一化改写会静默错序）＋展示字面量自洽；同步 `prototypes/CLAUDE.md:71` 屏说明（三态描述扩为 v2＋沿用口径）。`backup-restore.html` 屏 4 变体 A 因 first-run 保留而**无需重基**（原评审 F25 连带项消解）。
10. **parity 场景**（评审 F22）：books（混排）、**group 钉 `kind='ready'`**（去完本入口唯一出现处）、empty-filter、empty（简空态＋工具栏在）、finish、quota（视决策 5）；**pagination 升为必做**（13–24 本，12 本在 1440×900 下按钮在视口外不自动触发、截图确定）；可选 `sort=words` 场景证伪 rank＋tie-break。基线重出 `list.*`。
11. **骑手**（评审 F3.1）：FinishModal catch 改 `errMessage(e)` 透出服务端 detail（既有 spec「409 呈现守卫原因」的欠账，新入口使其可达）；e2e 补「已完结 409」桩。
12. **登记纪律**（评审 F17）：tasks 1.3 改**无条件登记**——design-vocab/design-lint 不扫 `src/**/*.css`、不查字号高度，新档位（chip 30px/12.5px、search&sort 36px、group-head 15px serif）只能人工登记。

## Risks / Trade-offs

- **排序语义反转**承载产品裁定（决策点 3）——若否决，`visibleBooks` 只保留过滤＋分页，rank 表删除。
- **quota 场景**处置（决策点 5）影响 parity 工作量与免费额度墙的像素保护面。
- **相对时间 8h 时差**（评审 F1.6，存量 bug）：接口无时区串被按本地解析，「刚刚归档」显示「8 小时前」；修法一行（parseServerTime 补 Z），**列为代码 task 骑手**（既有 e2e 桩用 toISOString 带 Z 故测不出）。
- **零书态与原型偏差**：first-run 保留＋工具栏不随零书渲染均属登记偏差——empty parity 场景双侧须同为 first-run（基线保留块），照 v2 直译会红。
- **IntersectionObserver** 守卫/桩二选一，漏了打挂 vitest（评审 F24）。
- **内部链接死路检查**：原评审 F25「first-run 退役连带清单」因用户裁定保留而**大部消解**——`novelListPage.test.tsx:204-221`、`landing-view.spec.ts:147`、`backup-restore.html`、ADJUSTMENTS #7 均**不需改动**（#7 改为「沿用并随基线保留」一句）。
