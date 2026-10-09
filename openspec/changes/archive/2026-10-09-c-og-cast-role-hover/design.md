# design — c-og-cast-role-hover

## Context

章纲页签出场角色的胶囊今天只有两类词：名字本身＋没卡名的「没卡」小标（`.no-card`）与「建卡」入口，查看态（`.fro` 逐名渲染）与编辑态（`og-char-picker` 候选 chip）两处同貌（见 proposal.md）。角色数据 `charactersApi.list` 一次就给全 `role/persona/dossier/aliases/first_chapter`，`ChapterWorkspace.refreshCharacterNames` 已经在循环这张表（取名字与别名、找主角名），只是把名字摊平成了 `string[]` 后丢掉了卡信息。

悬停浮层有两个既有约束：① `.og-pane` 是 `overflow-y: auto` 滚动容器，绝对定位浮层会被裁切 → 须走「portal 到 body ＋ fixed」（`.mp-panel` 先例）；② 大屏缩放层 `html { zoom: var(--ui-zoom) }` 会把 `getBoundingClientRect()` 的视觉值再放大一次 → 折算逻辑已收口在 `lib/panelAnchor.ts`（`htmlZoom()` / `placePanel()`）。

## Goals / Non-Goals

**Goals:**
- 两态胶囊同貌带身份小标；悬停（含键盘聚焦）出只读身份卡（人设＋基础档案）。
- 定位/裁剪/zoom 三个坑复用既有收口（`panelAnchor` 的 `htmlZoom` 折算 + portal），不自造第二套弹层定位。
- 角色清单不可用时优雅退化（纯名字胶囊），不阻断章纲页签。

**Non-Goals:**
- 不做身份卡内编辑/跳转动作（要改卡去设定页角色表）。
- 不动后端契约、不给关系图/角色表改角色语义；不做悬停卡的持久化偏好。
- 不做 touch 长按替代手势（桌面应用，pywebview/鼠标为主）。

## Decisions

1. **数据通道：`castInfos` 映射随既有角色刷新派生，别名同键归卡。** `ChapterWorkspace` 在 `refreshCharacterNames` 的既有循环里顺手产出 `Record<string, CastInfo>`（名字与每个别名各一键 → 同一张卡摘要），新增可选 prop 传 `OgPane`。
   - 备选：OgPane 自己拉角色表——否：面板已由工作台统一喂数据（`characterNames`/`protagonistName` 同源），再拉一遍是第二数据源与多余请求。
   - 备选：把 `characterNames` 升级成对象数组——否：现有 prop 名与语义（含别名展开的「已知名」集合）被缺人探测等三处复用，改形制牵连面大。
   - 可选 prop（`castInfos?`）保住既有测试与渲染路径：缺映射＝纯名字胶囊（退化态即 spec 的失败退化条款）。

2. **身份小标 `.cast-role`＝chip 内 10px 小标，四档配色沿角色类型色语言。** 主角 accent（accent-soft 底＋accent 字）、反派 err（err-soft 底＋err 字）、配角 muted（fg-soft 底）、路人 muted 虚线描边（对应关系图 `.rg-node.role-extra/ghost` 的虚线语义）。这与 `CharacterManager` 的 `.badge`（状态语义：已立主角/主角待立）分开——身份标只表身份不表状态，故不复用 `.badge` 的 ok/warn 档。
   - 备选：只标主角/反派/配角三档、路人不标——否：role 是四值闭集，缺标产生「没标是路人还是漏了」歧义（proposal 已按四档定口径）。
   - 备选：纯文字不着色——可做但扫读性差，且角色类型色语言已有先例（关系图），复用不发明新色。

3. **身份卡 `.cast-hover`＝portal＋fixed 悬停面卡，复用 `htmlZoom()` 折算，卡宽固定 300px 居中于胶囊并夹在视口内。** 竖向默认向下（gap 6px），下方不足且上方更宽裕则翻转向上；卡 `max-height` 限高＋自身滚动。锚定/翻转的 zoom 折算口径照抄 `panelAnchor`（`rect/z`），滚动与 resize 时重锚（`.mp-panel` 先例），Esc 与移出即收。
   - 备选：原生 `title` 属性（本仓 hover 信息的最常见形态）——否：用户要「看到基本信息、人设」的多行结构化信息，title 只能塞一行纯文本且不可选读；本卡是信息面不是提示语。
   - 备选：就地绝对定位（不 portal）——否：`.og-pane` 滚动裁切（已实证约束）。
   - 打开延迟 150ms／关闭宽限 150ms：扫过一排胶囊不闪卡，鼠标能移进卡内继续读（卡内文字可选中）。

4. **卡内容只读、空格不占位**：正名＋身份标 → 别名行（有才出）→ 一句话人设 → 基础档案已填格（性别·年龄·种族按 `DOSSIER_FIELDS` 前三键合一行，其余逐行；标签取 `characterModel.DOSSIER_FIELDS` 单源，不手抄中文标签）→ 首次出场行（`first_chapter` 有值才出）。长值行内折 2 行（`-webkit-line-clamp`），卡内不再滚动条抢戏（限高兜底）。
   - 备选：把认知六层也塞进来——否：那是「他怎么想」不是「基本信息、人设」，卡会变成小角色表；要看全卡去设定页。

5. **没卡名不出标不出卡**：「没卡」标＋建卡入口已在胶囊上自明；悬停给「没有角色卡」浮层是重复信息。

## Risks / Trade-offs

- [悬停卡遮住邻近胶囊/按钮] → 固定 300px 窄卡＋胶囊旁居中＋视口夹取；卡只在悬停期存续，移出即收。
- [角色很多时映射体积] → 每卡摘要只留展示字段（不含 cog 30 格），一书几十卡量级无感。
- [两处胶囊渲染各写一遍身份标走形] → 小标与身份卡各抽一个组件（`RoleTag`/`CastHover`）两态共用，vitest 断言两态同词同貌。
- [design-parity-book 的 workbench 场景整页截图含 chip 默认态] → 该场景不在 `design:check` 矩阵（只跑书架＋preview）；仍同貌更新原型 book.html 保基线诚实，回归小节记录实测差异比。
- [jsdom 无 `zoom`/布局] → 复用 `htmlZoom()` 的既有兜底（读不到＝1），定位逻辑可单测（传入 zoom 参数）。

## Migration Plan

纯前端增量：无数据迁移、无契约变更。合入即生效；回滚＝整笔 revert（新组件与新 CSS 类随之消失，无残留引用）。
