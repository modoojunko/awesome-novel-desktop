# c-renwei-narrow-dot-anchor — 人味边注窄栏塌缩态「跟段尾走」，不回模块交界

## Why

人味检测标记态在窄栏会把边注收成一枚 severity 圆点（`rw-notes-narrow`）。现行实现 `left:auto; right:2px` 把圆点钉在边注层最右缘——也就是中栏与右栏「写作助手」模块的交界/滚动条旁，离被标记段可达数百 px。2026-11-27 老板截图再次实锤：红/黄圆点贴着右栏模块，而不是正文纸张。

此前真机两连（2026-11-22）已把口径钉清：钉层右缘＝脱离段落飘到滚动条旁；改钉列缘（正文右缘＋16px）＝「行的最右侧」，短行（如「熬的。」他说。）时离文字太远。因此本次采用**段尾实测**：圆点跟段落末字走——短行贴末字右侧，末行写满时贴列缘外侧。该实现已在本分支（PR #1128，CI 绿，待合）落地，本 change 负责规格落档、缺口收口与归档。

## What Changes

- **塌缩态锚点改段尾实测**：窄栏圆点 SHALL 以该段最后一个含可见字的文本节点末字后缘（Range 插入位矩形）为锚——横向＝末字后缘＋盒内衬 3px（点与末字视觉间距约 6px），纵向＝按末行行高中点对齐；SHALL NOT 钉层右缘/列缘/右栏模块交界。尾部空白/零宽字符 SHALL 跳过，避免插入位跳到下一行行首。
- **满行自然贴列缘外侧**：末行写满到版心右缘时，插入位 x＝列缘，圆点落在列缘外侧的纸右边距上——仍是文字真实位置，不写死列缘。
- **量测缺席/极窄兜底**：首帧/无布局环境（Range 矩形不可得）时回落 CSS `min(var(--rw-notes-left), calc(100% - 20px))`；有内联锚时组件按同一边界钳制（盒宽 18＋2px 内缩），圆点完整可见、不触横向滚动。
- **不抢正文光标**：窄栏圆点盒（18px 面）SHALL NOT 吃点击——只有 8px 圆点与展开后的详情卡可交互；点末字右侧仍能落光标/继续打字，悬停圆点仍出卡、卡内按钮可点。
- **编辑即重锚**：逐字输入/删改走 MutationObserver（rAF 合并）重算段尾锚，圆点不等 0.7s 重扫；切宽栏时 stale 段尾锚 SHALL NOT 跟进文字列。
- **跟随布局变化**：窗口尺寸、字号档、rail 开合、滚动都走既有测量管线重算；同时修掉 RO 闭包读旧 `groups` 的 stale 隐患（改走 `groupsRef`），避免 findings 换代时圆点锚互相覆盖。
- **规格与登记**：`renwei-check` 补「塌缩态锚点＝段尾实测」契约与场景；`prototypes/ADJUSTMENTS.md` 登记「塌缩态为产品实现层形态，锚点跟段尾、不钉列缘」。
- **非目标**：不改塌缩触发阈值（120px＋16px）、圆点 8px 尺寸与 err/warn 颜色、hover 详情卡内容与「标为已改/跳过」动作；不改宽栏带文字边注的位置/宽度/详情卡方向；不动正文宽度与朱雀左侧批注。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `renwei-check`：「正文左右分边注与覆盖层」Requirement 补塌缩态锚点契约——圆点锚＝段尾实测（末字后缘 Range 矩形），短行跟末字、满行贴列缘外侧；SHALL NOT 钉层右缘/列缘/右栏模块交界；量测缺席回落列缘兜底；新增「短行圆点跟末字走」「满行圆点贴列缘外侧」「量测缺席不裁切」三个场景。

## Design Impact

- **受影响端**：C端 前端（`client/frontend`，React＋CSS），无 S端、无数据、无接口。
- **受影响屏/弹层**：章工作台 · 正文页签（人味检测「标记到正文」后的边注覆盖层，查看/编辑两态同层）。不涉及报告弹窗、设定页、预览页。
- **对象状态**：无新增状态。仍沿用既有 severity 两档——`err`（一票否决，红）/`warn`（提示，黄），对照 design-language §5 状态语言总表；不新增语气词、不新增胶囊/徽标形态。
- **共享段**：不触碰。只改 C端 业务层规则（`.rw-marginlayer.rw-notes-narrow`）与 `RenweiMarginNotes` 测量代码；不改 base.css 令牌、基础组件类、pill/notice/sk/panel/f-err 家族。
- **原型先行**：不需要新稿。锚点语义沿用原型的「段角胶囊跟段尾走」口径（`docs/design-c/drafts/ai-novel-c端-人味检测-原型.src.html`，段角胶囊后因右栏简述退役）；run-time 基线 `docs/design-c/prototypes/book.html` 未画人味边注，本次不新增视觉形态，只在 `prototypes/ADJUSTMENTS.md` 登记一行实现层形态与锚点口径。
- **设计工件产出方**：实现侧自查（几何不变量用真实浏览器 Range 量测＋单测覆盖，无需设计侧出新稿）。

## Impact

- `client/frontend/src/components/novel/workbench/RenweiMarginNotes.tsx`：新增 `textEndRect()`（最后一个含可见字的文本节点末字后缘 Range 矩形，跳过尾部空白/零宽字符）、`DOT_BOX_H/DOT_BOX_W/DOT_GAP_TO_BOX` 常量、`dots`/`narrow` 状态、`groupsRef` 防 stale；窄栏才计算并内联 `left/top`（含覆盖层钳制），量测缺席走 CSS 兜底；MutationObserver（rAF 合并）在逐字编辑时重锚。
- `client/frontend/src/design/book.css`：窄栏规则删除 `right:2px`，改 `left: min(var(--rw-notes-left), calc(100% - 20px))` 作量测兜底；整盒 `pointer-events:none`、只有圆点与详情卡接事件；注释记录 11-22 两连判例、11-27 截图与点击穿透理由。
- `client/frontend/src/__tests__/renweiCheck.test.tsx`：锚点/zoom 折算/极窄钳制/宽栏不写内联锚/窄→宽切换/量测缺席/窄栏 CSS 源守卫共 7 条用例；`afterEach` 统一收原型桩。
- `docs/design-c/prototypes/ADJUSTMENTS.md`：补实现层形态、锚点与交互口径登记。
- 行为面：后端、检测算法、报告弹窗、数据存储零改动；宽栏带文字边注位置不变。
- 验证证据：真 Chromium 几何探针（短行点距末字 6.39px、满行 6px；点中心＝末行中心）；点击穿透探针（末字右侧 +1/+16px 命中 `<p>`，悬停圆点出卡、卡内按钮可点）；单测 18/18；变异验证（去 zoom 折算/去窄栏门/去钳制/回退 `right:2px` 均红）；全量 2349 passed / 1 skipped；`tsc` 0；CI `check` 绿。
- 流程：按老板立规，代码与测试齐备后只报 diff，commit/PR/打包/发版逐次等批准。
