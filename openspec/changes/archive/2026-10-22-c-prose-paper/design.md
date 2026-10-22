## Context

正文列的现状几何（真机实测，`docs/design-c/drafts/prose-paper-captures/metrics.json`）：中栏约 860px，`.editor-wrap` 的 `padding: 36px clamp(24px,6vw,72px) 120px`，版心 `.editor` `max-width: 680px` 居中；列底 `--bg`（oklch 98%）与编辑态 `--surface`（纯白）几乎同色，编辑态还靠「顶条与正文区同底色＋连体外框」合成一个控件来提示"在编辑"。

三个约束决定了实现形态：

1. **滚动容器不能搬**。`ProsePane` 的 `wrapRef` 承担续写滚动比例恢复（`scrollTop/scrollHeight`）、生成时贴底自动滚（`scrollHeight - scrollTop - clientHeight < 160`）、思考面板锚尾滚动；e2e `free-writing-flow.spec.ts` 也直接对 `.editor-wrap` 设 `scrollTop`。任何把滚动挪进纸内的方案都会动到这一串。
2. **版心 680 是设计常量**，不能被纸边距挤掉；而 1280 宽的三栏布局下中栏只有 700px，纸边距与桌面缝必须会自己让路。
3. **正文列里还有三组"住客"**：生成等待行（`.gen-line`，absolute、`top:36px` 硬编码了 wrap 的内边距）、思考面板族（`.tk-live/.tk-anchor/.tk-bar/.tk-drawer/.tk-timeout`，`max-width:680; margin:auto` 挂在 wrap 下）、人味边注（`.zq-mark`，`left:-46px` 住在版心左侧空白里）。

原型（A 连续纸 + 白纸 + 编辑态虚线框）已完成并经拍板，几何、令牌与三处耦合都在原型里验证过；本设计只记录落地路径与取舍。

## Goals / Non-Goals

**Goals:**

- 用一层新包裹元素承载"纸"，不改滚动容器、不改版心、不改数据与生成链。
- 让纸边距随列宽自适应：宽屏 64，窄屏先挤纸边距、再挤版心，纸两侧永远留最小桌面缝。
- 让写字范围框只在编辑态出现、随纸滚动、不参与任何交互。
- 把"编辑工具行与正文连体"的旧形态干净替换为两层，同时保住填屏、呼吸灯、等待行/思考面板的既有行为。

**Non-Goals:**

- 不做真分页（按页切断、跨页断行）。
- 不做纸色偏好、标尺、页边距拖拽、纸张纹理。
- 不改动 `.editor` 的字体/行高/夹取规则，不改 `zq-*`/`rw-*` 的标记几何。
- 不动右栏、左树、页签条与头部徽章行。

## Decisions

### D1：纸是一层普通流内包裹，滚动仍在 `.editor-wrap`

`ProsePane` 在 `.editor-wrap` 内新增 `<div className="prose-paper">`，把 `.gen-line`、`.tk-*` 族与 `EditorContent` 一起包进去；`wrapRef` 仍挂 `.editor-wrap`。

- **为什么**：滚动容器不动 ⇒ `resumeScroll`、贴底自动滚、e2e 的 `.editor-wrap` 口径全部零改动；纸随内容长，正是"连续纸"。
- **否掉的替代**：①固定纸（纸钉在视口、文在纸内滚）——观感更像一页，但要把滚动搬进纸里，打断上面那一串依赖；②不包裹、纯靠 `box-shadow` 在 `.editor` 上铺纸色——无法表达上下纸边距、也无法让思考面板进纸。

### D2：纸宽与纸边距用两条同文本的 `clamp` 表达

```
--paper-pad-x:  clamp(20px, (100% - 680px - 2*12px) / 2, 64px)   /* 用在 padding 上，100% = 列宽 */
--paper-guide-x: clamp(20px, (100% - 680px) / 2, 64px)            /* 用在 inset 上，100% = 纸宽 */
width: min(808px, 100% - 24px)
```

下限 20px 是实机修正的产物：初版按「纸边距压到 0 再压版心」实现，1280 档实测正文**贴着纸边**（纸边距 0），看起来像没做完而非"窄屏"——纸边距低于 20px 就该让版心让路。

- **为什么**：CSS 的百分比在两个上下文里基准不同——`padding` 的 100% 是包含块（列）宽度，`inset`/`background-position` 的 100% 是纸自身的盒宽。写两条同式子的变量，正好覆盖"纸满列"与"纸窄于列"两种情形：宽屏时两者都取到 64；列窄到容不下 808 时，第一条先降到 (列宽-704)/2，纸边距变小而版心不动；再窄则两者都归 0，版心开始跟着列宽走。
- **否掉的替代**：媒体查询逐档写死纸边距——1280/1366/1440/1920 之外还有分屏与窗口拖拽，档位永远补不全。
- **代价**：两个变量同名不同义，必须靠注释说明；自检脚本里加了一条"范围框必须走 `--paper-guide-x`"的守卫，避免以后有人只改其中一条。

