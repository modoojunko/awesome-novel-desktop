# Design — c-renwei-narrow-dot-anchor

## Context

人味边注层（`.rw-marginlayer`）是 `.editor-wrap`（中栏）内的绝对定位覆盖层，宽度＝整个中栏，而不是纸面。带文字的边注列由 `RenweiMarginNotes.measure()` 实测正文栏（`.editor`，680px 版心）右缘，写 `--rw-notes-left = 右缘 + 16px`；右留白 < 120px＋16px 时挂 `rw-notes-narrow`，CSS 把边注收成 8px severity 圆点。

现状问题：塌缩规则是 `left:auto; right:2px`——锚在覆盖层（＝中栏）右缘，也就是中栏与右栏写作助手交界/滚动条旁。中栏 760~980px（开右栏的常见窗口）时纸右侧还有桌面缝，圆点离被标记段可达数百 px；2026-11-27 老板截图再次实锤。

11-22 真机两连已排除两个中间方案：钉层缘＝脱离段落飘到滚动条旁；钉列缘（正文右缘＋16px）＝「行的最右侧」，短行时离文字太远。因此锚点必须是**每段各自的段尾**，不是任何一条竖向边缘。

约束：正文锁死（覆盖层不占布局流）、不得横向滚动、不得把边注推向窗口最右（既有 Requirement）；窗口/栏宽/zoom/字号变化都要重锚；不新增视觉形态与状态。

## Goals / Non-Goals

**Goals:**

- 塌缩态圆点跟段落末字走：短行贴末字右侧，满行贴列缘外侧；纵向与末行居中对齐。
- 圆点在任何中栏宽度/字号档下都不被裁切、不压正文、不触发横向滚动。
- 把「圆点跟末字」变成可单测的几何不变量，并覆盖量测缺席的兜底。

**Non-Goals:**

- 不改塌缩触发阈值（120px＋16px）、圆点 8px 尺寸、err/warn 颜色、hover 详情卡内容。
- 不改宽栏带文字边注的位置/宽度/详情卡方向。
- 不做第三种锚点形态（层缘/列缘/纸边）；段尾是唯一锚。
- 不改原型基线的像素形态（原型从未包含人味边注运行态）。

## Decisions

### D1：锚点＝段尾实测（末字后缘），不做任何竖向边缘锚

- 选择：用 `Range` 取该段**最后一个文本节点**末尾的插入位矩形，圆点横向＝`rect.right + 3px`（盒内衬；8px 点与末字视觉间距约 6px），纵向＝`rect.top + (rect.height − 18px)/2`（按末行行高中点对齐）。
- 理由：只有段尾能表达「这枚点属于这一段的末尾」；短行、满行两种极端都自然成立（满行时插入位 x 恰等于列缘，圆点落在列缘外侧的纸边距上）。
- 备选：
  - 钉层右缘（现状）＝脱离段落、贴右栏模块/滚动条；11-22 判例否决。
  - 钉列缘（正文右缘＋16px）＝所有段共用一条竖线，短行离文字远；11-22 二次反馈否决。
  - 钉纸面右缘＝纸边距被挤到 20px 时会压纸边，且与文字脱钩；否决。

### D2：逐段内联 `left/top`，不引入单一 CSS 变量

- 选择：`measure()` 为每个问题段算出 `{top,left}` 存 `dots` 状态，窄栏渲染时内联到 `.rw-mnote`；宽栏仍用 `--rw-notes-left`。
- 理由：每段末字 x 不同（短行可差几百 px），一个 CSS 变量无法表达；内联值也让单测可直接断言。
- 备选：CSS `left: min(...)` 单一锚——只能表达列缘，正是被否决的形态；仅保留作量测缺席兜底。

### D3：量测缺席回落列缘兜底，两条路径都钳在层内

- 选择：`textEndRect()` 失败（首帧、无布局）时不给内联 left；CSS 窄栏规则 `left: min(var(--rw-notes-left), calc(100% - 20px))` 兜底。有内联锚时组件同样 `Math.min(计算值, layerW − DOT_BOX_W − 2)`（盒宽 18＋2px 内缩；层已有 `overflow-x:hidden`）。
- 理由：首帧不能把圆点甩到 0 或层外；极窄列（正文右缘＋16px 放不下 18px 盒）时向左收 4px，8px 圆点仍完整、距正文 ≥15px。两条路径同一钳制口径，未来纸边距改动也不会让内联锚越界。
- 备选：量测失败就隐藏圆点——丢指路入口；弃。

### D4：取最后一个含可见字的正文文本节点，跳过装饰/控件

