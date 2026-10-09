# c-og-cast-role-hover — 章纲出场角色胶囊：身份标＋悬停身份卡

## Why

章纲页签的出场角色胶囊今天只显示名字（外加「没卡」小标），看不出谁是主角、谁是反派、谁是配角，更看不到人设——要核对「这场戏谁来演、他是什么人」只能跳设定页翻卡或凭记忆。用户 2026-10-09 提出：每个胶囊标出身份（主角/反派/配角），鼠标放上去能看到 TA 的基本信息与人设。

## What Changes

- **胶囊身份标**：出场角色胶囊（查看态逐名 chip 与编辑态 `og-char-picker` 候选 chip 两态同貌）里**有角色卡**的名字带一枚身份小标，取值跟随角色卡 `role` 四档：主角／配角／反派／路人（四档同标——第三档「配角」与用户点名的主角/反派同族，「路人」同属 role 闭集，缺标会产生「没标＝配角还是路人」歧义）。没卡名维持既有「没卡」标与「建卡」入口，不出身份标。
- **悬停身份卡**：鼠标悬停（含键盘聚焦）有卡胶囊浮出**身份卡**：称呼（角色卡正名）＋身份标＋别名行（有才出）、一句话人设、基础档案已填格（性别·年龄·种族合一行，其余势力·身份／外貌标签／语言特征／背景／剧情定位逐行）、首次出场章号（有才出）。没卡名不出卡（「没卡」标＋建卡入口已在胶囊上自明）。
- **数据零后端**：`charactersApi.list` 既有字段（`role`/`persona`/`dossier`/`aliases`/`first_chapter`）就够——`ChapterWorkspace` 在既有角色清单刷新里顺手聚合成「名字（含别名）→ 卡摘要」映射下发 `OgPane`，别名归到所属卡。
- **明确不做**：不改角色表/关系图的角色语义与四档取值；不改「没卡」标、建卡入口与 textarea 直输名；不给身份卡加编辑/跳转动作（看信息用，要改卡去设定页）；不动后端契约。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 章纲页签出场角色胶囊新增身份标与悬停身份卡——查看/编辑两态同词同貌、别名归卡、没卡名不出卡。
- `design-system`: 组件词汇登记——`.cast-role`（chip 内身份小标，沿 `.no-card` 小标形制，四档配色沿角色类型色语言）＋`.cast-hover`（悬停身份卡浮层：portal＋fixed，沿 `.mp-panel` 裁剪对策先例）；无新令牌档、无新语气档、无第四种胶囊形态。

## Design Impact

- **受影响端**：C端（单端）。新类落在 `book.css` 的 cast-* 作用域族，不触 `base.css` 令牌与 `pill/notice/sk/panel/f-err` 共享段（→ 无需 design-cross；判定依据：只组合既有 token 的 C端 业务类）。
- **受影响的屏/弹层**：章工作台 › 章纲页签（查看态 `.fro` 出场角色行＋编辑态 `og-char-picker`）；新增悬停身份卡浮层（悬停态不在 parity 采样帧）。
- **用到或新增的对象状态**（对照状态语言总表）：无新状态语义——身份标是**身份标签**（角色卡 `role` 属性，对象是谁）不是状态（对象怎样）；四档配色沿既有角色类型色语言（关系图 `.rg-node.role-*` 先例：主角 accent／反派 err／配角 muted／路人虚线 muted），不引入 info/ok/warn/err 之外语气档；身份标沿「chip 内小标」既有形制（`.no-card` 同款 10px 胶囊），不新增第四种胶囊形态档位。
- **是否触碰两端共享段**：否。
- **是否需要原型先行**：需要——`prototypes/book.html` `og-char-picker` 两态胶囊补身份标（含悬停身份卡 demo）；`ADJUSTMENTS.md` 登记。`design-parity-book` 的 workbench 场景不入 `design:check` 矩阵（design:check 只跑 书架＋preview 两 spec），chip 默认态仍按同貌更新原型保基线诚实。
- **设计工件产出**：实现侧自查（复用既有词汇与角色类型色语言，无新视觉形态），无需设计侧会话。

## Impact

- 前端：`components/novel/workbench/OgPane.tsx`（两态胶囊挂身份标＋悬停）、新组件 `components/novel/workbench/CastHover.tsx`（身份卡＋小标＋fixed 定位）、`components/novel/workbench/ChapterWorkspace.tsx`（角色清单聚合 castInfos 下发）、`design/book.css`（`.cast-role` / `.cast-hover`）。
- 后端：无（`charactersApi.list` 既有字段）。
- 测试：vitest（身份标四档渲染／悬停卡内容与别名归卡／没卡名无标无卡／编辑态同貌）；既有 e2e 如断言 chip 结构需复核更新。
- 原型：`docs/design-c/prototypes/book.html` + `prototypes/ADJUSTMENTS.md`。
- 依赖：无新增依赖。