### D3：纸边用 `inset` 阴影而不是 `border`

- **为什么**：`border` 会吃掉 2px 内容宽，版心从 680 变 678（原型第一版实测踩过）。`box-shadow: inset 0 0 0 1px` 不参与布局。
- **代价**：纸边不能单独设圆角颜色（本设计也不需要）。

### D4：写字范围框＝一个装饰节点，不是伪元素

新增 `<span className="prose-frame" aria-hidden="true">`，`position:absolute; border:1px dashed; pointer-events:none`，`inset: 56px var(--paper-guide-x) 72px`。

- **为什么**：需要左右＋上下四条边，两个伪元素不够分；一个节点同时给出四条边，且虚线样式由浏览器原生 dashed 提供，不用手写 repeating-gradient。
- **否掉的替代**：`::before/::after` 各画一条竖线——只能左右两条，且渐变淡出让"虚线"很难做。
- **可见性**：阅读态用 `.editor-wrap:not(.editing) .prose-frame { display:none }` 整框隐藏（不是调淡），编辑态才画。

### D5：编辑工具行与正文解耦

`.ol-top.edit-bar` 去掉圆角与连体边框、只留一条下分隔线；`.editor-wrap.editing` 去掉 `--surface` 底、边框与下方圆角，改桌面底。

- **为什么**：纸出现后，"工具行与正文同底色连体"会与纸边投影打架（工具行看起来也是纸的一部分，但没有纸边距）。解耦后工具行归列头、纸归内容，两者互不污染。
- **代价**：规范里"成形编辑框＝一个控件"的口径退役（本 change 的 MODIFIED 条目），查看/编辑的区分改由"无工具行 vs 有工具行＋范围框"承担。

### D6：呼吸灯环从"工具行＋正文整列"改为"纸"

`.prose-body.generating` 的 box-shadow 环移到纸包裹层上。

- **为什么**：纸出现后若仍环 `.prose-body`，环会落在桌面上（纸两侧与上沿），看起来像界面在闪而不是正文在写。
- **代价**：MODIFIED「正文生成中的现场保护」的生成状态可视口径。

### D7：生成等待行与思考面板随内容进纸

`.gen-line` 的 `top` 从硬编码 `36px` 改为纸的上内边距变量；宽度改由 `--paper-guide-x` 推出。

- **为什么**：它必须落在版心首行位置；上纸后 `36px` 这个魔数失去意义（现由纸边距决定），顺手删除。

## Risks / Trade-offs

- [parity 必红] → 实现 PR 同批更新 `docs/design-c/prototypes/book.html` 并在 `ADJUSTMENTS.md` 登记"正文区上纸"；不靠调阈值。
- [窄屏行宽变宽] 1280 下版心从今天的 556 变 676、1024 下从 371 变 470（纸边距体系比现有 `padding-inline: clamp(24px,6vw,72px)` 更省空间）→ 验收按 1280 与 1024 各看一眼；这是"更接近 680 常量"的改善，但要确认作者接受行宽变化。
- [窄屏人味边注出纸] 列窄到纸边距 0 时 `.zq-mark(left:-46px)` 会压到纸边/桌面 → 实现时把边注偏移改为 `min(46px, 纸边距)`，或仅在纸边距 ≥56 时展示边注。
- [思考面板/等待行定位漂移] 它们都挂在 wrap 下，进纸后定位基准变成纸 → 四条生成路径（等待行、思考面板、收起条/回看、超时卡）必须逐条截图验证；这是两个已上线 change（c-prose-gen-phases、c-thinking-display）的成果，不能回退。
- [滚动容器的隐性契约] `body.focus .editor-wrap { padding-inline: 8vw }` 与 `.gen-line top:36px` 都建立在现有 padding 上 → 前者由纸自居中吸收（不改），后者按 D7 改。
- [横向溢出] 纸宽 + 桌面 > 列宽时会出横向滚动条 → 纸宽写 `min(808px, 100% - 24px)`；自检里保留 `scrollWidth - clientWidth = 0` 断言。

## Migration Plan

1. 组件加纸包裹层（D1）→ 样式换代（D2/D3/D5）→ 范围框（D4）→ 生成态四处（D6/D7）。
2. 每步都跑：`npm run design:lint`、`design:check`（先更新 book 原型）、`free-writing-flow`、`design-parity-book`、以及正文/思考相关单测。
3. 回滚：本 change 纯前端呈现层，回滚＝还原该 PR；无数据迁移、无接口版本兼容问题。

## Open Questions

- 空章/短章在**阅读态**是否也把纸撑满一屏（Word 恒整页）。当前取"编辑态撑满、阅读态随内容"，实现后看真机观感再定；不影响规格与任务拆分。
- 桌面是否在专注态之外再加一层极淡内阴影——当前不加（扁平底座），可后续单独调。