- 选择：递归收集段内文本节点，跳过装饰/控件子树（`.zq-mark`、`.ProseMirror-widget`、`[contenteditable="false"]`）；从尾往前找第一个 `trim()` 非空的节点；再剥掉尾部空白/零宽字符（`/[\s\u200b]+$/`），`setStart/setEnd(last, end)`。
- 理由：段落末尾若有 `<br>` 等空节点，整体 collapse 会把插入位落到下一行行首，圆点跳行；尾部空格/零宽字符也会让插入位在满行时折到下一行行首。更关键的是朱雀 band 尾章是段内最后一个文本节点（`contenteditable=false` 的「AI／疑似」widget），人味标记态又会把它移到左边距——不跳过就会量到左margin、圆点被劫持到段落开头。Range 新建默认折叠在 `(document,0)`，起止都要显式落到末字后。
- 验证：真 Chromium 探针（段尾挂 `.zq-mark`）修前 picked=`疑似`、rect.right=127（正文末字 259.6）；修后 picked=正文末字、rect.right=259.6；单测「段尾是朱雀判定章」钉子。

### D5：顺带修 RO 闭包的 stale `groups`

- 选择：`groupsRef.current = groups` 每次渲染同步；`measure()` 从 ref 取当轮问题段。
- 理由：ResizeObserver 的 deps 只挂 `editorEl`（避免每次 findings 变化重挂观察器），闭包里的 `groups` 会过期；圆点锚依赖 findings，按旧组重算会互相覆盖/残留。

### D6：窄栏整盒不吃事件，只有圆点与详情卡可交互

- 选择：`.rw-notes-narrow .rw-mnote { pointer-events:none }`，`.nt .dot` 与 `.dtl` 恢复 `auto`。
- 理由：18px 盒从末字后 3px 起压住纸边距，正是「点段尾落光标/继续打字」的点击带；整盒吃事件会抢走 contenteditable 的 mousedown/focus。`hover` 会命中祖先，悬停圆点仍亮详情卡；卡内按钮在 `.dtl` 上恢复 auto，操作不受影响。
- 验证：真 Chromium 探针——末字右侧 +1/+16px 的 `elementFromPoint` 均命中 `<p>`；悬停圆点 `.dtl display=block`；点卡内按钮回调触发。
- 备选：`onMouseDown` 转发焦点到 editor——要处理 caret 落点/选区，复杂且易与编辑器手势冲突；弃。

### D7：逐字编辑用 MutationObserver（rAF 合并）重锚

- 选择：独立一条 `[editorEl]` effect 装 `MutationObserver`（`subtree/characterData/childList`），rAF 合并测量；不依赖 `ResizeObserver` 是否存在（jsdom/旧环境也能装）；清理时 `disconnect()`。
- 理由：圆点 x 现在依赖末行内容，而输入不改变尺寸、RO 抓不到；不重算会停在旧文字末尾直到 0.7s 重扫回来（期间可能压在刚打的字上）。rAF 合并避免每个字符都测量。
- 备选：每次 findings 重扫才重锚——有最长 ~1s 的错位窗口；弃。

### D8：宽栏不算段尾锚

- 选择：先算 `isNarrow`，只有窄栏才遍历问题段做 Range 量测并 `setDots`；宽栏沿用 `--rw-notes-left` 文字列，`dots` 不更新。
- 理由：滚动 rAF 里宽栏白跑 N 次 Range 读取＋state churn；`narrow ? dots[g.para] : undefined` 的门同时挡住「窄→宽」切换时上一档的 stale 段尾锚。
- 验证：单测覆盖宽栏无内联 left、窄→宽切换后 stale dots 不跟进，以及「段内续写 → MutationObserver 重锚 → left 更新」。

## Risks / Trade-offs

- [每次滚动帧为每个问题段做 Range 量测，成本高于纯 top 测量] → 只在窄栏做（D8），measure 已按 rAF 节流；问题段数量级为个位数（按段聚合），Range 量测在毫秒级。逐字输入另加 MutationObserver，同样 rAF 合并。
- [jsdom 的 Range 几何由 test-setup 给全零桩] → 单测用 `vi.spyOn` 覆写并 `afterEach` 收桩（断言失败也不漏桩）；真 Chromium 探针验证插入位矩形/collapsed range 行为。
- [非 Chromium 的 WebKit 对 collapsed Range 可能返回 height 0] → `measure()` 在 height 0 时回落到段落 computed line-height 补足（单测已钉）；桌面端仍是 WebView2/Chromium。
- [详情卡仍朝左展开，圆点更靠左时覆盖更多正文] → 窄栏本来就没有右侧空间；详情卡是 hover 浮层，不改布局；圆点仍离正文 ≥6px，覆盖在预期内。
- [内联 left 与 CSS 兜底并存，可能出现一帧跳位] → `useLayoutEffect` 在绘制前完成测量与状态提交；首帧兜底本身就是可接受的「列缘位置」，不会甩到层外。

## Migration Plan

- 纯前端样式/测量改动，无数据、无接口、无配置迁移。
- 回滚：还原 `RenweiMarginNotes.tsx` 的段尾锚与 `book.css` 窄栏规则即回到 `right:2px`；无持久化影响。
- 发版需随下一个桌面包；开发态 Vite 即时生效。

## Open Questions

（无——锚点、兜底与测试口径均已在 specs 中定死。）
