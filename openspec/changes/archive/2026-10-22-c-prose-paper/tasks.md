## 1. 纸面骨架（组件＋样式）

- [x] 1.1 `ProsePane.tsx` 在 `.editor-wrap` 内新增 `.prose-paper` 包裹层，把 `.gen-line`、`.tk-*` 族与 `EditorContent` 一起包进去；确认 `wrapRef` 仍挂 `.editor-wrap`（滚动容器不变）。验证：`npm test -- chapterWorkspace` 与 `renweiCheck` 通过，`.editor-wrap` 的 `scrollTop` 相关断言不变
- [x] 1.2 `book.css` 新增纸面令牌（桌面／纸／纸边／纸投影／范围框／纸边距／版心），并用 `clamp` 双变量实现「先挤纸边距、再挤版心、恒留 12px 桌面缝」。验证：1280/1440/1920 三档下 `.editor` 计算宽度分别为 676/680/680，`scrollWidth - clientWidth = 0`
- [x] 1.3 纸面规则：`.prose-paper` 白面＋`inset` 纸边（不用 `border`）＋投影＋纸边距；`.editor-wrap` 去 `padding-inline` 换桌面底；`.editor-wrap.editing` 去连体边框/圆角/`--surface` 底。验证：`.editor` 计算宽度恒 680（1440 档）、纸宽 808、无横向溢出；目视确认桌面在纸两侧与上下可见

## 2. 写字范围框（编辑态）

- [x] 2.1 新增装饰节点 `.prose-frame`（`aria-hidden`，`pointer-events:none`，`position:absolute`，`1px dashed`，四条边由 `inset` 给出），位置走纸边距同一变量。验证：编辑态 `getComputedStyle` 为 `dashed`，框与版心左右边缘对齐（截图比对）
- [x] 2.2 阅读态整框隐藏（`.editor-wrap:not(.editing)` 下 `display:none`），编辑态显示；框随纸滚动。验证：切换两态断言 `display` 值，滚动到中段截图确认框仍在版心边缘

## 3. 生成期四处随纸归位

- [x] 3.1 `.gen-line` 的 `top` 改为纸的上内边距变量、宽度由纸边距变量推出（删掉 36px 魔数）。验证：触发一次生成（真实或打桩）截图，等待行落在版心首行、缩进与正文一致
- [x] 3.2 呼吸灯改环纸面（不再罩工具行与两侧桌面），保留「首个正文片段到达起、收尾即止、box-shadow 不改版式」。验证：流式期截图 + 既有 `proseStream`/`thinkingDisplay` 单测通过
- [x] 3.3 思考面板／收起条／回看抽屉／超时卡全部落在纸内且与正文同列宽。验证：四种形态逐条截图（`think-panel`、`think-bar`+`think-drawer`、`think-timeout`），宽度均等于版心
- [x] 3.4 人味边注与朱雀标记在宽屏仍在纸边距内。验证：开启人味标记后截图，`.zq-mark` 不出纸；窄屏下边注偏移改为 `min(46px, 纸边距)`（或按纸边距阈值隐藏）

## 4. 原型基线与门禁

- [x] 4.1 更新 `docs/design-c/prototypes/book.html` 的正文区到纸面形态，并在 `prototypes/ADJUSTMENTS.md` 登记「正文区上纸」（含几何与范围框口径）。验证：`npm run design:check` 的 book parity 回到阈值内（<0.2%）
- [x] 4.2 `npm run design:lint` 通过；新增颜色只用 oklch/color-mix/既有令牌，无裸 hex/rgb。验证：lint 零违规；`check-inline-colors` 通过

## 5. 回归与真机验收

- [x] 5.1a 全量单测 1763 全绿（`vitest run` 139 文件）＋ `npm run build`（含 `check-inline-colors` 与 legacy-colors 150 条覆写）＋ `design:lint` 零违规
- [ ] 5.1b e2e 关键路径（`free-writing-flow` / `design-parity-book`）——需独立 S端 栈（本机共享 demo S端 不用于本会话验证），留 CI 与真机跑；滚动/贴底/纸随文动已用 Playwright 直测（scrollTop 800 → 纸位移 -800，贴底后纸下留 56px 桌面）
- [x] 5.2 真机抽检 1440 / 1280 / 专注态三屏：阅读态无范围框、编辑态有虚线框、纸边与桌面对比可见、长章滚动时纸边跟着走。验证：三屏截图入库 PR 说明
- [x] 5.3 生成链路真机抽检：点「生成正文」跑一次真实生成，确认等待行/思考面板/呼吸灯/正文四者的位置与范围。验证：录像或四张连续截图
