## 1. 原型先行

- [x] 1.1 `docs/design-c/prototypes/preview.html` 阅读区改纸面形态：`.pv-prose-wrap` 换桌面底、渲染模板加 `.pv-paper` 包裹层（章头＋正文进纸）、护眼/夜间两条回退规则，与实现同构。验证：浏览器打开原型目视——白纸档桌面/纸两层，护眼/夜间整面填色不变
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记「预览阅读区上纸」：默认白纸档由整面 `--bg` 改为桌面/纸两层（与写作页 `c-prose-paper` 同源令牌）、纸宽与写作页同式而内容列仍 66ch（design.md D4 取舍）、护眼/夜间不上纸

## 2. 纸面令牌单源化

- [x] 2.1 `book.css` 把 `c-prose-paper` 令牌块（桌面/纸面/纸边/纸投影/纸边距/版心/桌面缝）的选择器从 `.col-editor` 扩为 `.col-editor, .preview-v`（design.md D1，不在预览侧复制第二份值）。验证：写作正文页渲染零视觉变化（阅读态/编辑态各截一图与改前对拍）

## 3. 预览阅读区上纸

- [x] 3.1 `PreviewView.tsx` 在 `.pv-prose-wrap` 内新增 `.pv-paper` 包裹层，把 `.pv-chapter` 与 `.pv-prose` 包进去；滚动容器仍是 `.pv-prose-wrap`。验证：`previewReader.test.tsx` 通过，章级导航（上一章/下一章）断言不变
- [x] 3.2 `book.css` 新增预览纸面规则：`.pv-prose-wrap` 换 `var(--paper-desk)` 底并去自身 padding；`.pv-paper` 白面＋`inset` 纸边＋投影＋纸边距，宽度沿用写作页同款 clamp 双变量与 `min` 宽公式，`flex: 1 0 auto`（空章/短章纸也撑满桌面，与 `c-paper-empty-fill` 语义对齐）。验证：默认主题宽屏目视两层、纸两侧可见桌面缝；窄列先挤纸边距、无横向滚动
- [x] 3.3 护眼/夜间回退：`.pv-theme-sepia` / `.pv-theme-night` 下 `.pv-prose-wrap` 恢复整面填色与原 padding、`.pv-paper` 退化为透传（无底/无影/无纸边距），回退处注释「新增主题档必须同步回退」。验证：三档切换即时生效，护眼/夜间目视与改前一致

## 4. 门禁与原型 parity

- [x] 4.1 `npm run design:lint` 零违规（本 change 无新颜色，全部消费既有令牌）。验证：lint 通过；`check-inline-colors` 通过
- [x] 4.2 `npm run design:check` 预览 parity 随原型同批回到阈值内（<0.2%），book parity 复跑不回退。验证：两屏 parity 数值记录进 PR 说明
- [x] 4.3 `tsc --noEmit` 与 `vitest run` 相关面（`previewReader`＋`chapterWorkspace`）全绿。验证：本地跑通并记录用例数

## 5. 回归与真机验收

- [x] 5.1 全量单测＋`npm run build`（含 legacy-colors 覆写）。验证：全绿；legacy-colors 编译副本条数不异常
- [ ] 5.2 真机抽检：默认白纸（宽屏/窄列分屏）、三档主题往返切换、翻章滚动（纸随文走）、空章提示在纸上。验证：截图入库 PR 说明
- [ ] 5.3 e2e 关键路径——需独立 S端 栈（本机共享 demo S端 不用于本会话验证），留 CI 与真机跑。验证：CI e2e 绿或记录豁免口径

---

双端判定：本 change 不触两端共享段——改动全落 `book.css`（C端业务层）与 `PreviewView.tsx`，不碰 `base.css` 令牌与基础组件类（proposal「Design Impact」判定依据），免双端同改与 `design-cross.mjs`。
