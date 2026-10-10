# c-char-list-order-search — 角色列表拖拽排序（手动顺序持久化）＋搜索可见性修复

## Why

角色多了之后作家找不到人：列表组内顺序被钉死为建卡序（`order_by(seq)`），作家无法把重要人物排前面；而搜索（名字＋别名，拍板不扩容）存在一个隐藏缺陷——命中的角色落在收起的分组里时**完全不可见**，作家会以为没搜到。作家对「自由排序」的定义已拍板＝**按住拖拽改变列表顺序**（不做排序方式切换器）。

## What Changes

- **拖拽排序（前端）**：列表行把手拖拽（短按仍是选中）；「按角色类型分组」开关（默认开＝组内拖拽；关＝整条扁平自由拖），开关状态按书记忆；搜索过滤中禁拖（把手置灰）；`Alt+↑/↓` 键盘移动；拖拽视觉态进 React 状态（拖影/落位线/半透明源行）。
- **顺序持久化（后端）**：characters 表加可空 `sort_rank` 列（走整库迁移通道，存量用户升级首启走一次候选带回，rank=NULL 恰为想要的语义）；新端点 `PUT /api/novels/{pid}/characters/order`（body 全量有序 id 数组；允许子集提交＝未提交卡 rank 不动；未知/跨书/重复/空 id 400 点名；单事务 executemany、**不 bump rev、不作废门禁存档**；last-write-wins 无书级锁）；列表读路径改 `ORDER BY sort_rank IS NULL, sort_rank, seq`（旧书无 rank＝原创建序）。
- **回弹与失败语义（前端）**：orderRef 永续持有本地全序，reloadList 到货按其重排（新 id 追加末尾、消失 id 滤除）——自动保存后的列表重取不再把拖好的顺序打回；连续拖拽合并提交（串行队列只留最新数组，独立于单格保存队列）；order 失败＝回退视觉顺序＋toast「顺序没保存上，请重试」。
- **提示词钉序（后端）**：list 顺序改了会波及 **5 个提示词消费点**（章纲角色锚、主线起草、章纲一行卡、拆卷素材、人物盘点）——抽共用 seq 排序 key 全部钉回建卡序，SHALL NOT 把作者的手动显示顺序泄进任何 AI 上下文。
- **搜索可见性修复（前端）**：搜索时自动展开有命中的折叠分组（清空后还原折叠快照）；零结果空态「没找到『xx』」＋一键清空；搜索范围维持名字＋别名不变（拍板）。
- **备份往返（后端）**：角色段导出带 `sort_rank`、导入还原（旧包缺键＝NULL 落末尾）；撤销恢复的卡 rank＝NULL 落末尾（sort_rank 不进撤销快照）。
- 明确不做：排序方式切换器、拖到别的分组＝改角色类型、拼音搜索、搜索语义词扩容（均二期/已拍板砍）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-settings`: 新增「列表手动排序（拖拽）」要求（持久化端点契约、组内/扁平两态、开关记忆、搜索禁拖、键盘、失败回退、新卡与撤销恢复落末尾）；「角色列表一次给全」扩展——载荷携带 sort_rank、搜索命中分组自动展开、零结果空态一键清空；「写章侧的角色状态块」补角色排列钉建卡序。
- `backup-restore`: 「角色段的导入导出契约（v2）」补 sort_rank 随包往返（缺失键＝NULL）。

## Design Impact

- **受影响端**：C端（S端零改动）。
- **受影响屏/弹层**：设定 · 角色面板左栏列表（原型 `docs/design-c/prototypes/character-settings.html`）。
- **对象状态**：拖拽中＝源行半透明＋拖影（跟随指针）＋插入位置高亮线；搜索过滤中把手置灰；顺序保存失败 toast（补救语带「请重试」）；不新增提示语气、不触碰共享段。
- **原型先行**：需要——`character-settings.html` 补把手、拖拽三态、分组开关（含关=扁平态行内类型标签）、搜索自动展开与空态形态，偏差登记 `ADJUSTMENTS.md`；交互基准＝`docs/design-c/drafts/ai-novel-c端-角色批量添加与拖拽排序-原型.html`（已验证）。
- **设计工件产出**：实现侧自查（design:lint / design:check / tsc / e2e 门禁全绿）。

## Impact

- `client/backend/models/character.py`：`sort_rank` 可空整型列（schema 指纹变更→存量用户升级首启走一次整库迁移「候选带回」，migration 引擎零改动可承接；发车前核对同版本其他 schema 变更合流一次迁完）。
- `client/backend/settings/character_service.py`：`set_characters_order`（校验 ids ⊆ 本书卡集、去重拒绝、400 `invalid_ids` 点名；单事务 UPDATE、不 bump rev）；`list_characters` 读路径改序；`card_to_dict` 加 `sort_rank`（前端回弹竞态与拼提交数组依赖）；新增共用 `seq_sort_key` 并替换 5 个提示词消费点的排序（`write/chapter_writer.py`、`settings/ai_router.py`、`chapters/ai_draft.py`、`volumes/ai_plan.py`、`chapters/ai_cast.py`）——**必须与读路径改序同一 change 原子落地**。
- `client/backend/settings/characters_router.py`：`PUT /order` 静态段声明在 `/{character_id}` 族之前（防路由遮蔽，`/graph` 先例）。
- `client/backend/backup/`：导出白名单加 sort_rank；v2 导入 `raw.get("sort_rank")`（非 int→NULL）；撤销快照 `_snapshot_card` **不带** sort_rank。
- `client/frontend/src/lib/characterOrder.ts`（新，纯函数：全局 id 数组唯一真源、组内拖=全局 splice、键盘移动池、分组视图派生）＋ `useCharacterReorder`（串行队列只留最新、orderRef 本地真源解 reloadList 回弹、失败回退）＋ 列表面板指针绑定（把手 aria-hidden、6px 阈值、短按选中、搜索置灰、ghost portal+rAF）＋分组开关（`chars.grouped.${projectId}`）＋搜索自动展开（派生态，快照还原）。
- 测试：后端 order 端点全套（持久化/幂等/子集/未知/跨书/重复/空 400/不 bump rev/不作废门禁/新卡与撤销恢复落末尾/路由不遮蔽）＋ writer 钉序断言×5 ＋备份往返＋迁移缺列回归；前端 characterOrder 单测＋搜索展开/空态＋开关持久化；e2e 拖拽→PUT 载荷→刷新保序、分组开关、搜索三态。
- 依赖：无外部硬前置；前端拖拽联调依赖本 change 后端部分（过渡期 e2e 可 `page.route` 桩）。
